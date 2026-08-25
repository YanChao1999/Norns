from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.agents.runner import _execute_agent, _run_stage
from backend.app.database import Base
from backend.app.models import AgentConfig, AgentRun, Board, Card, Stage
from backend.app.orchestrator.state_machine import CardStatus


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
