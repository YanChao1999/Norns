import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from backend.app.config import Settings, get_settings


def test_settings_require_valid_encryption_key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(ValidationError):
        Settings()

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    settings = Settings()
    assert settings.resolved_encryption_key == key
    get_settings.cache_clear()


def test_settings_reject_default_secret_key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SECRET_KEY", "changeme")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()
    get_settings.cache_clear()
