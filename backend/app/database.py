from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import inspect
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
        await conn.run_sync(assert_fresh_schema)


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
