from __future__ import annotations

import asyncio
import re
from typing import Any

from ..models.connector import Connector, ConnectorType
from .registry import RuntimeTool

try:
    from polarion.polarion import Polarion as PolarionClient
except Exception:  # pragma: no cover - optional dependency
    PolarionClient = None


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

DEFAULT_REQUIREMENT_QUERY = "type:requirement"
SEARCH_FIELDS = ["id", "title", "type", "status", "description"]


def assert_writable_field(field: str) -> str:
    if field not in WRITABLE_FIELDS:
        raise ValueError(f"Polarion field {field!r} is not writable")
    return field


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "default"


def _enum_id(value: Any) -> Any:
    if value is None:
        return None
    return getattr(value, "id", None) or getattr(value, "name", None) or value


def workitem_payload(workitem: Any) -> dict[str, Any]:
    description = None
    getter = getattr(workitem, "getDescription", None)
    if callable(getter):
        try:
            description = getter()
        except Exception:
            description = None
    if description is None:
        raw = getattr(workitem, "description", None)
        description = getattr(raw, "content", raw)
    return {
        "id": getattr(workitem, "id", None),
        "title": getattr(workitem, "title", None),
        "type": _enum_id(getattr(workitem, "type", None)),
        "status": _enum_id(getattr(workitem, "status", None)),
        "description": description,
    }


def polarion_provider(connectors: list[Connector]) -> list[RuntimeTool]:
    runtime_tools: list[RuntimeTool] = []
    for connector in connectors:
        if connector.connector_type != ConnectorType.POLARION or not connector.is_active:
            continue
        suffix = _slugify(connector.name)
        runtime_tools.extend(
            [
                RuntimeTool(
                    name=f"polarion_{suffix}_search_workitems",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"polarion_{suffix}_search_workitems",
                            "description": (
                                "Search Polarion work items in the connector project. "
                                "Empty query lists requirements (type:requirement). "
                                "Then create a Norns card with norns_create_card using title, body=description, external_id=id, "
                                "or create a missing Polarion item with polarion create_workitem."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Polarion Lucene query, e.g. type:requirement AND status:draft",
                                    },
                                    "limit": {"type": "integer", "description": "Max results, default 50"},
                                },
                            },
                        },
                    },
                    execute=_make_search_workitems(connector),
                ),
                RuntimeTool(
                    name=f"polarion_{suffix}_get_workitem",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"polarion_{suffix}_get_workitem",
                            "description": "Get a Polarion work item by id, including description.",
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
                    name=f"polarion_{suffix}_create_workitem",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"polarion_{suffix}_create_workitem",
                            "description": (
                                "Create a Polarion work item in the connector project. "
                                "Use type softwarerequirement or systemrequirement. "
                                "Optional parent_id links the new item to a heading such as 5E96-147."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "description": "Polarion type id, default softwarerequirement",
                                    },
                                    "parent_id": {
                                        "type": "string",
                                        "description": "Existing Polarion id to link, e.g. 5E96-147",
                                    },
                                    "link_role": {
                                        "type": "string",
                                        "description": "Link role when parent_id is set, default relates_to",
                                    },
                                },
                                "required": ["title"],
                            },
                        },
                    },
                    execute=_make_create_workitem(connector),
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


def _connector_project(connector: Connector) -> str:
    if not connector.encrypted_config:
        return ""
    try:
        return str(connector.get_config().get("project") or "").strip()
    except Exception:
        return ""


def _polarion_client(connector: Connector) -> Any:
    if PolarionClient is None:
        raise RuntimeError("polarion is not installed")
    config = connector.get_config()
    server = str(config.get("server") or "").strip()
    if not server:
        raise ValueError("Set Server on the Polarion connector in Settings.")
    username = str(config.get("username") or "").strip()
    password = config.get("password") or None
    token = config.get("token") or None
    if not password and not token:
        raise ValueError("Set a Polarion password or token on the connector in Settings.")
    return PolarionClient(
        server,
        username,
        password,
        token=token,
    )


