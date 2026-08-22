from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_session
from backend.app.main import app


def _make_client() -> tuple[TestClient, object]:
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
    return TestClient(app), engine


def test_board_crud():
    client, engine = _make_client()
    with client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200

        created = client.post("/api/boards", json={"name": "Platform", "description": "Delivery board"})
        assert created.status_code == 201
        board_id = created.json()["id"]

        listed = client.get("/api/boards")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.put(f"/api/boards/{board_id}", json={"name": "Platform Ops"})
        assert updated.status_code == 200
        assert updated.json()["name"] == "Platform Ops"

        deleted = client.delete(f"/api/boards/{board_id}")
        assert deleted.status_code == 204

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_card_update_cannot_bypass_gates():
    client, engine = _make_client()
    with client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        board = client.post("/api/boards", json={"name": "Platform"}).json()
        stage_id = board["stages"][0]["id"]
        card = client.post(f"/api/boards/{board['id']}/cards", json={"title": "Work", "body": "Do it"}).json()

        skipped = client.post(
            f"/api/boards/{board['id']}/cards",
            json={"title": "Skip ahead", "current_stage_id": board["stages"][2]["id"]},
        )
        assert skipped.status_code == 201
        assert skipped.json()["current_stage_id"] == stage_id

        updated = client.put(
            f"/api/cards/{card['id']}",
            json={"title": "Work updated", "status": "done", "current_stage_id": board["stages"][1]["id"]},
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Work updated"
        assert updated.json()["status"] == "idle"
        assert updated.json()["current_stage_id"] == stage_id

        approval = client.post(f"/api/cards/{card['id']}/approve", json={"approved": True})
        assert approval.status_code == 409

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_stage_machine_crud_and_guards():
    client, engine = _make_client()
    with client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        board = client.post("/api/boards", json={"name": "Platform"}).json()
        board_id = board["id"]
        original_ids = [stage["id"] for stage in board["stages"]]

        machine = client.get("/api/orchestration/card-status")
        assert machine.status_code == 200
        body = machine.json()
        assert "idle" in body["states"]
        assert "running" in body["transitions"]["idle"]

        created = client.post(
            f"/api/boards/{board_id}/stages",
            json={"name": "Review", "require_approval": False},
        )
        assert created.status_code == 201
        review_id = created.json()["id"]
        assert created.json()["require_approval"] is False

        reordered = client.put(
            f"/api/boards/{board_id}/stages/reorder",
            json={"stage_ids": [review_id, *original_ids]},
        )
        assert reordered.status_code == 200
        assert [stage["id"] for stage in reordered.json()] == [review_id, *original_ids]
        assert [stage["order"] for stage in reordered.json()] == [1, 2, 3, 4]

        bad_reorder = client.put(f"/api/boards/{board_id}/stages/reorder", json={"stage_ids": original_ids})
        assert bad_reorder.status_code == 400

        renamed = client.put(f"/api/stages/{review_id}", json={"name": "QA", "require_approval": True})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "QA"
        assert renamed.json()["require_approval"] is True

        removed = client.delete(f"/api/stages/{review_id}")
        assert removed.status_code == 204
        leftover = client.get(f"/api/boards/{board_id}/stages").json()
        assert [stage["id"] for stage in leftover] == original_ids

        card = client.post(f"/api/boards/{board_id}/cards", json={"title": "Work"}).json()
        blocked = client.delete(f"/api/stages/{card['current_stage_id']}")
        assert blocked.status_code == 409
        assert "still has cards" in blocked.json()["detail"]

        empty_stages = [stage for stage in leftover if stage["id"] != card["current_stage_id"]]
        for stage in empty_stages:
            assert client.delete(f"/api/stages/{stage['id']}").status_code == 204
        assert client.delete(f"/api/stages/{card['current_stage_id']}").status_code == 409

        empty_board = client.post("/api/boards", json={"name": "Empty machine"}).json()
        for stage in empty_board["stages"][1:]:
            assert client.delete(f"/api/stages/{stage['id']}").status_code == 204
        last_empty = client.delete(f"/api/stages/{empty_board['stages'][0]['id']}")
        assert last_empty.status_code == 409
        assert "at least one stage" in last_empty.json()["detail"]

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
