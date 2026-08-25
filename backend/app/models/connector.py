from __future__ import annotations

import json
from enum import Enum
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import Enum as SAEnum
from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..config import get_settings
from ..database import Base

SECRET_CONFIG_KEYS = frozenset({"api_key", "token", "password"})


class ConnectorType(str, Enum):
    OPENAI = "openai"
    CURSOR = "cursor"
    DEEPSEEK = "deepseek"
    GITHUB = "github"
    JIRA = "jira"
    POLARION = "polarion"


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[ConnectorType] = mapped_column(
        SAEnum(ConnectorType, name="connector_type", native_enum=False),
        nullable=False,
    )
    encrypted_config: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    @staticmethod
    def _fernet() -> Fernet:
        return Fernet(get_settings().resolved_encryption_key.encode("utf-8"))

    def set_config(self, config: dict) -> None:
        payload = json.dumps(config).encode("utf-8")
        self.encrypted_config = self._fernet().encrypt(payload)

    def get_config(self) -> dict:
        decrypted = self._fernet().decrypt(self.encrypted_config)
        return json.loads(decrypted.decode("utf-8"))

    @property
    def config_keys(self) -> list[str]:
        return sorted(self.get_config().keys()) if self.encrypted_config else []

    @property
    def public_config(self) -> dict[str, str]:
        if not self.encrypted_config:
            return {}
        config = self.get_config()
        return {
            key: str(value)
            for key, value in config.items()
            if key not in SECRET_CONFIG_KEYS and value not in (None, "")
        }
