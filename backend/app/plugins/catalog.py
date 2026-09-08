from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any

from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models.connector import Connector, ConnectorType
from .adapters import ExternalMcpPlugin, github_plugin, jira_plugin, polarion_plugin
from .base import Plugin, PluginContext, ToolSpec
from .norns import NornsPlugin
from .sandbox import SandboxPlugin

ENTRY_POINT_GROUP = "norns.plugins"


@dataclass
class PluginCatalog:
    plugins: list[Plugin] = field(default_factory=list)
    connectors: list[Connector] = field(default_factory=list)

    def by_name(self) -> dict[str, Plugin]:
        return {plugin.name: plugin for plugin in self.plugins}

    def selected(self, allowlist: list[str]) -> list[Plugin]:
        if not allowlist:
            return []
        wanted = {name.strip().lower() for name in allowlist if name and name.strip()}
        include_all_mcp = "mcp" in wanted
        selected: list[Plugin] = []
        for plugin in self.plugins:
            name = plugin.name.lower()
            if name in wanted or (include_all_mcp and isinstance(plugin, ExternalMcpPlugin)):
                selected.append(plugin)
        return selected

    def tools(self, allowlist: list[str], context: PluginContext) -> list[ToolSpec]:
        tools: list[ToolSpec] = []
        for plugin in self.selected(allowlist):
            if isinstance(plugin, ExternalMcpPlugin):
                continue
            tools.extend(plugin.tools(context))
        return tools

    def summaries(self, connectors: list[Connector]) -> list[dict[str, Any]]:
        return [
            {
                "name": plugin.name,
                "title": plugin.title,
                "description": plugin.description,
                "builtin": plugin.builtin,
                "requires_connector": plugin.requires_connector,
                "available": plugin.available(connectors),
            }
            for plugin in self.plugins
        ]


def builtin_plugins() -> list[Plugin]:
    return [NornsPlugin(), SandboxPlugin(), github_plugin(), jira_plugin(), polarion_plugin()]


def load_entry_point_plugins() -> list[Plugin]:
    loaded: list[Plugin] = []
    try:
        selected = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover - older importlib
        selected = entry_points().get(ENTRY_POINT_GROUP, [])
    for entry in selected:
        try:
            loaded_obj = entry.load()
        except Exception:
            continue
        if isinstance(loaded_obj, Plugin):
            instance = loaded_obj
        elif callable(loaded_obj):
            instance = loaded_obj()
        else:
            continue
        if isinstance(instance, Plugin):
            loaded.append(instance)
    return loaded


def load_plugin_catalog(connectors: list[Connector] | None = None) -> PluginCatalog:
    plugins: list[Plugin] = []
    seen: set[str] = set()
    for plugin in [*builtin_plugins(), *load_entry_point_plugins()]:
        if plugin.name in seen:
            continue
        seen.add(plugin.name)
        plugins.append(plugin)
    for connector in connectors or []:
        if connector.connector_type != ConnectorType.MCP or not connector.is_active:
            continue
        extra = ExternalMcpPlugin(connector)
        if extra.name not in seen:
            seen.add(extra.name)
            plugins.append(extra)
    return PluginCatalog(plugins=plugins, connectors=list(connectors or []))


async def load_plugin_catalog_from_db() -> PluginCatalog:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))
        connectors = list(result.scalars().all())
    return load_plugin_catalog(connectors)


def cursor_mcp_servers(
    allowlist: list[str],
    connectors: list[Connector],
    *,
    extra_env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    confirm_writes: bool = False,
) -> dict[str, Any]:
    """Cursor SDK mcp_servers mapping for the stage allowlist."""
    catalog = load_plugin_catalog(connectors)
    selected = catalog.selected(allowlist)
    servers: dict[str, Any] = {}
    builtin_names = [plugin.name for plugin in selected if plugin.builtin or not isinstance(plugin, ExternalMcpPlugin)]
    if builtin_names:
        servers["norns"] = _stdio_norns_mcp(builtin_names, extra_env=extra_env, cwd=cwd, confirm_writes=confirm_writes)
    if confirm_writes:
        return servers
    for plugin in selected:
        if not isinstance(plugin, ExternalMcpPlugin):
            continue
        launch = plugin.mcp_launch()
        if launch.get("url"):
            servers[plugin.name] = {"url": launch["url"], "type": launch.get("type") or "http"}
        elif launch.get("command"):
            servers[plugin.name] = {
                "command": launch["command"],
                "args": launch.get("args") or [],
                "env": _stdio_env(launch.get("env"), extra_env, inherit_norns=False),
                "cwd": cwd or None,
            }
    return servers


def _stdio_norns_mcp(
    plugin_names: list[str],
    *,
    extra_env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    confirm_writes: bool = False,
) -> dict[str, Any]:
    args = ["-m", "norns.mcp", "--plugins", ",".join(plugin_names)]
    run_id = str((extra_env or {}).get("NORNS_RUN_ID") or "").strip()
    if confirm_writes:
        args.append("--confirm-writes")
        if run_id:
            args.extend(["--run-id", run_id])
    payload: dict[str, Any] = {
        "command": sys.executable,
        "args": args,
        "env": _stdio_env(None, extra_env, inherit_norns=True),
    }
    if confirm_writes:
        payload["env"]["NORNS_CONFIRM_WRITES"] = "1"
    if cwd:
        payload["cwd"] = cwd
    return payload


_NORNS_MCP_ENV_KEYS = frozenset(
    {
        "DATABASE_URL",
        "ENCRYPTION_KEY",
        "SECRET_KEY",
        "NORNS_HOME",
        "NORNS_ENV",
        "QUEUE_BACKEND",
        "SESSION_COOKIE_SECURE",
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONNOUSERSITE",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "TMPDIR",
        "TEMP",
        "TMP",
    }
)

_EXTERNAL_MCP_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "VIRTUAL_ENV",
        "TMPDIR",
        "TEMP",
        "TMP",
        "NPM_CONFIG_CACHE",
        "npm_config_cache",
    }
)


def _filtered_process_env(allowed: frozenset[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if value is None:
            continue
        if key in allowed or key.startswith("NORNS_"):
            env[key] = value
    return env


def _stdio_env(
    launch_env: Mapping[str, Any] | None,
    extra_env: Mapping[str, str] | None,
    *,
    inherit_norns: bool,
) -> dict[str, str]:
    env = _filtered_process_env(_NORNS_MCP_ENV_KEYS if inherit_norns else _EXTERNAL_MCP_ENV_KEYS)
    if launch_env:
        env.update({str(key): str(value) for key, value in launch_env.items() if value is not None})
    if extra_env:
        env.update({str(key): str(value) for key, value in extra_env.items() if value is not None})
    return env


def dump_mcp_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, default=str)
