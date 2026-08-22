import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.models.connector import Connector, ConnectorType


def test_connector_config_round_trip():
    connector = Connector(name="gh", connector_type=ConnectorType.GITHUB, encrypted_config=b"")
    connector.set_config({"token": "secret", "base_url": "https://github.example"})
    assert connector.get_config()["token"] == "secret"
    assert connector.config_keys == ["base_url", "token"]


@pytest.mark.parametrize("value", ["", "   ", "not-a-fernet-key"])
def test_encryption_key_must_be_valid_fernet(value: str):
    with pytest.raises(ValidationError):
        Settings(encryption_key=value)
