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


def test_polarion_client_prefers_token_auth(monkeypatch):
    captured: dict[str, object] = {}

    def fake_client(server, user, password=None, token=None, **kwargs):
        captured.update(server=server, user=user, password=password, token=token)
        return object()

    monkeypatch.setattr("backend.app.tools.polarion.PolarionClient", fake_client)
    connector = Connector(name="Polarion", connector_type=ConnectorType.POLARION, encrypted_config=b"", is_active=True)
    connector.set_config(
        {
            "server": "https://polarion.example",
            "username": "alice",
            "password": "secret",
            "token": "pat-1",
            "project": "5E96",
        }
    )
    _polarion_client(connector)
    assert captured["token"] == "pat-1"
    assert captured["password"] is None
    assert captured["user"] == "alice"


def test_polarion_password_jwt_uses_token_login(monkeypatch):
    captured: dict[str, object] = {}
    jwt = "a." + ("b" * 40) + "." + ("c" * 40)

    def fake_client(server, user, password=None, token=None, **kwargs):
        captured.update(server=server, user=user, password=password, token=token)
        return object()

    monkeypatch.setattr("backend.app.tools.polarion.PolarionClient", fake_client)
    connector = Connector(name="Polarion", connector_type=ConnectorType.POLARION, encrypted_config=b"", is_active=True)
    connector.set_config(
        {
            "server": "https://testdrive.polarion.com/polarion/#/home",
            "username": "5e9628e6e8524472b8b92c47eb7e785a",
            "password": jwt,
            "project": "5E96",
        }
    )
    _polarion_client(connector)
    assert captured["server"] == "https://testdrive.polarion.com/polarion"
    assert captured["token"] == jwt
    assert captured["password"] is None


def test_polarion_project_retries_workitem_prefix(monkeypatch):
    from backend.app.tools.polarion import _polarion_project

    calls: list[str] = []

    class FakeClient:
        def getProject(self, project_id: str):
            calls.append(project_id)
            if project_id == "5E96":
                return SimpleNamespace(id=project_id)
            raise Exception(f"Could not find project {project_id}")

    monkeypatch.setattr("backend.app.tools.polarion._polarion_client", lambda connector: FakeClient())
    user = "5e9628e6e8524472b8b92c47eb7e785a"
    connector = Connector(name="Polarion", connector_type=ConnectorType.POLARION, encrypted_config=b"", is_active=True)
    connector.set_config(
        {"server": "https://testdrive.polarion.com/polarion", "username": user, "password": "secret", "project": user}
    )
    project = _polarion_project(connector, hint_id="5E96-147")
    assert project.id == "5E96"
    assert calls == [user, "5E96"]


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
    monkeypatch.setattr("backend.app.tools.polarion._polarion_project", lambda connector, hint_id="": project)

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
