from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..models.connector import Connector

ToolExecutor = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(slots=True)
class ToolSpec:
    """One callable tool. Shared by OpenAI function-calling and MCP."""

    name: str
    description: str
    input_schema: dict[str, Any]
    execute: ToolExecutor

    def openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }

    def mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema or {"type": "object", "properties": {}},
        }


def apply_run_ids(arguments: dict[str, Any], context: PluginContext | None) -> dict[str, Any]:
    """Fill board/card/stage ids from the MCP/stage run when the model omits them."""
    if context is None:
        return dict(arguments)
    merged = dict(arguments)
    if not str(merged.get("board_id") or "").strip() and context.board_id:
        merged["board_id"] = context.board_id
    if not str(merged.get("card_id") or "").strip() and context.card_id:
        merged["card_id"] = context.card_id
    if not str(merged.get("stage_id") or "").strip() and context.stage_id:
        merged["stage_id"] = context.stage_id
    return merged


@dataclass(slots=True)
class PluginContext:
    connectors: list[Connector] = field(default_factory=list)
    board_id: str | None = None
    card_id: str | None = None
    stage_id: str | None = None
    workspace_path: str = ""
    git_url: str = ""
    github_repo: str = ""


class Plugin:
    """A Norns tool plugin. Built-ins ship with the package; extras register via entry points."""

    name: str = ""
    title: str = ""
    description: str = ""
    builtin: bool = True
    requires_connector: str | None = None

    def tools(self, context: PluginContext) -> list[ToolSpec]:
        raise NotImplementedError

    def available(self, connectors: list[Connector]) -> bool:
        if not self.requires_connector:
            return True
        wanted = self.requires_connector.lower()
        return any(
            connector.is_active and str(connector.connector_type.value).lower() == wanted for connector in connectors
        )