def _polarion_project(connector: Connector) -> Any:
    project_id = _connector_project(connector)
    if not project_id:
        raise ValueError("Set Project on the Polarion connector in Settings.")
    return _polarion_client(connector).getProject(project_id)


def _make_search_workitems(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            query = str(arguments.get("query") or DEFAULT_REQUIREMENT_QUERY).strip() or DEFAULT_REQUIREMENT_QUERY
            try:
                limit = int(arguments.get("limit") or 50)
            except (TypeError, ValueError):
                limit = 50
            limit = max(1, min(limit, 200))
            project = _polarion_project(connector)
            items = project.searchWorkitem(query, field_list=list(SEARCH_FIELDS), limit=limit)
            return {"query": query, "items": [workitem_payload(item) for item in items or []]}

        try:
            return await asyncio.to_thread(_call)
        except Exception as exc:
            return {"error": str(exc).split("response headers")[0].strip() or exc.__class__.__name__}

    return execute


def _make_get_workitem(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            workitem = _polarion_project(connector).getWorkitem(arguments["workitem_id"])
            return workitem_payload(workitem)

        try:
            return await asyncio.to_thread(_call)
        except Exception as exc:
            return {"error": str(exc).split("response headers")[0].strip() or exc.__class__.__name__}

    return execute


def _make_create_workitem(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            title = str(arguments.get("title") or "").strip()
            if not title:
                raise ValueError("title is required")
            workitem_type = str(arguments.get("type") or "softwarerequirement").strip() or "softwarerequirement"
            description = str(arguments.get("description") or "").strip()
            parent_id = str(arguments.get("parent_id") or "").strip()
            link_role = str(arguments.get("link_role") or "relates_to").strip() or "relates_to"
            project = _polarion_project(connector)
            workitem = project.createWorkitem(workitem_type, new_workitem_fields={"title": title})
            if description and hasattr(workitem, "setDescription"):
                workitem.setDescription(description)
            if parent_id:
                parent = project.getWorkitem(parent_id)
                workitem.addLinkedItem(parent, link_role)
            payload = workitem_payload(workitem)
            if parent_id:
                payload["parent_id"] = parent_id
                payload["link_role"] = link_role
            return payload

        try:
            return await asyncio.to_thread(_call)
        except Exception as exc:
            return {"error": str(exc).split("response headers")[0].strip() or exc.__class__.__name__}

    return execute


def _make_add_comment(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            workitem = _polarion_project(connector).getWorkitem(arguments["workitem_id"])
            workitem.addComment("Norns", arguments["comment"])
            return {"id": arguments["workitem_id"], "comment_added": True}

        try:
            return await asyncio.to_thread(_call)
        except Exception as exc:
            return {"error": str(exc).split("response headers")[0].strip() or exc.__class__.__name__}

    return execute


def _make_update_field(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            field = assert_writable_field(arguments["field"])
            workitem = _polarion_project(connector).getWorkitem(arguments["workitem_id"])
            if field == "description" and hasattr(workitem, "setDescription"):
                workitem.setDescription(arguments["value"])
            else:
                setattr(workitem, field, arguments["value"])
                workitem.update()
            return {"id": arguments["workitem_id"], "field": field, "updated": True}

        try:
            return await asyncio.to_thread(_call)
        except Exception as exc:
            return {"error": str(exc).split("response headers")[0].strip() or exc.__class__.__name__}

    return execute


def _make_follow_links(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> list[dict[str, Any]] | dict[str, str]:
            workitem = _polarion_project(connector).getWorkitem(arguments["workitem_id"])
            linked = workitem.getLinkedItem() if hasattr(workitem, "getLinkedItem") else []
            return [workitem_payload(item) for item in linked or []]

        try:
            return await asyncio.to_thread(_call)
        except Exception as exc:
            return {"error": str(exc).split("response headers")[0].strip() or exc.__class__.__name__}

    return execute
