"""Async SQLite access. No repository abstraction (HERMES_DESIGN §11.2) — stages
use the session directly.
"""

from __future__ import annotations


from sqlalchemy import Engine, inspect, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from hermes.storage.models import Base

SCHEMA_VERSION = 2


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _conn_record):  # pragma: no cover - sync engine only
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def make_engine(sqlite_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(sqlite_url, echo=echo, future=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Forward-migrate existing DBs when columns are added (no Alembic).
    await _add_missing_columns(engine)


async def _add_missing_columns(engine: AsyncEngine) -> None:
    def _migrate(sync_conn):
        inspector = inspect(sync_conn)
        for table in Base.metadata.tables.values():
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    col_type = col.type.compile(engine.dialect)
                    sync_conn.execute(
                        text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}')
                    )

    async with engine.begin() as conn:
        await conn.run_sync(_migrate)


class Store:
    """Thin owner of engine + session factory + schema bootstrap."""

    def __init__(self, sqlite_url: str, *, echo: bool = False):
        self.engine = make_engine(sqlite_url, echo=echo)
        self.session_factory = make_session_factory(self.engine)

    async def init(self) -> None:
        await create_schema(self.engine)

    def session(self) -> AsyncSession:
        return self.session_factory()

    async def close(self) -> None:
        await self.engine.dispose()
