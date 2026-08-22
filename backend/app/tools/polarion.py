from __future__ import annotations

import asyncio
import re
from typing import Any

from ..models.connector import Connector, ConnectorType
from .registry import RuntimeTool

try:
    import polarion as polarion_module
except Exception:  # pragma: no cover - optional dependency
    polarion_module = None


WRITABLE_FIELDS = frozenset(
    {
        "title",
        "description",
        "status",
        "severity",
        "priority",
        "assignee",
        "resolution",
    }
)


def assert_writable_field(field: str) -> str:
    if field not in WRITABLE_FIELDS:
        raise ValueError(f"Polarion field {field!r} is not writable")
    return field


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "default"


def polarion_provider(connectors: list[Connector]) -> list[RuntimeTool]:
    runtime_tools: list[RuntimeTool] = []
    for connector in connectors:
        if connector.connector_type != ConnectorType.POLARION or not connector.is_active:
            continue
        suffix = _slugify(connector.name)
        runtime_tools.extend(
            [
                RuntimeTool(
                    name=f"polarion_{suffix}_get_workitem",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"polarion_{suffix}_get_workitem",
                            "description": "Get a Polarion work item.",
                            "parameters": {
                                "type": "object",
                                "properties": {"workitem_id": {"type": "string"}},
                                "required": ["workitem_id"],
                            },
                        },
                    },
                    execute=_make_get_workitem(connector),
                ),
                RuntimeTool(
                    name=f"polarion_{suffix}_add_comment",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"polarion_{suffix}_add_comment",
                            "description": "Add a comment to a Polarion work item.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "workitem_id": {"type": "string"},
                                    "comment": {"type": "string"},
                                },
                                "required": ["workitem_id", "comment"],
                            },
                        },
                    },
                    execute=_make_add_comment(connector),
                ),
                RuntimeTool(
                    name=f"polarion_{suffix}_update_field",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"polarion_{suffix}_update_field",
                            "description": "Update a Polarion field.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "workitem_id": {"type": "string"},
                                    "field": {"type": "string"},
                                    "value": {},
                                },
                                "required": ["workitem_id", "field", "value"],
                            },
                        },
                    },
                    execute=_make_update_field(connector),
                ),
                RuntimeTool(
                    name=f"polarion_{suffix}_follow_links",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"polarion_{suffix}_follow_links",
                            "description": "Follow linked Polarion work items.",
                            "parameters": {
                                "type": "object",
                                "properties": {"workitem_id": {"type": "string"}},
                                "required": ["workitem_id"],
                            },
                        },
                    },
                    execute=_make_follow_links(connector),
                ),
            ]
        )
    return runtime_tools


def _polarion_client(connector: Connector) -> Any:
    if polarion_module is None:
        raise RuntimeError("polarion is not installed")
    config = connector.get_config()
    client_class = getattr(polarion_module, "Polarion", None)
    if client_class is None:
        raise RuntimeError("Installed polarion package does not expose a Polarion client")
    return client_class(config["server"], config["username"], config["password"], project=config.get("project"))


def _make_get_workitem(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            workitem = _polarion_client(connector).getWorkitem(arguments["workitem_id"])
            return {"id": workitem.id, "title": getattr(workitem, "title", None), "status": getattr(workitem, "status", None)}

        return await asyncio.to_thread(_call)

    return execute


def _make_add_comment(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            workitem = _polarion_client(connector).getWorkitem(arguments["workitem_id"])
            workitem.addComment(arguments["comment"])
            return {"id": arguments["workitem_id"], "comment_added": True}

        return await asyncio.to_thread(_call)

    return execute


def _make_update_field(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            field = assert_writable_field(arguments["field"])
            workitem = _polarion_client(connector).getWorkitem(arguments["workitem_id"])
            setattr(workitem, field, arguments["value"])
            workitem.update()
            return {"id": arguments["workitem_id"], "field": field, "updated": True}

        return await asyncio.to_thread(_call)

    return execute


def _make_follow_links(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> list[dict[str, Any]]:
            workitem = _polarion_client(connector).getWorkitem(arguments["workitem_id"])
            linked = getattr(workitem, "linkedWorkItems", [])
            return [{"id": getattr(item, "id", None), "title": getattr(item, "title", None)} for item in linked]

        return await asyncio.to_thread(_call)

    return execute
