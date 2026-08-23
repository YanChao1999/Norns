from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.app.orchestrator.enqueue as enqueue
from backend.app.config import get_settings
from backend.app.database import Base
from backend.app.models import AgentConfig, AgentRun, Board, Card, Stage, StageTransition
from backend.app.orchestrator.gates import approve_card, reject_card
from backend.app.orchestrator.state_machine import CardStatus


@pytest.mark.asyncio
async def test_enqueue_stage_run_uses_arq(monkeypatch):
    captured: dict[str, object] = {}

    class FakeRedis:
        async def enqueue_job(self, name, **kwargs):
            captured["name"] = name
            captured["kwargs"] = kwargs

        async def close(self):
            captured["closed"] = True

    async def fake_create_pool(_settings):
        captured["pool"] = True
        return FakeRedis()

    monkeypatch.setattr(enqueue, "create_pool", fake_create_pool)
    monkeypatch.setattr(enqueue, "_pool", None)

    run_id = await enqueue.enqueue_stage_run("card-1", "stage-1", "run-1")
    assert run_id == "run-1"
    assert captured["name"] == "run_stage_task"
    assert captured["kwargs"] == {"card_id": "card-1", "stage_id": "stage-1", "run_id": "run-1"}
    assert captured["pool"] is True


@pytest.mark.asyncio
async def test_enqueue_stage_run_inline(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run_stage(card_id, stage_id, run_id):
        captured["args"] = (card_id, stage_id, run_id)

    monkeypatch.setenv("QUEUE_BACKEND", "inline")
    get_settings.cache_clear()
    monkeypatch.setattr("backend.app.agents.runner.run_stage", fake_run_stage)
    try:
        run_id = await enqueue.enqueue_stage_run("card-1", "stage-1", "run-inline")
        await asyncio.sleep(0)
        assert run_id == "run-inline"
        assert captured["args"] == ("card-1", "stage-1", "run-inline")
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_gate_logic_creates_approval_and_moves_card(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    queued: list[tuple[str, str]] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "generated-run"

    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage_a = Stage(name="Todo", order=1, require_approval=True)
        stage_a.agent_config = AgentConfig(system_prompt="todo", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        stage_b = Stage(name="Doing", order=2, require_approval=True)
        stage_b.agent_config = AgentConfig(system_prompt="doing", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        board.stages = [stage_a, stage_b]
        card = Card(title="Card", body="Body", status=CardStatus.WAITING_APPROVAL, current_stage=stage_a)
        board.cards = [card]
        run = AgentRun(
            card=card,
            stage=stage_a,
            inputs={},
            tool_calls=[],
            model_output="done",
            handoff={"summary": "handoff"},
            status="completed",
            completed_at=datetime.utcnow(),
        )
        session.add_all([board, run])
        await session.commit()

        approval = await approve_card(session, card.id, "admin", "looks good")
        await session.refresh(card)
        assert approval.approved is True
        assert card.current_stage_id == stage_b.id
        assert card.status == CardStatus.RUNNING
        assert queued == [(card.id, stage_b.id)]

        card.status = CardStatus.WAITING_APPROVAL
        run2 = AgentRun(
            card_id=card.id,
            stage_id=stage_b.id,
            inputs={},
            tool_calls=[],
            model_output="retry",
            handoff={"summary": "redo"},
            status="completed",
            completed_at=datetime.utcnow(),
        )
        session.add(run2)
        await session.commit()

        rejection = await reject_card(session, card.id, "admin", "needs work")
        await session.refresh(card)
        assert rejection.approved is False
        assert card.current_stage_id == stage_b.id
        assert card.status == CardStatus.BLOCKED

    await engine.dispose()


@pytest.mark.asyncio
async def test_reject_line_returns_card_to_previous_stage():
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
        stage_a = Stage(name="Todo", order=1, require_approval=True)
        stage_a.agent_config = AgentConfig(system_prompt="todo", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        stage_b = Stage(name="Doing", order=2, require_approval=True)
        stage_b.agent_config = AgentConfig(system_prompt="doing", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        board.stages = [stage_a, stage_b]
        card = Card(title="Card", body="Body", status=CardStatus.WAITING_APPROVAL, current_stage=stage_b)
        board.cards = [card]
        run = AgentRun(
            card=card,
            stage=stage_b,
            inputs={},
            tool_calls=[],
            model_output="done",
            handoff={"summary": "handoff"},
            status="completed",
            completed_at=datetime.utcnow(),
        )
        session.add_all([board, run])
        await session.flush()
        session.add(
            StageTransition(
                board_id=board.id,
                from_stage_id=stage_b.id,
                to_stage_id=stage_a.id,
                event="reject",
            )
        )
        await session.commit()

        await reject_card(session, card.id, "admin", "send back")
        await session.refresh(card)
        assert card.current_stage_id == stage_a.id
        assert card.status == CardStatus.IDLE

    await engine.dispose()
