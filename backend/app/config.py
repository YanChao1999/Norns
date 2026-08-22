from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Norns"
    database_url: str = Field(default="sqlite+aiosqlite:///./norns.db", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    secret_key: str = Field(default="changeme", alias="SECRET_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    default_model: str = Field(default="gpt-4o", alias="DEFAULT_MODEL")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin", alias="ADMIN_PASSWORD")
    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")
    session_cookie_name: str = "norns_session"
    session_max_age: int = 60 * 60 * 8
    auto_create_tables: bool = True

    @field_validator("encryption_key")
    @classmethod
    def encryption_key_must_be_fernet(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "ENCRYPTION_KEY is required. Generate one with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        try:
            Fernet(value.encode("utf-8"))
        except Exception as exc:
            raise ValueError("ENCRYPTION_KEY must be a valid Fernet key") from exc
        return value

    @property
    def resolved_encryption_key(self) -> str:
        return self.encryption_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
