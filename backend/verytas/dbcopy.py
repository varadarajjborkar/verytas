"""Copy every table from one database to another, schema first.

The demo is seeded into SQLite (the seed drives the API through a test client and a simulated clock, which
is quick on a laptop and slow on a free-tier box), then copied into the hosted Postgres. Rows go across in
foreign-key order through the models' own column types, so timestamps, JSON and booleans come out as
Postgres expects rather than as SQLite stored them.

The target is emptied first. Nothing here is meant for a database that holds data worth keeping.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from verytas.db import Base, make_engine

_BATCH = 500


async def copy_database(source_url: str, target_url: str) -> dict[str, int]:
    from verytas import models  # noqa: F401  (registers every table on Base)

    if source_url == target_url or target_url.startswith("sqlite"):
        raise SystemExit("the target must be a different, Postgres database: it is emptied first")

    source, target = make_engine(source_url), make_engine(target_url)
    counts: dict[str, int] = {}
    try:
        async with target.begin() as dst:
            await dst.run_sync(Base.metadata.drop_all)
            await dst.run_sync(Base.metadata.create_all)
        async with source.connect() as src, target.begin() as dst:
            for table in Base.metadata.sorted_tables:
                aware = [c.name for c in table.columns if isinstance(c.type, DateTime) and c.type.timezone]
                rows = [_as_utc(dict(r), aware) for r in (await src.execute(select(table))).mappings().all()]
                for i in range(0, len(rows), _BATCH):
                    await dst.execute(table.insert(), rows[i:i + _BATCH])
                counts[table.name] = len(rows)
            if dst.dialect.name == "postgresql":
                await _reset_sequences(dst)
    finally:
        await source.dispose()
        await target.dispose()
    return counts


def _as_utc(row: dict, columns: list[str]) -> dict:
    """SQLite hands timestamps back naive, and they are UTC. Postgres reads a naive value for a timestamptz
    column in the session's zone, so a copy run from India moved every time by five and a half hours."""
    for name in columns:
        value = row.get(name)
        if isinstance(value, datetime) and value.tzinfo is None:
            row[name] = value.replace(tzinfo=UTC)
    return row


async def _reset_sequences(conn: AsyncConnection) -> None:
    """Rows were inserted with their ids, so each serial sequence still starts at 1; move it past the max."""
    for table in Base.metadata.sorted_tables:
        for col in table.primary_key.columns:
            if col.autoincrement is False or not isinstance(col.type, Integer):
                continue
            top = (await conn.execute(select(func.max(col)))).scalar()
            if top is None:
                continue
            seq = (await conn.execute(text("SELECT pg_get_serial_sequence(:t, :c)"),
                                      {"t": table.name, "c": col.name})).scalar()
            if seq:
                await conn.execute(text("SELECT setval(:s, :v)"), {"s": seq, "v": top})


def main(argv: list[str]) -> None:
    source_url, target_url = argv
    counts = asyncio.run(copy_database(source_url, target_url))
    sys.stdout.write(f"copied {sum(counts.values())} rows across {len(counts)} tables\n")


if __name__ == "__main__":
    main(sys.argv[1:])
