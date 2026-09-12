from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from backend.app.cursor_api import (
    _bridge_workspace,
    list_cursor_model_infos,
    list_cursor_models,
    run_cursor_cloud_agent,
)


class _FakeBridgeClient:
    def __init__(self) -> None:
        self.closed = False

    async def list_models(self, *, api_key: str):
        assert api_key == "crsr_test"
        return [SimpleNamespace(id="composer-2", display_name="Composer 2"), SimpleNamespace(id="auto")]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.closed = True
        return False


def test_bridge_workspace_reuses_one_directory():
    assert _bridge_workspace() == _bridge_workspace()


@pytest.mark.asyncio
async def test_list_cursor_models_uses_http_api(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "items": [
                    {"id": "composer-2.5", "displayName": "Composer 2.5"},
                    {"id": "default", "displayName": "Auto"},
                    {"id": "grok-4.6", "displayName": "Grok 4.6"},
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            assert url.endswith("/v1/models")
            assert kwargs.get("auth") == ("crsr_test", "")
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    infos = await list_cursor_model_infos("crsr_test")
    assert [item.id for item in infos] == ["composer-2.5", "auto", "grok-4.6"]
    assert infos[0].display_name == "Composer 2.5"
    models = await list_cursor_models("crsr_test")
    assert models == ["composer-2.5", "auto", "grok-4.6"]


@pytest.mark.asyncio
async def test_list_cursor_models_falls_back_to_sdk_bridge(monkeypatch):
    client = _FakeBridgeClient()

    class BoomClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise httpx.ConnectError("offline")

    async def fake_launch_bridge(*, workspace: str):
        assert workspace
        return client

    monkeypatch.setattr("httpx.AsyncClient", BoomClient)
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
async def test_run_cursor_cloud_agent_remaps_gpt4o(monkeypatch):
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
        return FakeAgent()

    monkeypatch.setattr(
        "backend.app.cursor_api.AsyncClient.launch_bridge",
        staticmethod(fake_launch_bridge),
    )
    monkeypatch.setattr("backend.app.cursor_api.AsyncAgent.create", staticmethod(fake_create))

    text = await run_cursor_cloud_agent(
        api_key="crsr_test",
        prompt="Do the stage",
        model="gpt-4o",
        timeout_seconds=5.0,
    )
    assert text == "ok"
    assert seen["model"] == "auto"


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

    async def fake_create(options=None, *, client, model, api_key, name, cloud):
        seen["model"] = model
        seen["repos"] = list(cloud.repos)
        seen["options"] = options
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


@pytest.mark.asyncio
async def test_run_cursor_uses_local_git_workspace(monkeypatch, tmp_path):
    repo = tmp_path / "app"
    repo.mkdir()
    (repo / ".git").mkdir()
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
        seen["bridge"] = workspace
        return client

    async def fake_create(options=None, *, client, model, api_key, name, cloud=None, local=None):
        seen["local"] = local
        seen["cloud"] = cloud
        return FakeAgent()

    monkeypatch.setattr(
        "backend.app.cursor_api.AsyncClient.launch_bridge",
        staticmethod(fake_launch_bridge),
    )
    monkeypatch.setattr("backend.app.cursor_api.AsyncAgent.create", staticmethod(fake_create))

    text = await run_cursor_cloud_agent(
        api_key="crsr_test",
        prompt="Edit the repo",
        workspace_path=str(repo),
        repo_url="https://github.com/example/norns",
    )
    assert text == "ok"
    assert seen["bridge"] == str(repo)
    assert seen["local"] is not None
    assert seen["cloud"] is None


@pytest.mark.asyncio
async def test_run_cursor_cloud_agent_attaches_mcp_servers(monkeypatch):
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

    async def fake_create(options=None, *, client, model, api_key, name, cloud):
        seen["mcp"] = options.mcp_servers
        return FakeAgent()

    monkeypatch.setattr(
        "backend.app.cursor_api.AsyncClient.launch_bridge",
        staticmethod(fake_launch_bridge),
    )
    monkeypatch.setattr("backend.app.cursor_api.AsyncAgent.create", staticmethod(fake_create))

    text = await run_cursor_cloud_agent(
        api_key="crsr_test",
        prompt="Use tools",
        mcp_servers={"norns": {"command": "python", "args": ["-m", "norns.mcp"]}},
    )
    assert text == "ok"
    assert "norns" in seen["mcp"]
