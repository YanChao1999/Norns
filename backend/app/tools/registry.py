from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..models.connector import Connector
from ..plugins.base import PluginContext

ToolExecutor = Callable[[dict[str, Any]], Awaitable[Any]]
ToolProvider = Callable[..., list["RuntimeTool"]]


@dataclass(slots=True)
class RuntimeTool:
    name: str
    openai_tool: dict[str, Any]
    execute: ToolExecutor


class ToolRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ToolProvider] = {}

    def register_provider(self, name: str, provider: ToolProvider) -> None:
        self._providers[name] = provider

    def get_runtime_tools(
        self,
        allowlist: list[str],
        connectors: list[Connector],
        context: PluginContext | None = None,
    ) -> list[RuntimeTool]:
        if not allowlist:
            return []
        selected: list[RuntimeTool] = []
        normalized_allowlist = set(allowlist)
        plugin_context = context or PluginContext(connectors=connectors)
        if not plugin_context.connectors:
            plugin_context.connectors = connectors
        for provider_name, provider in self._providers.items():
            if provider_name not in normalized_allowlist:
                continue
            selected.extend(_call_provider(provider, connectors, plugin_context))
        return selected

    def get_tools_for_allowlist(self, allowlist: list[str], connectors: list[Connector]) -> list[dict[str, Any]]:
        return [tool.openai_tool for tool in self.get_runtime_tools(allowlist, connectors)]


def _call_provider(provider: ToolProvider, connectors: list[Connector], context: PluginContext) -> list[RuntimeTool]:
    try:
        return provider(connectors, context)
    except TypeError:
        return provider(connectors)


def create_default_registry() -> ToolRegistry:
    from ..plugins.catalog import builtin_plugins

    registry = ToolRegistry()
    for plugin in builtin_plugins():
        registry.register_provider(plugin.name, _plugin_provider(plugin))
    return registry


def _plugin_provider(plugin):
    def provider(connectors: list[Connector], context: PluginContext | None = None) -> list[RuntimeTool]:
        from ..workspace import resolve_workspace

        ctx = context or PluginContext(connectors=connectors)
        if not ctx.workspace_path and not ctx.git_url:
            workspace = resolve_workspace(connectors)
            ctx = PluginContext(
                connectors=ctx.connectors or connectors,
                board_id=ctx.board_id,
                card_id=ctx.card_id,
                stage_id=ctx.stage_id,
                workspace_path=workspace.path,
                git_url=workspace.git_url,
                github_repo=workspace.github_repo,
            )
        specs = plugin.tools(ctx)
        return [RuntimeTool(name=spec.name, openai_tool=spec.openai_tool(), execute=spec.execute) for spec in specs]

    return provider
