from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.cursor_api import list_cursor_models, run_cursor_cloud_agent


@pytest.mark.asyncio
async def test_list_cursor_models_uses_sdk(monkeypatch):
    class FakeClient:
        def __init__(self, *, auth_token: str):
            assert auth_token == "crsr_test"

        async def list_models(self, *, api_key: str):
            assert api_key == "crsr_test"
            return [SimpleNamespace(id="composer-2"), SimpleNamespace(id="auto")]

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("backend.app.cursor_api.AsyncClient", FakeClient)
    models = await list_cursor_models("crsr_test")
    assert models == ["composer-2", "auto"]


@pytest.mark.asyncio
async def test_run_cursor_cloud_agent_uses_sdk(monkeypatch):
    created: dict[str, object] = {}

    class FakeRun:
        async def wait(self) -> None:
            return None

        async def text(self) -> str:
            return "Stage handoff from Cursor SDK"

    class FakeAgent:
        async def send(self, prompt: str):
            created["prompt"] = prompt
            return FakeRun()

        async def aclose(self) -> None:
            created["closed"] = True

    class FakeClient:
        def __init__(self, *, auth_token: str):
            assert auth_token == "crsr_test"

        async def aclose(self) -> None:
            created["client_closed"] = True

    async def fake_create(*, client, model, api_key, name, cloud):
        assert api_key == "crsr_test"
        assert name == "Norns stage run"
        assert model is None  # auto -> omit explicit id
        assert cloud.repos == []
        created["client"] = client
        return FakeAgent()

    monkeypatch.setattr("backend.app.cursor_api.AsyncClient", FakeClient)
    monkeypatch.setattr("backend.app.cursor_api.AsyncAgent.create", staticmethod(fake_create))

    text = await run_cursor_cloud_agent(
        api_key="crsr_test",
        prompt="Do the stage",
        model="auto",
        timeout_seconds=5.0,
    )
    assert text == "Stage handoff from Cursor SDK"
    assert created["prompt"] == "Do the stage"
    assert created["client_closed"] is True


@pytest.mark.asyncio
async def test_run_cursor_cloud_agent_attaches_repo(monkeypatch):
    seen: dict[str, object] = {}

    class FakeRun:
        async def wait(self) -> None:
            return None

        async def text(self) -> str:
            return "ok"

    class FakeAgent:
        async def send(self, prompt: str):
            return FakeRun()

        async def aclose(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *, auth_token: str):
            pass

        async def aclose(self) -> None:
            return None

    async def fake_create(*, client, model, api_key, name, cloud):
        seen["model"] = model
        seen["repos"] = list(cloud.repos)
        return FakeAgent()

    monkeypatch.setattr("backend.app.cursor_api.AsyncClient", FakeClient)
    monkeypatch.setattr("backend.app.cursor_api.AsyncAgent.create", staticmethod(fake_create))

    text = await run_cursor_cloud_agent(
        api_key="crsr_test",
        prompt="Ship it",
        model="composer-2",
        repo_url="https://github.com/example/norns",
    )
    assert text == "ok"
    assert seen["model"] == "composer-2"
    assert len(seen["repos"]) == 1
    assert seen["repos"][0].url == "https://github.com/example/norns"
