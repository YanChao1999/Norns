from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.app.database import (
    assert_fresh_schema,
    ensure_agent_config_llm_provider,
    ensure_connector_types,
    ensure_stage_auto_start,
    ensure_stage_confirm_writes,
    ensure_workspace_columns,
)


def test_assert_fresh_schema_rejects_stages_without_lane(tmp_path: Path):
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.execute(
        'CREATE TABLE stages (id TEXT PRIMARY KEY, board_id TEXT, name TEXT, "order" INTEGER, require_approval INTEGER)'
    )
    raw.commit()
    raw.close()
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn, pytest.raises(RuntimeError, match="norns init --force"):
        assert_fresh_schema(conn)
    engine.dispose()


def test_assert_fresh_schema_accepts_current_columns(tmp_path: Path):
    path = tmp_path / "fresh.db"
    raw = sqlite3.connect(path)
    raw.execute(
        'CREATE TABLE stages (id TEXT, board_id TEXT, name TEXT, "order" INTEGER, lane INTEGER, require_approval INTEGER)'
    )
    raw.commit()
    raw.close()
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        assert_fresh_schema(conn)
    engine.dispose()


def test_ensure_agent_config_llm_provider_adds_column(tmp_path: Path):
    path = tmp_path / "agents.db"
    raw = sqlite3.connect(path)
    raw.execute(
        """
        CREATE TABLE agent_configs (
            id TEXT PRIMARY KEY,
            stage_id TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            model TEXT NOT NULL,
            temperature FLOAT NOT NULL,
            tool_allowlist TEXT NOT NULL
        )
        """
    )
    raw.commit()
    raw.close()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        ensure_agent_config_llm_provider(conn)
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(agent_configs)"))}
    engine.dispose()
    assert "llm_provider" in cols


def test_ensure_workspace_columns_adds_board_and_agent_fields(tmp_path: Path):
    path = tmp_path / "workspace.db"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE boards (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
    raw.execute(
        """
        CREATE TABLE agent_configs (
            id TEXT PRIMARY KEY,
            stage_id TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            model TEXT NOT NULL,
            temperature FLOAT NOT NULL,
            tool_allowlist TEXT NOT NULL
        )
        """
    )
    raw.commit()
    raw.close()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        ensure_workspace_columns(conn)
        board_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(boards)"))}
        agent_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(agent_configs)"))}
    engine.dispose()
    assert "workspace_path" in board_cols
    assert "git_url" in board_cols
    assert "workspace_path" in agent_cols
    assert "git_url" in agent_cols


def test_ensure_stage_confirm_writes_adds_column(tmp_path: Path):
    path = tmp_path / "writes.db"
    raw = sqlite3.connect(path)
    raw.execute(
        'CREATE TABLE stages (id TEXT PRIMARY KEY, board_id TEXT, name TEXT, "order" INTEGER, lane INTEGER, require_approval INTEGER)'
    )
    raw.commit()
    raw.close()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        ensure_stage_confirm_writes(conn)
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(stages)"))}
    engine.dispose()
    assert "confirm_writes" in cols


def test_ensure_stage_auto_start_adds_column(tmp_path: Path):
    path = tmp_path / "auto.db"
    raw = sqlite3.connect(path)
    raw.execute(
        'CREATE TABLE stages (id TEXT PRIMARY KEY, board_id TEXT, name TEXT, "order" INTEGER, lane INTEGER, require_approval INTEGER)'
    )
    raw.commit()
    raw.close()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        ensure_stage_auto_start(conn)
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(stages)"))}
        # SQLite stores the portable default; dialect helper uses 0 for non-Postgres.
        default = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='stages'")).scalar()
    engine.dispose()
    assert "auto_start" in cols
    assert default is not None


def test_sql_false_uses_false_for_postgresql():
    from backend.app.database import _sql_false

    class _Dialect:
        name = "postgresql"

    class _Conn:
        dialect = _Dialect()

    assert _sql_false(_Conn()) == "FALSE"


def test_sql_false_uses_zero_for_sqlite():
    from backend.app.database import _sql_false

    class _Dialect:
        name = "sqlite"

    class _Conn:
        dialect = _Dialect()

    assert _sql_false(_Conn()) == "0"


def test_ensure_connector_types_legacy_insert(tmp_path: Path):
    path = tmp_path / "connectors.db"
    raw = sqlite3.connect(path)
    raw.execute(
        """
        CREATE TABLE connectors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            connector_type VARCHAR(8) NOT NULL CHECK (connector_type IN ('github', 'jira', 'polarion')),
            encrypted_config BLOB NOT NULL,
            is_active BOOLEAN NOT NULL
        )
        """
    )
    raw.execute("INSERT INTO connectors VALUES ('1', 'GitHub', 'github', X'00', 1)")
    raw.commit()
    raw.close()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        ensure_connector_types(conn)
        conn.execute(
            text(
                "INSERT INTO connectors (id, name, connector_type, encrypted_config, is_active) "
                "VALUES ('2', 'OpenAI', 'openai', X'00', 1), ('3', 'Cursor', 'cursor', X'00', 1), "
                "('4', 'DeepSeek', 'deepseek', X'00', 1)"
            )
        )
        names = [row[0] for row in conn.execute(text("SELECT name FROM connectors ORDER BY name"))]
    engine.dispose()
    assert names == ["Cursor", "DeepSeek", "GitHub", "OpenAI"]


def test_ensure_connector_types_widens_openai_only_check(tmp_path: Path):
    path = tmp_path / "openai-only.db"
    raw = sqlite3.connect(path)
    raw.execute(
        """
        CREATE TABLE connectors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            connector_type VARCHAR(8) NOT NULL CHECK (connector_type IN ('github', 'jira', 'polarion', 'openai')),
            encrypted_config BLOB NOT NULL,
            is_active BOOLEAN NOT NULL
        )
        """
    )
    raw.commit()
    raw.close()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        ensure_connector_types(conn)
        conn.execute(
            text(
                "INSERT INTO connectors (id, name, connector_type, encrypted_config, is_active) "
                "VALUES ('1', 'Cursor', 'cursor', X'00', 1), ('2', 'DeepSeek', 'deepseek', X'00', 1)"
            )
        )
        types = [row[0] for row in conn.execute(text("SELECT connector_type FROM connectors ORDER BY connector_type"))]
    engine.dispose()
    assert types == ["cursor", "deepseek"]
