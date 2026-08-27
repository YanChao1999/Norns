from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.agents.runner import WORK_INSTRUCTION, _execute_agent, _run_openai_tool_loop, _run_stage
from backend.app.database import Base
from backend.app.models import AgentConfig, AgentRun, Board, Card, Stage
from backend.app.orchestrator.state_machine import CardStatus
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


def _stage(name: str, order: int, require_approval: bool) -> Stage:
    stage = Stage(name=name, order=order, require_approval=require_approval)
    stage.agent_config = AgentConfig(system_prompt=name, model="gpt-4o", temperature=0.7, tool_allowlist=[])
    return stage


@pytest.mark.asyncio
async def test_gated_stage_waits_for_human_even_when_agent_recommends_approve(monkeypatch):
    engine, SessionLocal = await _session_factory()
    queued: list[tuple[str, str]] = []

    async def fake_execute(**_kwargs):
        return (
            "Looks good\nDECISION: approve\nREASON: Ready.",
            [],
            {"summary": "Looks good", "recommendation": "approve", "recommendation_reason": "Ready."},
        )

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "queued"

    monkeypatch.setattr("backend.app.agents.runner._execute_agent", fake_execute)
    monkeypatch.setattr("backend.app.agents.runner.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = _stage("Urd", 1, True)
        board.stages = [stage]
        card = Card(title="Work", body="Do it", status=CardStatus.IDLE, current_stage=stage)
        board.cards = [card]
        session.add(board)
        await session.commit()

        await _run_stage(session, card.id, stage.id, "run-1")
        await session.refresh(card)
        run = (await session.execute(select(AgentRun).where(AgentRun.id == "run-1"))).scalar_one()

        assert card.status == CardStatus.WAITING_APPROVAL
        assert card.current_stage_id == stage.id
        assert queued == []
        assert run.handoff["recommendation"] == "approve"

    await engine.dispose()


@pytest.mark.asyncio
async def test_auto_advance_ignores_agent_reject_recommendation(monkeypatch):
    engine, SessionLocal = await _session_factory()
    queued: list[tuple[str, str]] = []

    async def fake_execute(**_kwargs):
        return "No\nDECISION: reject\nREASON: Gaps.", [], {"summary": "No", "recommendation": "reject"}

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "queued"

    monkeypatch.setattr("backend.app.agents.runner._execute_agent", fake_execute)
    monkeypatch.setattr("backend.app.agents.runner.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage_a = _stage("Urd", 1, False)
        stage_b = _stage("Verdandi", 2, True)
        board.stages = [stage_a, stage_b]
        card = Card(title="Work", body="Do it", status=CardStatus.IDLE, current_stage=stage_a)
        board.cards = [card]
        session.add(board)
        await session.commit()

        await _run_stage(session, card.id, stage_a.id, "run-auto")
        await session.refresh(card)

        assert card.current_stage_id == stage_b.id
        assert queued == [(card.id, stage_b.id)]

    await engine.dispose()


@pytest.mark.asyncio
async def test_execute_agent_uses_cursor_cloud_agent_for_native_host(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_cursor(**kwargs):
        seen.update(kwargs)
        assert kwargs["api_key"] == "crsr_test"
        assert kwargs["model"] == "auto"
        return "Cursor handoff text\nDECISION: approve\nREASON: looks good"

    monkeypatch.setattr("backend.app.agents.runner.run_cursor_cloud_agent", fake_cursor)
    text, tools, handoff = await _execute_agent(
        SimpleNamespace(openai_api_key=""),
        SimpleNamespace(id="card-1", board_id="board-1", title="Work", body="Do it", runs=[]),
        SimpleNamespace(
            id="stage-1",
            name="Urd",
            require_approval=True,
            agent_config=SimpleNamespace(tool_allowlist=["norns"], system_prompt="Urd", model="auto", temperature=0.7),
        ),
        [],
        api_key="crsr_test",
        base_url="https://api.cursor.com/v1",
        default_model="auto",
        provider="cursor",
        workspace=SimpleNamespace(path="", git_url="", github_repo=""),
    )
    assert tools == []
    assert "Cursor handoff" in text
    assert handoff["summary"]
    assert "Card id: card-1" in str(seen.get("prompt") or "")
    assert "Board id: board-1" in str(seen.get("prompt") or "")
    assert seen["mcp_servers"]["norns"]["env"]["NORNS_CARD_ID"] == "card-1"
    assert seen["mcp_servers"]["norns"]["env"]["NORNS_STAGE_ID"] == "stage-1"


@pytest.mark.asyncio
async def test_openai_tool_loop_continues_after_empty_search():
    calls: list[dict[str, object]] = []

    async def search(arguments: dict) -> list:
        del arguments
        return []

    async def create(arguments: dict) -> dict:
        return {"key": "PROJ-1", "summary": arguments.get("summary")}

    search_call = SimpleNamespace(
        id="call-search",
        function=SimpleNamespace(name="jira_search", arguments='{"jql": "created >= -30d"}'),
    )
    create_call = SimpleNamespace(
        id="call-create",
        function=SimpleNamespace(name="jira_create", arguments='{"summary": "Please create a Jira ticket"}'),
    )

    class FakeMessage:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

        def model_dump(self, exclude_none=True):
            del exclude_none
            payload = {"role": "assistant", "content": self.content}
            if self.tool_calls:
                payload["tool_calls"] = [
                    {
                        "id": item.id,
                        "function": {"name": item.function.name, "arguments": item.function.arguments},
                    }
                    for item in self.tool_calls
                ]
            return payload

    script = [
        SimpleNamespace(choices=[SimpleNamespace(message=FakeMessage(tool_calls=[search_call]))]),
        SimpleNamespace(choices=[SimpleNamespace(message=FakeMessage(tool_calls=[create_call]))]),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=FakeMessage(content="Created PROJ-1\nDECISION: approve\nREASON: Ticket exists.")
                )
            ]
        ),
    ]

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return script.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    content, executed = await _run_openai_tool_loop(
        client,
        model="gpt-4o",
        temperature=0.1,
        messages=[{"role": "user", "content": "create a ticket"}],
        tools_payload=[{"type": "function", "function": {"name": "jira_search"}}],
        tool_map={
            "jira_search": RuntimeTool(name="jira_search", openai_tool={}, execute=search),
            "jira_create": RuntimeTool(name="jira_create", openai_tool={}, execute=create),
        },
    )
    assert [item["name"] for item in executed] == ["jira_search", "jira_create"]
    assert executed[0]["result"] == []
    assert executed[1]["result"]["key"] == "PROJ-1"
    assert "PROJ-1" in content
    assert all(call.get("tools") for call in calls)
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_openai_tool_loop_pauses_writes_when_confirm_enabled():
    create_call = SimpleNamespace(
        id="call-create",
        function=SimpleNamespace(name="jira_jira_create_issue", arguments='{"summary": "Ticket"}'),
    )

    class FakeMessage:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

        def model_dump(self, exclude_none=True):
            del exclude_none
            return {"role": "assistant", "content": self.content}

    script = [SimpleNamespace(choices=[SimpleNamespace(message=FakeMessage(tool_calls=[create_call]))])]

    class FakeCompletions:
        async def create(self, **kwargs):
            del kwargs
            return script.pop(0)

    async def create(arguments: dict) -> dict:
        del arguments
        raise AssertionError("write should not execute before confirmation")

    from backend.app.agents.runner import WriteConfirmationRequired

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    try:
        await _run_openai_tool_loop(
            client,
            model="gpt-4o",
            temperature=0.1,
            messages=[{"role": "user", "content": "create"}],
            tools_payload=[{"type": "function", "function": {"name": "jira_jira_create_issue"}}],
            tool_map={"jira_jira_create_issue": RuntimeTool(name="jira_jira_create_issue", openai_tool={}, execute=create)},
            confirm_writes=True,
        )
    except WriteConfirmationRequired as pending:
        assert pending.pending[0]["name"] == "jira_jira_create_issue"
        assert pending.executed == []
    else:
        raise AssertionError("expected WriteConfirmationRequired")


