from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_session
from backend.app.main import app
from backend.app.models import AgentRun, Card, Stage
from backend.app.orchestrator.state_machine import CardStatus
from backend.app.token_usage import attach_usage


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


def test_bakeoff_forks_identical_prompt_different_tools(monkeypatch):
    client, engine, SessionLocal = _make_client()
    queued: list[tuple[str, str]] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or f"run-{len(queued)}"

    monkeypatch.setattr("backend.app.bakeoff.enqueue_stage_run", fake_enqueue)

    with client:
        assert client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
        board = client.post("/api/boards", json={"name": "Bakeoff"}).json()
        cards = client.get(f"/api/boards/{board['id']}/cards").json()
        card_id = cards[0]["id"]
        client.put(f"/api/cards/{card_id}", json={"body": "Compare tool setups on this task."})

        started = client.post(
            f"/api/cards/{card_id}/bakeoff",
            json={
                "prompt": "Write a one-line summary of the risk.",
                "arms": [
                    {
                        "label": "tools",
                        "model": "gpt-4o",
                        "llm_provider": "openai",
                        "tool_allowlist": ["norns", "sandbox"],
                    },
                    {"label": "bare", "model": "gpt-4o", "llm_provider": "openai", "tool_allowlist": []},
                ],
                "require_approval": False,
                "auto_start": True,
            },
        )
        assert started.status_code == 202, started.text
        body = started.json()
        assert body["bakeoff_id"]
        assert body["status"] == "running"
        assert len(body["arms"]) == 2
        assert {arm["label"] for arm in body["arms"]} == {"tools", "bare"}
        assert len(queued) == 2

        async def inspect():
            async with SessionLocal() as session:
                family = list(
                    (await session.execute(select(Card).where((Card.id == card_id) | (Card.parent_card_id == card_id))))
                    .scalars()
                    .all()
                )
                assert len(family) == 2
                bodies = {card.body for card in family}
                assert bodies == {"Write a one-line summary of the risk."}
                stages = list(
                    (
                        await session.execute(
                            select(Stage).where(Stage.board_id == board["id"]).options(selectinload(Stage.agent_config))
                        )
                    )
                    .scalars()
                    .all()
                )
                bakeoff_stages = [stage for stage in stages if stage.name.startswith("Bakeoff ·")]
                assert len(bakeoff_stages) == 2
                for stage in bakeoff_stages:
                    assert stage.agent_config is not None
                tools_stage = next(stage for stage in bakeoff_stages if stage.name.endswith("tools"))
                bare_stage = next(stage for stage in bakeoff_stages if stage.name.endswith("bare"))
                assert tools_stage.agent_config.tool_allowlist == ["norns", "sandbox"]
                assert bare_stage.agent_config.tool_allowlist == []

        asyncio.run(inspect())

        compare = client.get(f"/api/cards/{card_id}/bakeoff")
        assert compare.status_code == 200
        report = compare.json()
        assert report["bakeoff_id"] == body["bakeoff_id"]
        assert report["prompt"] == "Write a one-line summary of the risk."
        assert len(report["arms"]) == 2

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_bakeoff_compare_usage_and_outcomes(monkeypatch):
    client, engine, SessionLocal = _make_client()

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        return run_id or "queued"

    monkeypatch.setattr("backend.app.bakeoff.enqueue_stage_run", fake_enqueue)

    with client:
        assert client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
        board = client.post("/api/boards", json={"name": "Compare"}).json()
        cards = client.get(f"/api/boards/{board['id']}/cards").json()
        card_id = cards[0]["id"]

        started = client.post(
            f"/api/cards/{card_id}/bakeoff",
            json={
                "arms": [
                    {
                        "label": "A",
                        "tool_allowlist": ["norns"],
                        "model": "deepseek-v4-flash",
                        "llm_provider": "deepseek",
                    },
                    {"label": "B", "tool_allowlist": [], "model": "gpt-4o", "llm_provider": "openai"},
                ],
                "auto_start": False,
            },
        )
        assert started.status_code == 202
        bakeoff_id = started.json()["bakeoff_id"]
        arms = {arm["label"]: arm for arm in started.json()["arms"]}

        async def seed_outcomes():
            async with SessionLocal() as session:
                for label, tokens, rec in (("A", 500, "approve"), ("B", 900, "reject")):
                    arm = arms[label]
                    card = await session.get(Card, arm["card_id"])
                    assert card is not None
                    handoff = attach_usage(
                        {
                            "summary": f"Arm {label} result",
                            "recommendation": rec,
                            "bakeoff": {
                                "id": bakeoff_id,
                                "label": label,
                                "root_card_id": card_id,
                                "stage_id": arm["stage_id"],
                                "prompt": card.body,
                                "tool_allowlist": ["norns"] if label == "A" else [],
                            },
                            "llm": {
                                "provider": "deepseek" if label == "A" else "openai",
                                "model": "deepseek-v4-flash" if label == "A" else "gpt-4o",
                            },
                        },
                        {
                            "prompt_tokens": tokens,
                            "completion_tokens": 50,
                            "total_tokens": tokens + 50,
                            "rounds": 1,
                            "source": "api",
                        },
                        identity={
                            "provider": "deepseek" if label == "A" else "openai",
                            "model": "deepseek-v4-flash" if label == "A" else "gpt-4o",
                        },
                    )
                    session.add(
                        AgentRun(
                            card_id=card.id,
                            stage_id=arm["stage_id"],
                            status="completed",
                            inputs={},
                            tool_calls=[],
                            model_output=f"output {label}",
                            handoff=handoff,
                        )
                    )
                    card.status = CardStatus.WAITING_APPROVAL
                await session.commit()

        asyncio.run(seed_outcomes())
        report = client.get(f"/api/cards/{card_id}/bakeoff").json()
        assert report["status"] == "waiting"
        by_label = {arm["label"]: arm for arm in report["arms"]}
        assert by_label["A"]["usage"]["total_tokens"] == 550
        assert by_label["B"]["usage"]["total_tokens"] == 950
        assert by_label["A"]["recommendation"] == "approve"
        assert by_label["B"]["recommendation"] == "reject"
        assert by_label["A"]["tool_allowlist"] == ["norns"]
        assert by_label["B"]["tool_allowlist"] == []
        assert report["totals"]["total_tokens"] == 1500

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_bakeoff_rejects_single_arm():
    client, engine, _SessionLocal = _make_client()
    with client:
        assert client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
        board = client.post("/api/boards", json={"name": "Bad"}).json()
        cards = client.get(f"/api/boards/{board['id']}/cards").json()
        response = client.post(
            f"/api/cards/{cards[0]['id']}/bakeoff",
            json={"arms": [{"label": "only", "tool_allowlist": []}]},
        )
        assert response.status_code == 422

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


@pytest.mark.asyncio
async def test_bakeoff_compare_none_without_meta():
    from backend.app.bakeoff import bakeoff_compare

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    await _create_tables(engine)
    async with SessionLocal() as session:
        from backend.app.models import Board

        board = Board(name="x")
        card = Card(title="t", body="b", status=CardStatus.IDLE, board=board)
        session.add_all([board, card])
        await session.commit()
        report = await bakeoff_compare(session, card.id)
        assert report is not None
        assert report["status"] == "none"
        assert report["arms"] == []
    await engine.dispose()
