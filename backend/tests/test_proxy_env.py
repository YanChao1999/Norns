from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.proxy_env import (
    apply_proxy_env_fixes,
    httpx_trust_env,
    normalize_proxy_url,
    set_use_system_proxy,
    use_system_proxy,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("socks://127.0.0.1:7897/", "socks5://127.0.0.1:7897/"),
        ("SOCKS://127.0.0.1:7897", "socks5://127.0.0.1:7897"),
        ("socks5://127.0.0.1:7897/", "socks5://127.0.0.1:7897/"),
        ("socks5h://127.0.0.1:7897/", "socks5h://127.0.0.1:7897/"),
        ("http://127.0.0.1:7890", "http://127.0.0.1:7890"),
        ("  socks://proxy.local:1080  ", "socks5://proxy.local:1080"),
        ("", ""),
    ],
)
def test_normalize_proxy_url(raw: str, expected: str):
    assert normalize_proxy_url(raw) == expected


def test_apply_proxy_env_fixes_rewrites_socks_scheme():
    env = {
        "ALL_PROXY": "socks://127.0.0.1:7897/",
        "HTTPS_PROXY": "socks://127.0.0.1:7897/",
        "HTTP_PROXY": "http://127.0.0.1:7890",
        "NO_PROXY": "localhost",
    }
    changed = apply_proxy_env_fixes(env)
    assert env["ALL_PROXY"] == "socks5://127.0.0.1:7897/"
    assert env["HTTPS_PROXY"] == "socks5://127.0.0.1:7897/"
    assert env["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert env["NO_PROXY"] == "localhost"
    assert {key for key, _ in changed} == {"ALL_PROXY", "HTTPS_PROXY"}


def test_apply_proxy_env_fixes_is_idempotent():
    env = {"all_proxy": "socks5://127.0.0.1:7897/"}
    assert apply_proxy_env_fixes(env) == []
    assert env["all_proxy"] == "socks5://127.0.0.1:7897/"


def test_use_system_proxy_defaults_true(monkeypatch):
    monkeypatch.delenv("USE_SYSTEM_PROXY", raising=False)
    monkeypatch.delenv("NORNS_HOME", raising=False)
    assert use_system_proxy() is True


def test_use_system_proxy_env_false(monkeypatch):
    monkeypatch.setenv("USE_SYSTEM_PROXY", "false")
    assert use_system_proxy() is False
    assert httpx_trust_env() is False


def test_set_use_system_proxy_persists(tmp_path: Path, monkeypatch):
    home = tmp_path / "norns"
    home.mkdir()
    monkeypatch.setenv("NORNS_HOME", str(home))
    monkeypatch.delenv("USE_SYSTEM_PROXY", raising=False)

    assert set_use_system_proxy(False) is False
    assert use_system_proxy() is False
    prefs = home / "preferences.json"
    assert prefs.is_file()
    assert '"use_system_proxy": false' in prefs.read_text(encoding="utf-8")

    monkeypatch.delenv("USE_SYSTEM_PROXY", raising=False)
    assert use_system_proxy() is False

    assert set_use_system_proxy(True) is True
    assert use_system_proxy() is True


@pytest.mark.asyncio
async def test_create_async_openai_skips_proxy_when_disabled(monkeypatch):
    monkeypatch.setenv("USE_SYSTEM_PROXY", "false")
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897/")
    monkeypatch.setenv("HTTPS_PROXY", "socks://127.0.0.1:7897/")

    captured: dict = {}

    def fake_openai(**kwargs):
        captured["kwargs"] = kwargs
        client = AsyncMock()
        client.close = AsyncMock()
        return client

    with patch("openai.AsyncOpenAI", side_effect=fake_openai):
        from backend.app.llm_client import create_async_openai

        client = create_async_openai(api_key="sk-test", base_url="https://api.deepseek.com/v1")

    http_client = captured["kwargs"].get("http_client")
    assert http_client is not None
    assert getattr(http_client, "_trust_env", True) is False
    # socks:// left alone when proxy is off (clients ignore env)
    assert os.environ["ALL_PROXY"].startswith("socks://")
    await client.close()


@pytest.mark.asyncio
async def test_create_async_openai_normalizes_socks_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_SYSTEM_PROXY", "true")
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897/")
    monkeypatch.setenv("HTTPS_PROXY", "socks://127.0.0.1:7897/")

    constructed = {}

    def fake_openai(**kwargs):
        constructed["all_proxy"] = os.environ.get("ALL_PROXY")
        constructed["https_proxy"] = os.environ.get("HTTPS_PROXY")
        constructed["http_client"] = kwargs.get("http_client")
        client = AsyncMock()
        client.close = AsyncMock()
        return client

    with patch("openai.AsyncOpenAI", side_effect=fake_openai):
        from backend.app.llm_client import create_async_openai

        client = create_async_openai(api_key="sk-test", base_url="https://api.deepseek.com/v1")

    assert constructed["all_proxy"] == "socks5://127.0.0.1:7897/"
    assert constructed["https_proxy"] == "socks5://127.0.0.1:7897/"
    assert constructed["http_client"] is None
    await client.close()


@pytest.mark.asyncio
async def test_socks5_async_openai_constructs_without_transport_error(monkeypatch):
    """Regression: Clash socks:// used to fail AsyncOpenAI() and leak aclose AttributeError."""
    for key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("USE_SYSTEM_PROXY", "true")
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897/")

    from backend.app.llm_client import create_async_openai
    from backend.app.proxy_env import apply_proxy_env_fixes

    apply_proxy_env_fixes()
    assert os.environ["ALL_PROXY"].startswith("socks5://")

    client = create_async_openai(api_key="sk-test", base_url="https://api.deepseek.com/v1", timeout=1.0)
    try:
        assert client is not None
    finally:
        await client.close()
    await asyncio.sleep(0)
