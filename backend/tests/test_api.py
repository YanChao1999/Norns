from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_session
from backend.app.main import app


def test_board_crud():
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

    with TestClient(app) as client:
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


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
