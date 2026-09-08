from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(ensure_connector_types)
        await conn.run_sync(ensure_agent_config_llm_provider)
        await conn.run_sync(ensure_workspace_columns)
        await conn.run_sync(ensure_stage_confirm_writes)
        await conn.run_sync(ensure_stage_auto_start)
        await conn.run_sync(assert_fresh_schema)


REQUIRED_CONNECTOR_TYPES = ("openai", "cursor", "deepseek", "mcp", "workspace", "polarion")


def ensure_connector_types(sync_conn) -> None:
    """Existing DBs CHECK connector_type without newer providers; create_all will not widen it."""
    inspector = inspect(sync_conn)
    if not inspector.has_table("connectors"):
        return
    dialect = sync_conn.dialect.name
    if dialect == "sqlite":
        ddl = sync_conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='connectors'")).scalar()
        if not ddl or "check" not in ddl.lower() or not _connector_ddl_missing_types(ddl):
            return
        from .models.connector import Connector

        sync_conn.execute(text("ALTER TABLE connectors RENAME TO connectors_legacy_types"))
        Connector.__table__.create(sync_conn)
        columns = "id, name, connector_type, encrypted_config, is_active"
        sync_conn.execute(text(f"INSERT INTO connectors ({columns}) SELECT {columns} FROM connectors_legacy_types"))
        sync_conn.execute(text("DROP TABLE connectors_legacy_types"))
        return
    if dialect == "postgresql":
        for constraint in inspector.get_check_constraints("connectors"):
            sqltext = str(constraint.get("sqltext") or "")
            name = constraint.get("name")
            if name and "connector_type" in sqltext and _connector_ddl_missing_types(sqltext):
                sync_conn.execute(text(f'ALTER TABLE connectors DROP CONSTRAINT "{name}"'))


def _connector_ddl_missing_types(ddl: str) -> bool:
    lowered = ddl.lower()
    return any(name not in lowered for name in REQUIRED_CONNECTOR_TYPES)


def ensure_openai_connector_type(sync_conn) -> None:
    ensure_connector_types(sync_conn)


def ensure_agent_config_llm_provider(sync_conn) -> None:
    """create_all does not add columns to existing agent_configs tables."""
    inspector = inspect(sync_conn)
    if not inspector.has_table("agent_configs"):
        return
    present = {column["name"] for column in inspector.get_columns("agent_configs")}
    if "llm_provider" in present:
        return
    sync_conn.execute(text("ALTER TABLE agent_configs ADD COLUMN llm_provider VARCHAR(32) NOT NULL DEFAULT ''"))


def ensure_workspace_columns(sync_conn) -> None:
    """create_all does not add git workspace columns to existing boards / agent_configs."""
    inspector = inspect(sync_conn)
    specs = {
        "boards": (
            ("workspace_path", "VARCHAR(1024) NOT NULL DEFAULT ''"),
            ("git_url", "VARCHAR(1024) NOT NULL DEFAULT ''"),
        ),
        "agent_configs": (
            ("workspace_path", "VARCHAR(1024) NOT NULL DEFAULT ''"),
            ("git_url", "VARCHAR(1024) NOT NULL DEFAULT ''"),
        ),
    }
    for table, columns in specs.items():
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name, ddl in columns:
            if name not in present:
                sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def ensure_stage_confirm_writes(sync_conn) -> None:
    inspector = inspect(sync_conn)
    if not inspector.has_table("stages"):
        return
    present = {column["name"] for column in inspector.get_columns("stages")}
    if "confirm_writes" not in present:
        sync_conn.execute(text("ALTER TABLE stages ADD COLUMN confirm_writes BOOLEAN NOT NULL DEFAULT 0"))


def ensure_stage_auto_start(sync_conn) -> None:
    inspector = inspect(sync_conn)
    if not inspector.has_table("stages"):
        return
    present = {column["name"] for column in inspector.get_columns("stages")}
    if "auto_start" not in present:
        sync_conn.execute(text("ALTER TABLE stages ADD COLUMN auto_start BOOLEAN NOT NULL DEFAULT 0"))


def assert_fresh_schema(sync_conn) -> None:
    """create_all does not add columns. Pre-0.0.1 SQLite files must be wiped."""
    inspector = inspect(sync_conn)
    required = {
        "stages": ("lane",),
        "stage_transitions": ("event", "condition_key", "condition_op", "condition_value", "order"),
    }
    missing: list[str] = []
    for table, columns in required.items():
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        missing.extend(f"{table}.{name}" for name in columns if name not in present)
    if missing:
        raise RuntimeError(
            "This Norns database predates 0.0.1 (missing "
            + ", ".join(missing)
            + "). There is no in-place upgrade yet. Wipe it with: norns init --force"
        )
