from __future__ import annotations

from typing import Any

from ..models.connector import Connector, ConnectorType
from ..tools.github import github_provider
from ..tools.jira import jira_provider
from ..tools.polarion import polarion_provider
from ..tools.registry import RuntimeTool
from .base import Plugin, PluginContext, ToolSpec


def runtime_tool_to_spec(tool: RuntimeTool) -> ToolSpec:
    function = (tool.openai_tool or {}).get("function") or {}
    return ToolSpec(
        name=tool.name,
        description=str(function.get("description") or tool.name),
        input_schema=function.get("parameters") or {"type": "object", "properties": {}},
        execute=tool.execute,
    )


class ConnectorToolPlugin(Plugin):
    """Wraps an existing RuntimeTool provider (GitHub / Jira / Polarion)."""

    def __init__(
        self,
        *,
        name: str,
        title: str,
        description: str,
        provider,
        requires_connector: str,
    ) -> None:
        self.name = name
        self.title = title
        self.description = description
        self.requires_connector = requires_connector
        self._provider = provider

    def tools(self, context: PluginContext) -> list[ToolSpec]:
        kwargs: dict[str, Any] = {}
        if self.name == "github":
            repo = context.github_repo or _connector_config_value(context.connectors, ConnectorType.GITHUB, "repo")
            if repo:
                kwargs["default_repo"] = repo
        elif self.name == "jira":
            project = _connector_config_value(context.connectors, ConnectorType.JIRA, "project")
            if project:
                kwargs["default_project"] = project
        return [runtime_tool_to_spec(tool) for tool in self._provider(context.connectors, **kwargs)]


def github_plugin() -> ConnectorToolPlugin:
    return ConnectorToolPlugin(
        name="github",
        title="GitHub",
        description="Read issues, list files, open PRs, comment, and create issues via the GitHub connector.",
        provider=github_provider,
        requires_connector="github",
    )


def jira_plugin() -> ConnectorToolPlugin:
    return ConnectorToolPlugin(
        name="jira",
        title="Jira",
        description="Search, comment, transition, and create Jira issues via the Jira connector.",
        provider=jira_provider,
        requires_connector="jira",
    )


def polarion_plugin() -> ConnectorToolPlugin:
    return ConnectorToolPlugin(
        name="polarion",
        title="Polarion",
        description="Read and update Polarion work items via the Polarion connector.",
        provider=polarion_provider,
        requires_connector="polarion",
    )


class ExternalMcpPlugin(Plugin):
    """Passthrough: an MCP server launched from a Settings connector (stdio or HTTP)."""

    builtin = False

    def __init__(self, connector: Connector) -> None:
        slug = _slugify(connector.name)
        self.name = f"mcp_{slug}"
        self.title = connector.name
        self.description = f"External MCP server ({connector.get_config().get('transport') or 'stdio'})."
        self.requires_connector = None
        self.connector = connector

    def tools(self, context: PluginContext) -> list[ToolSpec]:
        del context
        return []

    def available(self, connectors: list[Connector]) -> bool:
        del connectors
        return self.connector.is_active

    def mcp_launch(self) -> dict[str, Any]:
        config = self.connector.get_config()
        transport = str(config.get("transport") or "stdio").strip().lower()
        if transport == "http":
            return {"url": str(config.get("url") or "").strip(), "type": "http"}
        args = config.get("args") or []
        if isinstance(args, str):
            args = [part for part in args.split() if part]
        env = config.get("env") if isinstance(config.get("env"), dict) else {}
        return {
            "command": str(config.get("command") or "").strip(),
            "args": list(args),
            "env": {str(key): str(value) for key, value in env.items()},
        }


def _connector_config_value(connectors: list[Connector], connector_type: ConnectorType, key: str) -> str:
    for connector in connectors:
        if connector.connector_type != connector_type or not connector.is_active:
            continue
        if not connector.encrypted_config:
            continue
        try:
            value = str(connector.get_config().get(key) or "").strip()
        except Exception:
            continue
        if value:
            return value
    return ""


def _slugify(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "server"
