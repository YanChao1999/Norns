from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_session
from backend.app.main import app


def _make_client() -> tuple[TestClient, object]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(_create_tables(engine))

    async def override_get_session():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app), engine


def test_board_crud():
    client, engine = _make_client()
    with client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200

        created = client.post("/api/boards", json={"name": "Platform", "description": "Delivery board"})
        assert created.status_code == 201
        board_id = created.json()["id"]

        listed = client.get("/api/boards")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.put(f"/api/boards/{board_id}", json={"name": "Platform Ops"})
        assert updated.status_code == 200
        assert updated.json()["name"] == "Platform Ops"

        deleted = client.delete(f"/api/boards/{board_id}")
        assert deleted.status_code == 204

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_board_and_agent_workspace():
    client, engine = _make_client()
    with client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200

        created = client.post(
            "/api/boards",
            json={
                "name": "Repo board",
                "workspace_path": "/tmp/board-repo",
                "git_url": "https://github.com/acme/board",
            },
        )
        assert created.status_code == 201
        board = created.json()
        assert board["workspace_path"] == "/tmp/board-repo"
        assert board["git_url"] == "https://github.com/acme/board"

        updated = client.put(
            f"/api/boards/{board['id']}",
            json={"git_url": "https://github.com/acme/board.git"},
        )
        assert updated.status_code == 200
        assert updated.json()["git_url"] == "https://github.com/acme/board.git"

        stage_id = board["stages"][0]["id"]
        stage = client.put(
            f"/api/stages/{stage_id}",
            json={"workspace_path": "/tmp/agent-repo", "git_url": "https://github.com/acme/agent"},
        )
        assert stage.status_code == 200
        config = stage.json()["agent_config"]
        assert config["workspace_path"] == "/tmp/agent-repo"
        assert config["git_url"] == "https://github.com/acme/agent"

        resolved = client.get(f"/api/workspace?board_id={board['id']}&stage_id={stage_id}")
        assert resolved.status_code == 200
        body = resolved.json()
        assert body["source"] == "agent"
        assert body["github_repo"] == "acme/agent"

        board_only = client.get(f"/api/workspace?board_id={board['id']}")
        assert board_only.json()["source"] == "board"
        assert board_only.json()["github_repo"] == "acme/board"

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_card_update_cannot_bypass_gates():
    client, engine = _make_client()
    with client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        board = client.post("/api/boards", json={"name": "Platform"}).json()
        stage_id = board["stages"][0]["id"]
        card = client.post(f"/api/boards/{board['id']}/cards", json={"title": "Work", "body": "Do it"}).json()

        skipped = client.post(
            f"/api/boards/{board['id']}/cards",
            json={"title": "Skip ahead", "current_stage_id": board["stages"][2]["id"]},
        )
        assert skipped.status_code == 201
        assert skipped.json()["current_stage_id"] == stage_id

        updated = client.put(
            f"/api/cards/{card['id']}",
            json={"title": "Work updated", "status": "done", "current_stage_id": board["stages"][1]["id"]},
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Work updated"
        assert updated.json()["status"] == "idle"
        assert updated.json()["current_stage_id"] == stage_id

        approval = client.post(f"/api/cards/{card['id']}/approve", json={"approved": True})
        assert approval.status_code == 409

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_stage_machine_crud_and_guards():
    client, engine = _make_client()
    with client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        board = client.post("/api/boards", json={"name": "Platform"}).json()
        board_id = board["id"]
        original_ids = [stage["id"] for stage in board["stages"]]

        machine = client.get("/api/orchestration/card-status")
        assert machine.status_code == 200
        body = machine.json()
        assert "idle" in body["states"]
        assert "waiting_join" in body["states"]
        assert "waiting_tool_approval" in body["states"]
        assert "waiting_tool_approval" in body["transitions"]["running"]
        assert "running" in body["transitions"]["idle"]

        created = client.post(
            f"/api/boards/{board_id}/stages",
            json={"name": "Review", "require_approval": False},
        )
        assert created.status_code == 201
        review_id = created.json()["id"]
        assert created.json()["require_approval"] is False

        reordered = client.put(
            f"/api/boards/{board_id}/stages/reorder",
            json={"stage_ids": [review_id, *original_ids]},
        )
        assert reordered.status_code == 200
        assert [stage["id"] for stage in reordered.json()] == [review_id, *original_ids]
        assert [stage["order"] for stage in reordered.json()] == [1, 2, 3, 4]

        bad_reorder = client.put(f"/api/boards/{board_id}/stages/reorder", json={"stage_ids": original_ids})
        assert bad_reorder.status_code == 400

        renamed = client.put(
            f"/api/stages/{review_id}", json={"name": "QA", "require_approval": True, "confirm_writes": True}
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "QA"
        assert renamed.json()["require_approval"] is True
        assert renamed.json()["confirm_writes"] is True

        removed = client.delete(f"/api/stages/{review_id}")
        assert removed.status_code == 204
        leftover = client.get(f"/api/boards/{board_id}/stages").json()
        assert [stage["id"] for stage in leftover] == original_ids

        card = client.post(f"/api/boards/{board_id}/cards", json={"title": "Work"}).json()
        blocked = client.delete(f"/api/stages/{card['current_stage_id']}")
        assert blocked.status_code == 409
        assert "still has cards" in blocked.json()["detail"]

        empty_stages = [stage for stage in leftover if stage["id"] != card["current_stage_id"]]
        for stage in empty_stages:
            assert client.delete(f"/api/stages/{stage['id']}").status_code == 204
        assert client.delete(f"/api/stages/{card['current_stage_id']}").status_code == 409

        empty_board = client.post("/api/boards", json={"name": "Empty machine"}).json()
        for stage in empty_board["stages"][1:]:
            assert client.delete(f"/api/stages/{stage['id']}").status_code == 204
        last_empty = client.delete(f"/api/stages/{empty_board['stages'][0]['id']}")
        assert last_empty.status_code == 409
        assert "at least one stage" in last_empty.json()["detail"]

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_transition_lines_can_go_back_and_branch_on_if():
    client, engine = _make_client()
    with client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        board = client.post("/api/boards", json={"name": "Platform"}).json()
        urd, verdandi, skuld = board["stages"]
        lines = board["transitions"]
        assert len(lines) == 3
        assert lines[0]["from_stage_id"] == urd["id"]
        assert lines[0]["to_stage_id"] == verdandi["id"]

        back = client.post(
            f"/api/boards/{board['id']}/transitions",
            json={"from_stage_id": verdandi["id"], "to_stage_id": urd["id"], "event": "reject"},
        )
        assert back.status_code == 201
        assert back.json()["event"] == "reject"
        assert back.json()["to_stage_id"] == urd["id"]

        branched = client.post(
            f"/api/boards/{board['id']}/transitions",
            json={
                "from_stage_id": skuld["id"],
                "to_stage_id": verdandi["id"],
                "event": "approve",
                "condition_key": "risk",
                "condition_op": "eq",
                "condition_value": "high",
                "order": 0,
            },
        )
        assert branched.status_code == 201
        updated = client.put(
            f"/api/transitions/{branched.json()['id']}",
            json={"condition_op": "contains", "condition_value": "high"},
        )
        assert updated.status_code == 200
        assert updated.json()["condition_op"] == "contains"

        empty_contains = client.post(
            f"/api/boards/{board['id']}/transitions",
            json={
                "from_stage_id": skuld["id"],
                "to_stage_id": urd["id"],
                "event": "approve",
                "condition_key": "summary",
                "condition_op": "contains",
                "condition_value": "",
            },
        )
        assert empty_contains.status_code == 400

        deleted = client.delete(f"/api/transitions/{back.json()['id']}")
        assert deleted.status_code == 204

        parallel = client.post(
            f"/api/boards/{board['id']}/stages",
            json={"name": "Unit tests", "parallel": True, "from_stage_id": urd["id"]},
        )
        assert parallel.status_code == 201
        assert parallel.json()["order"] == verdandi["order"]
        assert parallel.json()["lane"] >= 1
        refreshed = client.get(f"/api/boards/{board['id']}").json()
        split_lines = [
            edge
            for edge in refreshed["transitions"]
            if edge["from_stage_id"] == urd["id"] and edge["event"] == "approve" and not edge["condition_key"]
        ]
        assert len(split_lines) >= 2

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_health_reports_whether_openai_is_configured():
    client, engine = _make_client()
    with client:
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert isinstance(body["openai_configured"], bool)

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_openai_connector_can_be_created_from_settings_api():
    client, engine = _make_client()
    with client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        created = client.post(
            "/api/connectors",
            json={
                "name": "OpenAI",
                "connector_type": "openai",
                "config": {"api_key": "sk-test", "base_url": "https://api.openai.com/v1", "default_model": "gpt-4o"},
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["connector_type"] == "openai"
        assert "api_key" in body["config_keys"]
        assert "api_key" not in body["public_config"]
        assert body["public_config"]["default_model"] == "gpt-4o"
        assert "sk-test" not in created.text
        assert client.get("/api/health").json()["openai_configured"] is True
        missing = client.post("/api/connectors", json={"name": "Empty", "connector_type": "openai", "config": {}})
        assert missing.status_code == 400
        cursor = client.post(
            "/api/connectors",
            json={
                "name": "Cursor",
                "connector_type": "cursor",
                "config": {"api_key": "crsr_test", "base_url": "https://api.cursor.com/v1", "default_model": "auto"},
            },
        )
        assert cursor.status_code == 201, cursor.text
        assert cursor.json()["connector_type"] == "cursor"
        assert "api_key" not in cursor.json()["public_config"]
        deepseek = client.post(
            "/api/connectors",
            json={
                "name": "DeepSeek",
                "connector_type": "deepseek",
                "config": {
                    "api_key": "sk-deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "default_model": "deepseek-v4-flash",
                },
            },
        )
        assert deepseek.status_code == 201, deepseek.text
        assert deepseek.json()["public_config"]["default_model"] == "deepseek-v4-flash"
        empty_cursor = client.post(
            "/api/connectors", json={"name": "Empty Cursor", "connector_type": "cursor", "config": {}}
        )
        assert empty_cursor.status_code == 400
        updated = client.put(
            f"/api/connectors/{body['id']}",
            json={"config": {"api_key": "", "default_model": "gpt-4o-mini"}},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["public_config"]["default_model"] == "gpt-4o-mini"
        assert client.get("/api/health").json()["openai_configured"] is True

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_llm_models_endpoint_returns_fallback_catalog():
    client, engine = _make_client()
    with client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        response = client.get("/api/connectors/llm-models?provider=deepseek")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["provider"] == "deepseek"
        assert body["source"] == "fallback"
        assert "deepseek-v4-flash" in body["models"]
        assert body["default_model"] == "deepseek-v4-flash"
        assert any(entry["provider"] == "deepseek" and entry["id"] == "deepseek-v4-flash" for entry in body["entries"])

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_llm_models_endpoint_labels_models_by_provider():
    client, engine = _make_client()
    with client:
        client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        client.post(
            "/api/connectors",
            json={
                "name": "DeepSeek",
                "connector_type": "deepseek",
                "config": {
                    "api_key": "sk-deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "default_model": "deepseek-v4-flash",
                },
            },
        )
        client.post(
            "/api/connectors",
            json={
                "name": "Cursor",
                "connector_type": "cursor",
                "config": {"api_key": "crsr_test", "base_url": "https://api.cursor.com/v1", "default_model": "auto"},
            },
        )
        response = client.get("/api/connectors/llm-models")
        assert response.status_code == 200, response.text
        body = response.json()
        labels = {entry["label"] for entry in body["entries"]}
        assert any("DeepSeek" in label for label in labels)
        assert any("Cursor" in label for label in labels)
        cursor_auto = next(
            entry for entry in body["entries"] if entry["provider"] == "cursor" and entry["id"] == "auto"
        )
        assert cursor_auto["usable"] is True
        assert "·" in cursor_auto["label"]
        assert "Cursor" in cursor_auto["label"]

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
