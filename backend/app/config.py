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
    secret_key: str = Field(default="", alias="SECRET_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    default_model: str = Field(default="gpt-4o", alias="DEFAULT_MODEL")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin", alias="ADMIN_PASSWORD")
    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")
    session_cookie_name: str = "norns_session"
    session_max_age: int = 60 * 60 * 8
    session_cookie_secure: bool = Field(default=False, alias="SESSION_COOKIE_SECURE")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )
    plantuml_url: str = Field(default="", alias="PLANTUML_URL")
    kroki_url: str = Field(default="", alias="KROKI_URL")
    auto_create_tables: bool = True
    queue_backend: str = Field(default="redis", alias="QUEUE_BACKEND")

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

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_set(cls, value: str) -> str:
        if not value.strip() or value.strip() == "changeme":
            raise ValueError("SECRET_KEY is required and must not be the default 'changeme'")
        return value

    @property
    def resolved_encryption_key(self) -> str:
        return self.encryption_key

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
