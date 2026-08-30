from __future__ import annotations

import json
from io import StringIO

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import AgentRun, Board, Card, Connector, ConnectorType, Stage
from backend.app.orchestrator.state_machine import CardStatus
from backend.app.plugins import mcp_protocol
from backend.app.plugins.base import PluginContext, ToolSpec
from backend.app.plugins.catalog import cursor_mcp_servers, load_plugin_catalog
from backend.app.plugins.norns import NornsPlugin, _create_card
from backend.app.tools.github import github_provider
from backend.app.tools.jira import jira_provider, restrict_jql
from backend.app.tools.registry import create_default_registry


def test_catalog_includes_builtin_plugins():
    catalog = load_plugin_catalog([])
    assert {plugin.name for plugin in catalog.plugins} >= {"norns", "github", "jira", "polarion"}
    norns = catalog.by_name()["norns"]
    assert norns.available([]) is True
    assert catalog.by_name()["jira"].available([]) is False
    norns_names = {spec.name for spec in catalog.tools(["norns"], PluginContext())}
    assert "norns_create_card" in norns_names
    assert "norns_get_workspace" in norns_names
    assert "norns_update_card" in norns_names


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


def test_github_and_polarion_tools_require_connectors_on_plugin_context():
    github = Connector(name="Work GH", connector_type=ConnectorType.GITHUB, encrypted_config=b"", is_active=True)
    polarion = Connector(name="Polarion", connector_type=ConnectorType.POLARION, encrypted_config=b"", is_active=True)
    catalog = load_plugin_catalog([github, polarion])
    assert catalog.tools(["github"], PluginContext()) == []
    assert catalog.tools(["polarion"], PluginContext()) == []
    github_names = {spec.name for spec in catalog.tools(["github"], PluginContext(connectors=[github]))}
    polarion_names = {spec.name for spec in catalog.tools(["polarion"], PluginContext(connectors=[polarion]))}
    assert "github_work_gh_create_issue" in github_names
    assert "polarion_polarion_get_workitem" in polarion_names
    assert "polarion_polarion_search_workitems" in polarion_names
    assert "polarion_polarion_create_workitem" in polarion_names


def test_github_defaults_repo_from_plugin_context():
    connector = Connector(name="Work GH", connector_type=ConnectorType.GITHUB, encrypted_config=b"", is_active=True)
    catalog = load_plugin_catalog([connector])
    spec = next(
        item
        for item in catalog.tools(["github"], PluginContext(connectors=[connector], github_repo="acme/app"))
        if item.name == "github_work_gh_create_issue"
    )
    assert "repo" not in spec.input_schema["required"]
    assert "title" in spec.input_schema["required"]


def test_jira_defaults_project_when_provided():
    connector = Connector(name="Jira", connector_type=ConnectorType.JIRA, encrypted_config=b"", is_active=True)
    tool = next(
        item for item in jira_provider([connector], default_project="PROJ") if item.name.endswith("create_issue")
    )
    assert "project" not in tool.openai_tool["function"]["parameters"]["required"]
    assert "summary" in tool.openai_tool["function"]["parameters"]["required"]


def test_restrict_jql_adds_project_when_query_is_only_order_by():
    assert restrict_jql("ORDER BY created DESC", "NORNS") == 'project = "NORNS" ORDER BY created DESC'
    assert restrict_jql("", "").startswith("created >= -14d")
    assert restrict_jql('project = "NORNS"', "NORNS") == 'project = "NORNS"'


def test_jira_tools_require_connectors_on_plugin_context():
    connector = Connector(name="Jira", connector_type=ConnectorType.JIRA, encrypted_config=b"", is_active=True)
    catalog = load_plugin_catalog([connector])
    assert catalog.tools(["jira"], PluginContext()) == []
    names = {spec.name for spec in catalog.tools(["jira"], PluginContext(connectors=[connector]))}
    assert "jira_jira_create_issue" in names


