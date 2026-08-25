from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from backend.app.database import assert_fresh_schema


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
