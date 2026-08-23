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
        await conn.run_sync(_ensure_columns)


def _ensure_columns(sync_conn) -> None:
    columns = [
        ("stages", "lane", "INTEGER DEFAULT 0 NOT NULL"),
        ("cards", "parent_card_id", "VARCHAR(36)"),
    ]
    for table, column, ddl in columns:
        if column in _table_columns(sync_conn, table):
            continue
        sync_conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _table_columns(sync_conn, table: str) -> set[str]:
    inspector = inspect(sync_conn)
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}
