from __future__ import annotations

import asyncio
import re
from typing import Any

from ..models.connector import Connector, ConnectorType
from .registry import RuntimeTool

try:
    from jira import JIRA
except Exception:  # pragma: no cover - optional dependency
    JIRA = None


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "default"


def _project_value(arguments: dict[str, Any], default_project: str) -> str:
    project = str(arguments.get("project") or default_project or "").strip()
    if not project:
        raise ValueError("project is required — set it on the Jira connector or pass a project key")
    return project


def _required_project(default_project: str, names: list[str]) -> list[str]:
    if default_project:
        return [name for name in names if name != "project"]
    return names


def jira_provider(connectors: list[Connector], default_project: str = "") -> list[RuntimeTool]:
    runtime_tools: list[RuntimeTool] = []
    for connector in connectors:
        if connector.connector_type != ConnectorType.JIRA or not connector.is_active:
            continue
        suffix = _slugify(connector.name)
        project = default_project or _connector_project(connector)
        runtime_tools.extend(
            [
                RuntimeTool(
                    name=f"jira_{suffix}_get_issue",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"jira_{suffix}_get_issue",
                            "description": "Retrieve a Jira issue.",
                            "parameters": {
                                "type": "object",
                                "properties": {"key": {"type": "string"}},
                                "required": ["key"],
                            },
                        },
                    },
                    execute=_make_get_issue(connector),
                ),
                RuntimeTool(
                    name=f"jira_{suffix}_search_issues",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"jira_{suffix}_search_issues",
                            "description": "Search Jira issues via JQL. Jira Cloud requires a restriction such as project = KEY or created >= -14d. Do not send ORDER BY alone.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "jql": {
                                        "type": "string",
                                        "description": "JQL with a restriction. Example: project = PROJ AND text ~ 'summary' ORDER BY created DESC",
                                    }
                                },
                                "required": ["jql"],
                            },
                        },
                    },
                    execute=_make_search_issues(connector, project),
                ),
                RuntimeTool(
                    name=f"jira_{suffix}_add_comment",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"jira_{suffix}_add_comment",
                            "description": "Add a Jira issue comment.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string"},
                                    "comment": {"type": "string"},
                                },
                                "required": ["key", "comment"],
                            },
                        },
                    },
                    execute=_make_add_comment(connector),
                ),
                RuntimeTool(
                    name=f"jira_{suffix}_transition_issue",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"jira_{suffix}_transition_issue",
                            "description": "Transition a Jira issue.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string"},
                                    "transition": {"type": "string"},
                                },
                                "required": ["key", "transition"],
                            },
                        },
                    },
                    execute=_make_transition_issue(connector),
                ),
                RuntimeTool(
                    name=f"jira_{suffix}_create_issue",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"jira_{suffix}_create_issue",
                            "description": (
                                "Create a Jira issue only when search finds none for this work. "
                                "If a ticket already tracks the same Polarion id or card, reuse it (comment or subtask). "
                                "Do not create a second top-level issue for the same Polarion section."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "project": {"type": "string", "description": "Jira project key, e.g. PROJ"},
                                    "summary": {"type": "string"},
                                    "description": {"type": "string"},
                                    "issuetype": {"type": "string", "description": "Issue type name, default Task"},
                                },
                                "required": _required_project(project, ["project", "summary"]),
                            },
                        },
                    },
                    execute=_make_create_issue(connector, project),
                ),
                RuntimeTool(
                    name=f"jira_{suffix}_create_subtask",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"jira_{suffix}_create_subtask",
                            "description": "Create a Jira subtask.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "project": {"type": "string"},
                                    "parent": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": _required_project(project, ["project", "parent", "summary"]),
                            },
                        },
                    },
                    execute=_make_create_subtask(connector, project),
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


def _jira_client(connector: Connector) -> Any:
    if JIRA is None:
        raise RuntimeError("jira is not installed")
    config = connector.get_config()
    return JIRA(server=config["server"], basic_auth=(config["username"], config["token"]))


def restrict_jql(jql: str, default_project: str = "") -> str:
    text = str(jql or "").strip()
    body = re.sub(r"(?is)\border\s+by\s+.*$", "", text).strip()
    if body:
        return text
    restriction = f'project = "{default_project}"' if default_project else "created >= -14d"
    order = text if re.search(r"(?i)\border\s+by\b", text) else "ORDER BY created DESC"
    return f"{restriction} {order}".strip()


def _jira_error_payload(exc: BaseException, jql: str = "") -> dict[str, str]:
    text = str(getattr(exc, "text", None) or "").strip() or str(exc).split("response headers")[0].strip()
    status = getattr(exc, "status_code", None)
    prefix = f"Jira HTTP {status}: " if status else "Jira: "
    payload = {"error": f"{prefix}{text}"}
    if jql:
        payload["jql"] = jql
    return payload


def _make_get_issue(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            issue = _jira_client(connector).issue(arguments["key"])
            return {"key": issue.key, "summary": issue.fields.summary, "status": issue.fields.status.name}

        return await asyncio.to_thread(_call)

    return execute


def _make_search_issues(connector: Connector, default_project: str = ""):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> list[dict[str, Any]] | dict[str, str]:
            jql = restrict_jql(str(arguments.get("jql") or ""), default_project or _connector_project(connector))
            try:
                issues = _jira_client(connector).search_issues(jql)
            except Exception as exc:
                return _jira_error_payload(exc, jql)
            return [{"key": issue.key, "summary": issue.fields.summary} for issue in issues]

        return await asyncio.to_thread(_call)

    return execute


def _make_add_comment(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            comment = _jira_client(connector).add_comment(arguments["key"], arguments["comment"])
            return {"id": comment.id, "body": comment.body}

        return await asyncio.to_thread(_call)

    return execute


def _make_transition_issue(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            client = _jira_client(connector)
            client.transition_issue(arguments["key"], arguments["transition"])
            return {"key": arguments["key"], "transition": arguments["transition"]}

        return await asyncio.to_thread(_call)

    return execute


def _make_create_issue(connector: Connector, default_project: str = ""):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            issue = _jira_client(connector).create_issue(
                project=_project_value(arguments, default_project),
                summary=arguments["summary"],
                description=arguments.get("description") or "",
                issuetype={"name": arguments.get("issuetype") or "Task"},
            )
            return {"key": issue.key, "id": getattr(issue, "id", None)}

        return await asyncio.to_thread(_call)

    return execute


def _make_create_subtask(connector: Connector, default_project: str = ""):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            issue = _jira_client(connector).create_issue(
                project=_project_value(arguments, default_project),
                parent={"key": arguments["parent"]},
                summary=arguments["summary"],
                description=arguments.get("description", ""),
                issuetype={"name": "Sub-task"},
            )
            return {"key": issue.key}

        return await asyncio.to_thread(_call)

    return execute
