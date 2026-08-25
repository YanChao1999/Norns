from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.connector_config import (
    filter_chat_model_ids,
    merge_connector_config,
    resolve_llm_credentials,
)
from backend.app.models.connector import Connector, ConnectorType


def test_connector_config_round_trip():
    connector = Connector(name="gh", connector_type=ConnectorType.GITHUB, encrypted_config=b"")
    connector.set_config({"token": "secret", "base_url": "https://github.example"})
    assert connector.get_config()["token"] == "secret"
    assert connector.config_keys == ["base_url", "token"]
    assert connector.public_config == {"base_url": "https://github.example"}


def test_openai_connector_credentials_are_used_for_runs():
    connector = Connector(name="OpenAI", connector_type=ConnectorType.OPENAI, encrypted_config=b"", is_active=True)
    connector.set_config({"api_key": "from-ui", "base_url": "https://example.test/v1", "default_model": "gpt-4o-mini"})
    creds = resolve_llm_credentials(
        [connector],
        SimpleNamespace(openai_api_key="", openai_base_url="https://api.openai.com/v1", default_model="gpt-4o"),
    )
    assert creds.api_key == "from-ui"
    assert creds.base_url == "https://example.test/v1"
    assert creds.default_model == "gpt-4o-mini"
    assert connector.public_config.get("default_model") == "gpt-4o-mini"
    assert "api_key" not in connector.public_config


def test_openai_is_preferred_when_cursor_is_also_active_without_stage_binding():
    openai = Connector(name="OpenAI", connector_type=ConnectorType.OPENAI, encrypted_config=b"", is_active=True)
    openai.set_config({"api_key": "sk-openai", "base_url": "https://api.openai.com/v1", "default_model": "gpt-4o"})
    cursor = Connector(name="Cursor", connector_type=ConnectorType.CURSOR, encrypted_config=b"", is_active=True)
    cursor.set_config({"api_key": "crsr_test", "base_url": "https://api.cursor.com/v1", "default_model": "auto"})
    creds = resolve_llm_credentials([openai, cursor], SimpleNamespace(openai_api_key=""))
    # Global resolve still prefers DeepSeek/OpenAI before Cursor; stage llm_provider binds Cursor explicitly.
    assert creds.provider == "openai"


def test_cursor_proxy_url_is_usable_for_chat():
    cursor = Connector(name="Cursor", connector_type=ConnectorType.CURSOR, encrypted_config=b"", is_active=True)
    cursor.set_config({"api_key": "proxy-key", "base_url": "http://127.0.0.1:3000/v1", "default_model": "claude-4-sonnet"})
    creds = resolve_llm_credentials([cursor], SimpleNamespace(openai_api_key=""))
    assert creds.provider == "cursor"
    assert creds.base_url == "http://127.0.0.1:3000/v1"
    from backend.app.connector_config import uses_cursor_cloud_agent

    assert uses_cursor_cloud_agent(creds.provider, creds.base_url) is False
    assert uses_cursor_cloud_agent("cursor", "https://api.cursor.com/v1") is True


def test_deepseek_connector_credentials_are_used_for_runs():
    connector = Connector(name="DeepSeek", connector_type=ConnectorType.DEEPSEEK, encrypted_config=b"", is_active=True)
    connector.set_config(
        {"api_key": "sk-deepseek", "base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-v4-flash"}
    )
    creds = resolve_llm_credentials([connector], SimpleNamespace(openai_api_key=""))
    assert creds.api_key == "sk-deepseek"
    assert creds.provider == "deepseek"
    assert creds.base_url == "https://api.deepseek.com/v1"


def test_filter_chat_model_ids_keeps_provider_defaults():
    openai = filter_chat_model_ids(
        "openai",
        ["gpt-4o", "text-embedding-3-large", "whisper-1", "o3-mini"],
        default_model="gpt-4o-mini",
    )
    assert openai[0] == "gpt-4o-mini"
    assert "gpt-4o" in openai
    assert "o3-mini" in openai
    assert "whisper-1" not in openai
    deepseek = filter_chat_model_ids("deepseek", ["deepseek-v4-flash", "other"], default_model="deepseek-v4-flash")
    assert deepseek == ["deepseek-v4-flash"]


def test_merge_connector_config_keeps_blank_secrets():
    merged = merge_connector_config(
        {"api_key": "keep-me", "base_url": "https://old"}, {"api_key": "", "base_url": "https://new"}
    )
    assert merged["api_key"] == "keep-me"
    assert merged["base_url"] == "https://new"


@pytest.mark.parametrize("value", ["", "   ", "not-a-fernet-key"])
def test_encryption_key_must_be_valid_fernet(value: str):
    with pytest.raises(ValidationError):
        Settings(encryption_key=value)


@pytest.mark.asyncio
async def test_fetch_llm_model_catalog_falls_back_without_key():
    from backend.app.connector_config import LlmCredentials, fetch_llm_model_catalog

    catalog = await fetch_llm_model_catalog(
        LlmCredentials(
            api_key="",
            base_url="https://api.deepseek.com/v1",
            default_model="deepseek-v4-flash",
            provider="deepseek",
        )
    )
    assert catalog.source == "fallback"
    assert "deepseek-v4-flash" in catalog.models


@pytest.mark.asyncio
async def test_fetch_llm_model_catalog_uses_remote_list():
    from backend.app.connector_config import LlmCredentials, fetch_llm_model_catalog

    remote = SimpleNamespace(data=[SimpleNamespace(id="deepseek-v4-pro"), SimpleNamespace(id="deepseek-v4-flash")])
    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.models.list = AsyncMock(return_value=remote)
        catalog = await fetch_llm_model_catalog(
            LlmCredentials(
                api_key="sk-test",
                base_url="https://api.deepseek.com/v1",
                default_model="deepseek-v4-flash",
                provider="deepseek",
            )
        )
    assert catalog.source == "api"
    assert catalog.models[0] == "deepseek-v4-flash"
    assert "deepseek-v4-pro" in catalog.models
