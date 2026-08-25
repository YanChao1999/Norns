from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.connector_config import merge_connector_config, resolve_llm_credentials
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


def test_cursor_connector_wins_over_openai_when_both_active():
    openai = Connector(name="OpenAI", connector_type=ConnectorType.OPENAI, encrypted_config=b"", is_active=True)
    openai.set_config({"api_key": "sk-openai", "base_url": "https://api.openai.com/v1", "default_model": "gpt-4o"})
    cursor = Connector(name="Cursor", connector_type=ConnectorType.CURSOR, encrypted_config=b"", is_active=True)
    cursor.set_config({"api_key": "crsr_test", "base_url": "https://api.cursor.com/v1", "default_model": "auto"})
    creds = resolve_llm_credentials([openai, cursor], SimpleNamespace(openai_api_key=""))
    assert creds.api_key == "crsr_test"
    assert creds.provider == "cursor"
    assert creds.default_model == "auto"


def test_deepseek_connector_credentials_are_used_for_runs():
    connector = Connector(name="DeepSeek", connector_type=ConnectorType.DEEPSEEK, encrypted_config=b"", is_active=True)
    connector.set_config(
        {"api_key": "sk-deepseek", "base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-v4-flash"}
    )
    creds = resolve_llm_credentials([connector], SimpleNamespace(openai_api_key=""))
    assert creds.api_key == "sk-deepseek"
    assert creds.provider == "deepseek"
    assert creds.base_url == "https://api.deepseek.com/v1"


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
