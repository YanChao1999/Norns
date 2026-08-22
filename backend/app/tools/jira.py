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


def jira_provider(connectors: list[Connector]) -> list[RuntimeTool]:
    runtime_tools: list[RuntimeTool] = []
    for connector in connectors:
        if connector.connector_type != ConnectorType.JIRA or not connector.is_active:
            continue
        suffix = _slugify(connector.name)
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
                            "description": "Search Jira issues via JQL.",
                            "parameters": {
                                "type": "object",
                                "properties": {"jql": {"type": "string"}},
                                "required": ["jql"],
                            },
                        },
                    },
                    execute=_make_search_issues(connector),
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
                                "required": ["project", "parent", "summary"],
                            },
                        },
                    },
                    execute=_make_create_subtask(connector),
                ),
            ]
        )
    return runtime_tools


def _jira_client(connector: Connector) -> Any:
    if JIRA is None:
        raise RuntimeError("jira is not installed")
    config = connector.get_config()
    return JIRA(server=config["server"], basic_auth=(config["username"], config["token"]))


def _make_get_issue(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            issue = _jira_client(connector).issue(arguments["key"])
            return {"key": issue.key, "summary": issue.fields.summary, "status": issue.fields.status.name}

        return await asyncio.to_thread(_call)

    return execute


def _make_search_issues(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> list[dict[str, Any]]:
            issues = _jira_client(connector).search_issues(arguments["jql"])
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


def _make_create_subtask(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            issue = _jira_client(connector).create_issue(
                project=arguments["project"],
                parent={"key": arguments["parent"]},
                summary=arguments["summary"],
                description=arguments.get("description", ""),
                issuetype={"name": "Sub-task"},
            )
            return {"key": issue.key}

        return await asyncio.to_thread(_call)

    return execute
