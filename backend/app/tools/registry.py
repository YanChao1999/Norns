from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..models.connector import Connector


ToolExecutor = Callable[[dict[str, Any]], Awaitable[Any]]
ToolProvider = Callable[[list[Connector]], list["RuntimeTool"]]


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

    def get_runtime_tools(self, allowlist: list[str], connectors: list[Connector]) -> list[RuntimeTool]:
        if not allowlist:
            return []
        selected: list[RuntimeTool] = []
        normalized_allowlist = set(allowlist)
        for provider_name, provider in self._providers.items():
            if provider_name not in normalized_allowlist:
                continue
            selected.extend(provider(connectors))
        return selected

    def get_tools_for_allowlist(self, allowlist: list[str], connectors: list[Connector]) -> list[dict[str, Any]]:
        return [tool.openai_tool for tool in self.get_runtime_tools(allowlist, connectors)]


def create_default_registry() -> ToolRegistry:
    from .github import github_provider
    from .jira import jira_provider
    from .polarion import polarion_provider

    registry = ToolRegistry()
    registry.register_provider("github", github_provider)
    registry.register_provider("jira", jira_provider)
    registry.register_provider("polarion", polarion_provider)
    return registry
