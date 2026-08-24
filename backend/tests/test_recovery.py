from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import AgentRun, Board, Card, Stage
from backend.app.orchestrator.recovery import recover_stale_runs
from backend.app.orchestrator.state_machine import CardStatus


@pytest.mark.asyncio
async def test_recover_stale_runs_blocks_abandoned_cards():
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
        stage = Stage(name="Urd", order=1, require_approval=True)
        board.stages = [stage]
        card = Card(title="Work", body="Do it", status=CardStatus.RUNNING, current_stage=stage)
        board.cards = [card]
        run = AgentRun(card=card, stage=stage, status="running", inputs={}, tool_calls=[], model_output="")
        session.add_all([board, run])
        await session.commit()
        run.created_at = datetime.utcnow() - timedelta(hours=2)
        await session.commit()

        recovered = await recover_stale_runs(session, older_than_seconds=1800)
        await session.refresh(card)
        await session.refresh(run)
        assert recovered == 1
        assert run.status == "failed"
        assert card.status == CardStatus.BLOCKED

    await engine.dispose()