@pytest.mark.asyncio
async def test_stdio_mcp_passes_connectors_into_plugin_context(monkeypatch):
    connector = Connector(name="Jira", connector_type=ConnectorType.JIRA, encrypted_config=b"", is_active=True)
    seen: dict[str, object] = {}

    class Catalog:
        connectors = [connector]
        plugins = []

        def tools(self, names, context):
            seen["names"] = names
            seen["connectors"] = list(context.connectors)
            seen["board_id"] = context.board_id
            seen["card_id"] = context.card_id
            seen["stage_id"] = context.stage_id
            seen["github_repo"] = context.github_repo
            return []

    async def fake_catalog():
        return Catalog()

    monkeypatch.setattr(mcp_protocol, "load_plugin_catalog_from_db", fake_catalog)
    monkeypatch.setenv("NORNS_BOARD_ID", "board-1")
    monkeypatch.setenv("NORNS_CARD_ID", "card-1")
    monkeypatch.setenv("NORNS_STAGE_ID", "stage-1")
    monkeypatch.setenv("NORNS_GITHUB_REPO", "acme/app")
    stdout = StringIO()
    await mcp_protocol.serve_stdio(["norns", "jira"], stdin=StringIO(""), stdout=stdout)
    assert seen["names"] == ["norns", "jira"]
    assert seen["connectors"] == [connector]
    assert seen["board_id"] == "board-1"
    assert seen["card_id"] == "card-1"
    assert seen["stage_id"] == "stage-1"
    assert seen["github_repo"] == "acme/app"


def test_cursor_mcp_servers_stdio_for_allowlist():
    servers = cursor_mcp_servers(
        ["norns", "jira"],
        [],
        extra_env={"NORNS_CARD_ID": "card-1", "NORNS_BOARD_ID": "board-1"},
    )
    assert "norns" in servers
    assert servers["norns"]["args"][-1] == "norns,jira"
    assert "-m" in servers["norns"]["args"]
    assert servers["norns"]["env"]["NORNS_CARD_ID"] == "card-1"
    assert servers["norns"]["env"]["NORNS_BOARD_ID"] == "board-1"
    assert "--confirm-writes" not in servers["norns"]["args"]


def test_cursor_mcp_passes_confirm_writes_on_argv():
    servers = cursor_mcp_servers(
        ["norns", "jira"],
        [],
        extra_env={"NORNS_CARD_ID": "card-1", "NORNS_RUN_ID": "run-9"},
        confirm_writes=True,
    )
    args = servers["norns"]["args"]
    assert "--confirm-writes" in args
    assert args[args.index("--run-id") + 1] == "run-9"
    assert servers["norns"]["env"]["NORNS_CONFIRM_WRITES"] == "1"
    assert servers["norns"]["env"]["NORNS_RUN_ID"] == "run-9"


def test_mcp_stdio_env_does_not_forward_llm_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-secret")
    servers = cursor_mcp_servers(["norns"], [], extra_env={"NORNS_CARD_ID": "card-1"})
    env = servers["norns"]["env"]
    assert env["NORNS_CARD_ID"] == "card-1"
    assert "OPENAI_API_KEY" not in env
    assert "ADMIN_PASSWORD" not in env
    assert "ENCRYPTION_KEY" in env
    assert "SECRET_KEY" in env


