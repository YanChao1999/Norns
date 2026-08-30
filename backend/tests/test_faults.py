from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.agents.runner import _run_openai_tool_loop, _run_stage
from backend.app.database import Base
from backend.app.faults import ENV, LOOP_TOOL_ERROR, MCP_ERROR, RUNNER_TIMEOUT
from backend.app.models import AgentConfig, AgentRun, Board, Card, Stage
from backend.app.orchestrator.state_machine import CardStatus
from backend.app.plugins import mcp_protocol
from backend.app.plugins.base import ToolSpec
from backend.app.tools.registry import RuntimeTool


async def _session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, SessionLocal


@pytest.mark.asyncio
async def test_inject_runner_timeout_via_run_stage(monkeypatch):
    engine, SessionLocal = await _session_factory()
    monkeypatch.setenv(ENV, RUNNER_TIMEOUT)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = Stage(name="Urd", order=1, require_approval=True)
        stage.agent_config = AgentConfig(system_prompt="Urd", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        board.stages = [stage]
        card = Card(title="Work", body="test inject", status=CardStatus.IDLE, current_stage=stage)
        board.cards = [card]
        session.add(board)
        await session.commit()

        await _run_stage(session, card.id, stage.id, "run-inject")
        await session.refresh(card)
        run = (await session.execute(select(AgentRun).where(AgentRun.id == "run-inject"))).scalar_one()
        assert card.status == CardStatus.IDLE
        assert run.status == "failed"
        assert "timed out" in (run.model_output or "").lower()
    await engine.dispose()


@pytest.mark.asyncio
async def test_inject_loop_tool_error_skips_execute(monkeypatch):
    monkeypatch.setenv(ENV, LOOP_TOOL_ERROR)
    search_call = SimpleNamespace(
        id="call-search",
        function=SimpleNamespace(name="jira_search", arguments='{"jql": "project = X"}'),
    )

    class FakeMessage:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

        def model_dump(self, exclude_none=True):
            del exclude_none
            return {"role": "assistant", "content": self.content}

    script = [
        SimpleNamespace(choices=[SimpleNamespace(message=FakeMessage(tool_calls=[search_call]))]),
        SimpleNamespace(choices=[SimpleNamespace(message=FakeMessage(content="Tool error noted."))]),
    ]

    class FakeCompletions:
        async def create(self, **kwargs):
            del kwargs
            return script.pop(0)

    async def search(arguments: dict) -> list:
        del arguments
        raise AssertionError("tool should not execute when loop_tool_error is injected")

    content, executed = await _run_openai_tool_loop(
        SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
        model="gpt-4o",
        temperature=0.1,
        messages=[{"role": "user", "content": "search"}],
        tools_payload=[{"type": "function", "function": {"name": "jira_search"}}],
        tool_map={"jira_search": RuntimeTool(name="jira_search", openai_tool={}, execute=search)},
    )
    assert executed[0]["result"]["error"].startswith("injected:")
    assert "noted" in content.lower()


@pytest.mark.asyncio
async def test_inject_mcp_error_on_tools_call(monkeypatch):
    monkeypatch.setenv(ENV, MCP_ERROR)

    async def ping(arguments: dict) -> dict:
        del arguments
        raise AssertionError("mcp tool should not execute when mcp_error is injected")

    tool = ToolSpec(
        name="ping",
        description="Ping",
        input_schema={"type": "object", "properties": {}},
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
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ping", "arguments": {}}})
        + "\n"
    )
    await mcp_protocol.serve_stdio(["norns"], stdin=stdin, stdout=stdout)
    body = json.loads(stdout.getvalue().strip())
    assert body["result"]["isError"] is True
    assert "injected" in body["result"]["content"][0]["text"]
