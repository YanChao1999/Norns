from types import SimpleNamespace

import pytest

from backend.app.models.connector import Connector, ConnectorType
from backend.app.tools.polarion import PolarionClient, _polarion_client, polarion_provider


def _connector() -> Connector:
    connector = Connector(name="Polarion", connector_type=ConnectorType.POLARION, encrypted_config=b"", is_active=True)
    connector.set_config(
        {"server": "https://polarion.example", "username": "user", "password": "secret", "project": "5E96"}
    )
    return connector


def test_polarion_client_class_is_the_library_client():
    assert PolarionClient is not None
    assert PolarionClient.__name__ == "Polarion"
    assert PolarionClient.__module__ == "polarion.polarion"


def test_polarion_client_requires_password_or_token():
    connector = Connector(name="Polarion", connector_type=ConnectorType.POLARION, encrypted_config=b"", is_active=True)
    connector.set_config({"server": "https://polarion.example", "username": "user"})
    with pytest.raises(ValueError, match="password or token"):
        _polarion_client(connector)


def test_polarion_create_workitem_tool_is_registered():
    names = {tool.name for tool in polarion_provider([_connector()])}
    assert "polarion_polarion_create_workitem" in names


@pytest.mark.asyncio
async def test_polarion_create_workitem_sets_description_and_parent(monkeypatch):
    created = SimpleNamespace(
        id="5E96-900",
        title="Norns shall record stage handoffs",
        type=SimpleNamespace(id="softwarerequirement"),
        status=SimpleNamespace(id="draft"),
        description=None,
        linked=None,
    )

    def set_description(value: str) -> None:
        created.description = SimpleNamespace(content=value)

    def add_linked_item(parent: object, role: str) -> None:
        created.linked = (getattr(parent, "id", None), role)

    created.setDescription = set_description
    created.addLinkedItem = add_linked_item
    created.getDescription = lambda: created.description.content if created.description else None

    parent = SimpleNamespace(id="5E96-147")
    calls: list[tuple[str, dict[str, str]]] = []

    def create_workitem(workitem_type: str, new_workitem_fields=None):
        calls.append((workitem_type, dict(new_workitem_fields or {})))
        return created

    project = SimpleNamespace(
        createWorkitem=create_workitem, getWorkitem=lambda item_id: parent if item_id == "5E96-147" else created
    )
    monkeypatch.setattr("backend.app.tools.polarion._polarion_project", lambda connector: project)

    tool = next(item for item in polarion_provider([_connector()]) if item.name.endswith("create_workitem"))
    result = await tool.execute(
        {
            "title": "Norns shall record stage handoffs",
            "description": "Handoffs are stored on the card.",
            "type": "softwarerequirement",
            "parent_id": "5E96-147",
        }
    )
    assert result["id"] == "5E96-900"
    assert result["parent_id"] == "5E96-147"
    assert "Handoffs" in result["description"]
    assert created.linked == ("5E96-147", "relates_to")
    assert calls == [("softwarerequirement", {"title": "Norns shall record stage handoffs"})]
