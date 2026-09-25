from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_session
from backend.app.main import app


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
    return TestClient(app), engine


def test_preferences_proxy_toggle(tmp_path: Path, monkeypatch):
    from backend.app.config import get_settings

    home = tmp_path / "norns"
    home.mkdir()
    # Isolate from apply_config tests that leave a random ADMIN_PASSWORD in the env.
    monkeypatch.setenv("NORNS_HOME", str(home))
    monkeypatch.setenv("ADMIN_PASSWORD", "admin")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897/")
    monkeypatch.delenv("USE_SYSTEM_PROXY", raising=False)
    get_settings.cache_clear()

    client, engine = _make_client()
    with client:
        assert client.get("/api/preferences").status_code == 401
        assert client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200

        got = client.get("/api/preferences")
        assert got.status_code == 200
        body = got.json()
        assert body["use_system_proxy"] is True
        assert body["proxy_env_detected"] is True
        assert "ALL_PROXY" in body["proxy_env"]

        off = client.put("/api/preferences", json={"use_system_proxy": False})
        assert off.status_code == 200
        assert off.json()["use_system_proxy"] is False
        assert os.environ["USE_SYSTEM_PROXY"] == "false"
        prefs = (home / "preferences.json").read_text(encoding="utf-8")
        assert '"use_system_proxy": false' in prefs

        on = client.put("/api/preferences", json={"use_system_proxy": True})
        assert on.status_code == 200
        assert on.json()["use_system_proxy"] is True
        assert os.environ["ALL_PROXY"].startswith("socks5://")

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    asyncio.run(engine.dispose())