def test_external_mcp_connector_is_passthrough(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    connector = Connector(name="Linear", connector_type=ConnectorType.MCP, encrypted_config=b"", is_active=True)
    connector.set_config({"transport": "stdio", "command": "npx", "args": "-y linear-mcp"})
    catalog = load_plugin_catalog([connector])
    assert "mcp_linear" in catalog.by_name()
    servers = cursor_mcp_servers(
        ["mcp"], [connector], extra_env={"NORNS_CARD_ID": "card-1", "NORNS_WORKSPACE": "/tmp/app"}
    )
    assert servers["mcp_linear"]["command"] == "npx"
    assert servers["mcp_linear"]["env"]["NORNS_CARD_ID"] == "card-1"
    assert servers["mcp_linear"]["env"]["NORNS_WORKSPACE"] == "/tmp/app"
    assert "OPENAI_API_KEY" not in servers["mcp_linear"]["env"]
    assert "ENCRYPTION_KEY" not in servers["mcp_linear"]["env"]
    assert "SECRET_KEY" not in servers["mcp_linear"]["env"]


def test_confirm_writes_skips_external_mcp():
    connector = Connector(name="Linear", connector_type=ConnectorType.MCP, encrypted_config=b"", is_active=True)
    connector.set_config({"transport": "stdio", "command": "npx", "args": "-y linear-mcp"})
    servers = cursor_mcp_servers(
        ["norns", "mcp"],
        [connector],
        extra_env={"NORNS_CARD_ID": "card-1"},
        confirm_writes=True,
    )
    assert "norns" in servers
    assert "mcp_linear" not in servers


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
        connectors = []

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
async def test_mcp_protocol_queues_jira_create_and_card_edit(monkeypatch):
    executed: list[str] = []

    async def create_issue(arguments: dict) -> dict:
        executed.append("jira_create")
        return {"key": "NOR-9"}

    async def update_card(arguments: dict) -> dict:
        executed.append("card_edit")
        return {"title": arguments.get("title")}

    async def get_issue(arguments: dict) -> dict:
        executed.append("jira_get")
        return {"key": arguments.get("key")}

    tools = [
        ToolSpec(
            name="jira_jira_create_issue",
            description="Create",
            input_schema={"type": "object", "properties": {}},
            execute=create_issue,
        ),
        ToolSpec(
            name="norns_update_card",
            description="Edit",
            input_schema={"type": "object", "properties": {}},
            execute=update_card,
        ),
        ToolSpec(
            name="jira_jira_get_issue",
            description="Get",
            input_schema={"type": "object", "properties": {}},
            execute=get_issue,
        ),
    ]

    class Catalog:
        connectors = []

        def tools(self, names, context):
            del names, context
            return tools

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
        stage = Stage(name="Urd", order=1, confirm_writes=True)
        board.stages = [stage]
        card = Card(title="Card", body="", status=CardStatus.RUNNING, current_stage=stage)
        board.cards = [card]
        run = AgentRun(card=card, stage=stage, inputs={}, tool_calls=[], model_output="", status="running")
        session.add_all([board, run])
        await session.commit()
        run_id = run.id

    async def fake_catalog():
        return Catalog()

    monkeypatch.setattr(mcp_protocol, "load_plugin_catalog_from_db", fake_catalog)
    monkeypatch.setattr(mcp_protocol, "AsyncSessionLocal", SessionLocal)
    stdout = StringIO()
    stdin = StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "jira_jira_create_issue", "arguments": {"summary": "Ticket"}},
            }
        )
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "norns_update_card", "arguments": {"title": "Renamed"}},
            }
        )
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "jira_jira_get_issue", "arguments": {"key": "NOR-1"}},
            }
        )
        + "\n"
    )
    await mcp_protocol.serve_stdio(["norns", "jira"], stdin=stdin, stdout=stdout, confirm_writes=True, run_id=run_id)
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert "pending_approval" in lines[0]["result"]["content"][0]["text"]
    assert "pending_approval" in lines[1]["result"]["content"][0]["text"]
    assert "NOR-1" in lines[2]["result"]["content"][0]["text"]
    assert executed == ["jira_get"]
    async with SessionLocal() as session:
        stored = await session.get(AgentRun, run_id)
        pending = list((stored.inputs or {}).get("pending_writes") or [])
    assert [item["name"] for item in pending] == ["jira_jira_create_issue", "norns_update_card"]
    await engine.dispose()


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
    bound = next(
        spec for spec in NornsPlugin().tools(PluginContext(card_id=created["id"])) if spec.name == "norns_update_card"
    )
    updated = await bound.execute({"title": "Renamed by context"})
    assert updated["title"] == "Renamed by context"
    create_tool = next(
        spec for spec in NornsPlugin().tools(PluginContext(board_id=board_id)) if spec.name == "norns_create_card"
    )
    assert "board_id" not in create_tool.input_schema["required"]
    from_context = await create_tool.execute({"title": "From Polarion", "body": "req text", "external_id": "PROJ-12"})
    assert from_context["title"] == "From Polarion"
    assert from_context["external_id"] == "PROJ-12"
    reused = await create_tool.execute(
        {"title": "Duplicate Polarion card", "body": "should not insert", "external_id": "PROJ-12"}
    )
    assert reused["reused"] is True
    assert reused["id"] == from_context["id"]
    assert reused["title"] == "From Polarion"
    await engine.dispose()
