from __future__ import annotations

import json
from io import StringIO

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import Board, Connector, ConnectorType, Stage
from backend.app.plugins import mcp_protocol
from backend.app.plugins.base import PluginContext, ToolSpec
from backend.app.plugins.catalog import cursor_mcp_servers, load_plugin_catalog
from backend.app.plugins.norns import NornsPlugin, _create_card
from backend.app.tools.github import github_provider
from backend.app.tools.jira import jira_provider
from backend.app.tools.registry import create_default_registry


def test_catalog_includes_builtin_plugins():
    catalog = load_plugin_catalog([])
    assert {plugin.name for plugin in catalog.plugins} >= {"norns", "github", "jira", "polarion"}
    norns = catalog.by_name()["norns"]
    assert norns.available([]) is True
    assert catalog.by_name()["jira"].available([]) is False


def test_default_registry_includes_norns():
    registry = create_default_registry()
    tools = registry.get_runtime_tools(["norns"], [])
    names = {tool.name for tool in tools}
    assert "norns_create_card" in names
    assert "norns_get_workspace" in names
    assert "norns_set_board_workspace" in names
    assert "norns_update_stage_prompt" in names
    assert "norns_add_transition" in names


def test_empty_allowlist_still_grants_nothing():
    catalog = load_plugin_catalog([])
    assert catalog.tools([], PluginContext()) == []
    assert cursor_mcp_servers([], []) == {}


def test_github_plugin_includes_create_issue():
    connector = Connector(name="Work GH", connector_type=ConnectorType.GITHUB, encrypted_config=b"", is_active=True)
    names = {tool.name for tool in github_provider([connector])}
    assert "github_work_gh_create_issue" in names


def test_jira_plugin_includes_create_issue():
    connector = Connector(name="Cloud Jira", connector_type=ConnectorType.JIRA, encrypted_config=b"", is_active=True)
    names = {tool.name for tool in jira_provider([connector])}
    assert "jira_cloud_jira_create_issue" in names


def test_cursor_mcp_servers_stdio_for_allowlist():
    servers = cursor_mcp_servers(["norns", "jira"], [])
    assert "norns" in servers
    assert servers["norns"]["args"][-1] == "norns,jira"
    assert "-m" in servers["norns"]["args"]


def test_external_mcp_connector_is_passthrough():
    connector = Connector(name="Linear", connector_type=ConnectorType.MCP, encrypted_config=b"", is_active=True)
    connector.set_config({"transport": "stdio", "command": "npx", "args": "-y linear-mcp"})
    catalog = load_plugin_catalog([connector])
    assert "mcp_linear" in catalog.by_name()
    servers = cursor_mcp_servers(["mcp"], [connector])
    assert servers["mcp_linear"]["command"] == "npx"


@pytest.mark.asyncio
async def test_mcp_protocol_lists_and_calls_tools(monkeypatch):
    async def ping(arguments: dict) -> dict:
        return {"pong": arguments.get("value")}

    tool = ToolSpec(
        name="ping",
        description="Ping",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        execute=ping,
    )

    class Catalog:
        def tools(self, names, context):
            del names, context
            return [tool]

    async def fake_catalog():
        return Catalog()

    monkeypatch.setattr(mcp_protocol, "load_plugin_catalog_from_db", fake_catalog)
    stdout = StringIO()
    stdin = StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "ping", "arguments": {"value": "hi"}},
            }
        )
        + "\n"
    )
    await mcp_protocol.serve_stdio(["norns"], stdin=stdin, stdout=stdout)
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines[0]["result"]["serverInfo"]["name"] == "norns"
    assert lines[1]["result"]["tools"][0]["name"] == "ping"
    assert "hi" in lines[2]["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_norns_create_card(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        board = Board(name="Board")
        board.stages = [Stage(name="Urd", order=1, require_approval=True)]
        session.add(board)
        await session.commit()
        board_id = board.id

    monkeypatch.setattr("backend.app.plugins.norns.AsyncSessionLocal", SessionLocal)
    created = await _create_card({"board_id": board_id, "title": "New work", "body": "from MCP"})
    assert created["title"] == "New work"
    assert created["current_stage_id"]
    tools = {spec.name for spec in NornsPlugin().tools(PluginContext())}
    assert "norns_update_stage_prompt" in tools
    await engine.dispose()
