from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.cursor_api import list_cursor_models, run_cursor_cloud_agent


class _FakeBridgeClient:
    def __init__(self) -> None:
        self.closed = False

    async def list_models(self, *, api_key: str):
        assert api_key == "crsr_test"
        return [SimpleNamespace(id="composer-2"), SimpleNamespace(id="auto")]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.closed = True
        return False


@pytest.mark.asyncio
async def test_list_cursor_models_uses_sdk_bridge(monkeypatch):
    client = _FakeBridgeClient()

    async def fake_launch_bridge(*, workspace: str):
        assert workspace
        return client

    monkeypatch.setattr(
        "backend.app.cursor_api.AsyncClient.launch_bridge",
        staticmethod(fake_launch_bridge),
    )
    models = await list_cursor_models("crsr_test")
    assert models == ["composer-2", "auto"]
    assert client.closed is True


@pytest.mark.asyncio
async def test_run_cursor_cloud_agent_uses_sdk_bridge(monkeypatch):
    created: dict[str, object] = {}
    client = _FakeBridgeClient()

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

    async def fake_launch_bridge(*, workspace: str):
        return client

    async def fake_create(*, client, model, api_key, name, cloud):
        assert api_key == "crsr_test"
        assert name == "Norns stage run"
        assert model == "auto"
        assert list(cloud.repos or []) == []
        created["client"] = client
        return FakeAgent()

    monkeypatch.setattr(
        "backend.app.cursor_api.AsyncClient.launch_bridge",
        staticmethod(fake_launch_bridge),
    )
    monkeypatch.setattr("backend.app.cursor_api.AsyncAgent.create", staticmethod(fake_create))

    text = await run_cursor_cloud_agent(
        api_key="crsr_test",
        prompt="Do the stage",
        model="auto",
        timeout_seconds=5.0,
    )
    assert text == "Stage handoff from Cursor SDK"
    assert created["prompt"] == "Do the stage"
    assert created["closed"] is True
    assert client.closed is True


@pytest.mark.asyncio
async def test_run_cursor_cloud_agent_attaches_repo(monkeypatch):
    seen: dict[str, object] = {}
    client = _FakeBridgeClient()

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

    async def fake_launch_bridge(*, workspace: str):
        return client

    async def fake_create(*, client, model, api_key, name, cloud):
        seen["model"] = model
        seen["repos"] = list(cloud.repos)
        return FakeAgent()

    monkeypatch.setattr(
        "backend.app.cursor_api.AsyncClient.launch_bridge",
        staticmethod(fake_launch_bridge),
    )
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
