from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import AgentConfig, Board, Card, Stage
from backend.app.orchestrator.auto_start import maybe_auto_start_card, pickup_idle_cards_for_stage
from backend.app.orchestrator.state_machine import CardStatus


@pytest.mark.asyncio
async def test_maybe_auto_start_enqueues_idle_card(monkeypatch):
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
        return run_id or "auto-run"

    monkeypatch.setattr("backend.app.orchestrator.auto_start.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = Stage(name="Urd", order=1, require_approval=True, auto_start=True)
        stage.agent_config = AgentConfig(system_prompt="x", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        board.stages = [stage]
        card = Card(title="Work", body="Do it", status=CardStatus.IDLE, current_stage=stage)
        board.cards = [card]
        session.add(board)
        await session.commit()

        run_id = await maybe_auto_start_card(session, card, stage)
        await session.refresh(card)
        assert run_id == "auto-run"
        assert card.status == CardStatus.RUNNING
        assert queued == [(card.id, stage.id)]

    await engine.dispose()


@pytest.mark.asyncio
async def test_maybe_auto_start_skips_without_flag(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    called = {"n": 0}

    async def fake_enqueue(*_args, **_kwargs):
        called["n"] += 1
        return "x"

    monkeypatch.setattr("backend.app.orchestrator.auto_start.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = Stage(name="Urd", order=1, require_approval=True, auto_start=False)
        stage.agent_config = AgentConfig(system_prompt="x", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        board.stages = [stage]
        card = Card(title="Work", body="Do it", status=CardStatus.IDLE, current_stage=stage)
        board.cards = [card]
        session.add(board)
        await session.commit()

        assert await maybe_auto_start_card(session, card, stage) is None
        await session.refresh(card)
        assert card.status == CardStatus.IDLE
        assert called["n"] == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_pickup_idle_cards_for_stage(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    queued: list[str] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append(card_id)
        return run_id or f"run-{card_id}"

    monkeypatch.setattr("backend.app.orchestrator.auto_start.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = Stage(name="Urd", order=1, require_approval=True, auto_start=True)
        stage.agent_config = AgentConfig(system_prompt="x", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        board.stages = [stage]
        a = Card(title="A", body="", status=CardStatus.IDLE, current_stage=stage)
        b = Card(title="B", body="", status=CardStatus.WAITING_APPROVAL, current_stage=stage)
        board.cards = [a, b]
        session.add(board)
        await session.commit()

        run_ids = await pickup_idle_cards_for_stage(session, stage.id)
        assert len(run_ids) == 1
        assert queued == [a.id]
        await session.refresh(a)
        await session.refresh(b)
        assert a.status == CardStatus.RUNNING
        assert b.status == CardStatus.WAITING_APPROVAL

    await engine.dispose()
