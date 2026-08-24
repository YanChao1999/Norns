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


def test_production_rejects_demo_admin_password(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SECRET_KEY", "not-changeme")
    monkeypatch.setenv("NORNS_ENV", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("ADMIN_PASSWORD", "unique-pass")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    settings = Settings()
    assert settings.environment == "production"
    get_settings.cache_clear()


def test_production_rejects_empty_admin_password(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SECRET_KEY", "not-changeme")
    monkeypatch.setenv("NORNS_ENV", "production")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    for password in ("", "   "):
        monkeypatch.setenv("ADMIN_PASSWORD", password)
        with pytest.raises(ValidationError):
            Settings()
    get_settings.cache_clear()
