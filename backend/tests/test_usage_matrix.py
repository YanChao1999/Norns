from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_session
from backend.app.main import app
from backend.app.models import AgentRun, Card
from backend.app.orchestrator.state_machine import CardStatus


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _make_client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(_create_tables(engine))

    async def override_get_session():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app), engine, SessionLocal


def test_card_usage_matrix_across_stages():
    client, engine, SessionLocal = _make_client()
    with client:
        assert client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
        board = client.post("/api/boards", json={"name": "Usage"}).json()
        card_id = board["cards"][0]["id"] if board.get("cards") else None
        if not card_id:
            # Board create returns detail with sample card in some versions; fall back to list.
            cards = client.get(f"/api/boards/{board['id']}/cards").json()
            card_id = cards[0]["id"]
        detail = client.get(f"/api/boards/{board['id']}").json()
        stages = sorted(detail["stages"], key=lambda item: item["order"])

        async def seed():
            async with SessionLocal() as session:
                card = await session.get(Card, card_id)
                assert card is not None
                session.add(
                    AgentRun(
                        card_id=card.id,
                        stage_id=stages[0]["id"],
                        status="completed",
                        inputs={},
                        tool_calls=[],
                        model_output="urd",
                        handoff={
                            "summary": "urd",
                            "llm": {"provider": "deepseek", "model": "deepseek-v4-flash"},
                            "usage": {
                                "prompt_tokens": 1000,
                                "completion_tokens": 200,
                                "total_tokens": 1200,
                                "rounds": 2,
                                "source": "api",
                                "provider": "deepseek",
                                "model": "deepseek-v4-flash",
                            },
                        },
                    )
                )
                session.add(
                    AgentRun(
                        card_id=card.id,
                        stage_id=stages[1]["id"],
                        status="completed",
                        inputs={},
                        tool_calls=[],
                        model_output="verdandi",
                        handoff={
                            "summary": "verdandi",
                            "llm": {"provider": "openai", "model": "gpt-4o"},
                            "usage": {
                                "prompt_tokens": 800,
                                "completion_tokens": 400,
                                "total_tokens": 1200,
                                "rounds": 1,
                                "source": "api",
                                "provider": "openai",
                                "model": "gpt-4o",
                            },
                        },
                    )
                )
                card.status = CardStatus.IDLE
                await session.commit()

        asyncio.run(seed())
        usage = client.get(f"/api/cards/{card_id}/usage")
        assert usage.status_code == 200
        body = usage.json()
        assert body["totals"]["prompt_tokens"] == 1800
        assert body["totals"]["completion_tokens"] == 600
        assert body["totals"]["total_tokens"] == 2400
        assert len(body["by_stage"]) >= 2
        first = next(row for row in body["by_stage"] if row["stage_id"] == stages[0]["id"])
        assert first["total_tokens"] == 1200
        assert first["provider"] == "deepseek"
        second = next(row for row in body["by_stage"] if row["stage_id"] == stages[1]["id"])
        assert second["model"] == "gpt-4o"

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
