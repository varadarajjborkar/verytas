from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> AsyncEngine:
    sqlite = url.startswith("sqlite")
    # Background reviews write while requests write. SQLite's default is to
    # fail at once on a held lock ("database is locked" -> 500); wait instead.
    engine = create_async_engine(url, future=True, connect_args={"timeout": 30} if sqlite else {})
    if sqlite:
        # SQLite ignores FK and CHECK-adjacent integrity unless asked; we lean on
        # those constraints (citations, version chain), so turn them on. WAL keeps
        # a crashed writer from corrupting the file and makes commits cheaper.
        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
            # Take over BEGIN from the driver (see _begin_immediate).
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            if ":memory:" not in url:
                cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        # A deferred transaction that reads first and writes later can't be
        # upgraded once another writer has committed: SQLite fails it at once
        # with "database is locked", ignoring busy_timeout, because waiting
        # could deadlock. Found by the black-box simulator at 8+ parallel
        # submissions. Taking the write lock up front makes contention wait.
        #
        # The price is that SQLite transactions, read-only ones included, run
        # one at a time. That is acceptable because SQLite is the local and demo
        # store, every transaction here is short (none spans a model call), and
        # Postgres in deployment never takes this path.
        @event.listens_for(engine.sync_engine, "begin")
        def _begin_immediate(conn):  # pragma: no cover - driver hook
            conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


class Database:
    def __init__(self, url: str) -> None:
        self.engine = make_engine(url)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        # Imported for its side effect of registering every table on Base.
        from verytas import models  # noqa: F401

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_add_missing_columns)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


def _add_missing_columns(conn) -> None:
    """Add nullable columns that models gained after a table was created.

    There are no migrations yet (Alembic comes with Postgres in deployment), and
    create_all never alters an existing table, so a local database from an
    earlier build would fail on the first new column. Only additive, nullable
    columns are handled; anything else still needs a fresh database.
    """
    from sqlalchemy import inspect

    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have or not column.nullable or column.primary_key:
                continue
            kind = column.type.compile(dialect=conn.dialect)
            conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}')
