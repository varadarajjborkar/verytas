from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, update
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
            # Password accounts from before tokens lapsed start their clock now rather than never lapsing.
            # A signed-out account matches too; harmless, since nobody holds a token for its hash.
            await conn.execute(update(models.User).where(models.User.password_hash.is_not(None),
                                                         models.User.token_issued_at.is_(None))
                               .values(token_issued_at=models.utcnow()))

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


def _add_missing_columns(conn) -> None:
    """Add nullable columns that models gained after a table was created.

    There are no migrations yet (Alembic comes with Postgres in deployment), and
    create_all never alters an existing table, so a local database from an
    earlier build would fail on the first new column. Only additive columns are
    handled: nullable ones, and NOT NULL ones with a plain default, which existing
    rows take. Anything else still needs a fresh database.
    """
    import logging

    from sqlalchemy import inspect

    log = logging.getLogger("verytas.db")
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have or column.primary_key:
                continue
            kind = column.type.compile(dialect=conn.dialect)
            fill = ""
            if not column.nullable:
                # A NOT NULL column with a plain default (a flag, a count, a fixed word) can be added with that
                # default written into the existing rows; anything computed still needs a fresh database.
                value = getattr(column.default, "arg", None)
                # SQLite also refuses a non-NULL default on an added REFERENCES column.
                if (column.default is None or callable(value) or column.foreign_keys
                        or not isinstance(value, bool | int | float | str)):
                    log.warning("%s.%s is new and NOT NULL without a plain default; it can't be added in place. "
                                "Start from a fresh database.", table.name, column.name)
                    continue
                literal = (str(int(value)) if isinstance(value, bool) else repr(value) if isinstance(value, int | float)
                           else "'" + value.replace("'", "''") + "'")
                fill = f" NOT NULL DEFAULT {literal}"
            fk = next(iter(column.foreign_keys), None)
            ref = f' REFERENCES "{fk.column.table.name}"("{fk.column.name}")' if fk is not None else ""
            conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}{fill}{ref}')
            if column.index:
                conn.exec_driver_sql(f'CREATE INDEX IF NOT EXISTS "ix_{table.name}_{column.name}" '
                                     f'ON "{table.name}" ("{column.name}")')
            log.info("added %s.%s to an existing database", table.name, column.name)
