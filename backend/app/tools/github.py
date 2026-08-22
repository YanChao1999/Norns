from __future__ import annotations

import asyncio
import re
from typing import Any

from ..models.connector import Connector, ConnectorType
from .registry import RuntimeTool

try:
    from github import Github
except Exception:  # pragma: no cover - optional dependency
    Github = None


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "default"


def github_provider(connectors: list[Connector]) -> list[RuntimeTool]:
    runtime_tools: list[RuntimeTool] = []
    for connector in connectors:
        if connector.connector_type != ConnectorType.GITHUB or not connector.is_active:
            continue
        suffix = _slugify(connector.name)
        runtime_tools.extend(
            [
                RuntimeTool(
                    name=f"github_{suffix}_read_issue",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"github_{suffix}_read_issue",
                            "description": "Read a GitHub issue using the configured Python client.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "repo": {"type": "string"},
                                    "issue_number": {"type": "integer"},
                                },
                                "required": ["repo", "issue_number"],
                            },
                        },
                    },
                    execute=_make_issue_reader(connector),
                ),
                RuntimeTool(
                    name=f"github_{suffix}_list_files",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"github_{suffix}_list_files",
                            "description": "List files from a GitHub repository reference.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "repo": {"type": "string"},
                                    "path": {"type": "string", "default": ""},
                                    "ref": {"type": "string"},
                                },
                                "required": ["repo"],
                            },
                        },
                    },
                    execute=_make_file_lister(connector),
                ),
                RuntimeTool(
                    name=f"github_{suffix}_open_pr",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"github_{suffix}_open_pr",
                            "description": "Open a pull request in GitHub.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "repo": {"type": "string"},
                                    "title": {"type": "string"},
                                    "body": {"type": "string"},
                                    "head": {"type": "string"},
                                    "base": {"type": "string"},
                                },
                                "required": ["repo", "title", "body", "head", "base"],
                            },
                        },
                    },
                    execute=_make_pr_creator(connector),
                ),
                RuntimeTool(
                    name=f"github_{suffix}_comment_pr",
                    openai_tool={
                        "type": "function",
                        "function": {
                            "name": f"github_{suffix}_comment_pr",
                            "description": "Comment on a GitHub pull request.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "repo": {"type": "string"},
                                    "pull_number": {"type": "integer"},
                                    "body": {"type": "string"},
                                },
                                "required": ["repo", "pull_number", "body"],
                            },
                        },
                    },
                    execute=_make_pr_commenter(connector),
                ),
            ]
        )
    return runtime_tools


def _github_client(connector: Connector) -> Any:
    if Github is None:
        raise RuntimeError("PyGithub is not installed")
    config = connector.get_config()
    token = config.get("token")
    base_url = config.get("base_url")
    if base_url:
        return Github(base_url=base_url, login_or_token=token)
    return Github(login_or_token=token)


def _make_issue_reader(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            client = _github_client(connector)
            issue = client.get_repo(arguments["repo"]).get_issue(int(arguments["issue_number"]))
            return {"title": issue.title, "body": issue.body, "state": issue.state, "html_url": issue.html_url}

        return await asyncio.to_thread(_call)

    return execute


def _make_file_lister(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> list[dict[str, Any]]:
            client = _github_client(connector)
            repo = client.get_repo(arguments["repo"])
            contents = repo.get_contents(arguments.get("path") or "", ref=arguments.get("ref"))
            if not isinstance(contents, list):
                contents = [contents]
            return [{"path": item.path, "type": item.type, "size": item.size} for item in contents]

        return await asyncio.to_thread(_call)

    return execute


def _make_pr_creator(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            client = _github_client(connector)
            pr = client.get_repo(arguments["repo"]).create_pull(
                title=arguments["title"],
                body=arguments["body"],
                head=arguments["head"],
                base=arguments["base"],
            )
            return {"number": pr.number, "html_url": pr.html_url}

        return await asyncio.to_thread(_call)

    return execute


def _make_pr_commenter(connector: Connector):
    async def execute(arguments: dict[str, Any]) -> Any:
        def _call() -> dict[str, Any]:
            client = _github_client(connector)
            issue = client.get_repo(arguments["repo"]).get_issue(int(arguments["pull_number"]))
            comment = issue.create_comment(arguments["body"])
            return {"id": comment.id, "html_url": comment.html_url}

        return await asyncio.to_thread(_call)

    return execute