@pytest.mark.asyncio
async def test_execute_agent_includes_work_instruction(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_cursor(**kwargs):
        seen.update(kwargs)
        return "done\nDECISION: approve\nREASON: ok"

    monkeypatch.setattr("backend.app.agents.runner.run_cursor_cloud_agent", fake_cursor)
    await _execute_agent(
        SimpleNamespace(openai_api_key=""),
        SimpleNamespace(id="card-1", board_id="board-1", title="Work", body="Do it", runs=[]),
        SimpleNamespace(
            id="stage-1",
            name="Skuld",
            require_approval=True,
            agent_config=SimpleNamespace(tool_allowlist=["jira"], system_prompt="Skuld", model="auto", temperature=0.7),
        ),
        [],
        api_key="crsr_test",
        base_url="https://api.cursor.com/v1",
        default_model="auto",
        provider="cursor",
    )
    prompt = str(seen.get("prompt") or "")
    assert WORK_INSTRUCTION.split(".")[0] in prompt
    assert "do not defer" in prompt.lower() or "Do not defer" in prompt
    assert "Empty search results" in prompt


@pytest.mark.asyncio
async def test_execute_agent_is_practice_run_without_api_key():
    text, tools, handoff = await _execute_agent(
        SimpleNamespace(openai_api_key=""),
        SimpleNamespace(title="Work", body="Do it"),
        SimpleNamespace(name="Urd"),
        [],
        api_key="",
    )
    assert tools == []
    assert handoff["placeholder"] is True
    assert "practice run" in text.lower()
    assert "api key" in text.lower()
