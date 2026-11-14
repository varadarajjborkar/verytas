from __future__ import annotations

from datetime import UTC, datetime

import pytest

from verytas.dbcopy import _as_utc, copy_database


def test_naive_sqlite_times_are_marked_utc_before_postgres_reads_them_in_its_own_zone():
    naive = datetime(2026, 9, 22, 1, 12, 29)
    row = _as_utc({"created_at": naive, "title": "x", "done_at": None}, ["created_at", "done_at"])
    assert row["created_at"] == naive.replace(tzinfo=UTC) and row["done_at"] is None and row["title"] == "x"


async def test_the_target_must_be_another_postgres_database():
    with pytest.raises(SystemExit):
        await copy_database("sqlite+aiosqlite:///a.db", "sqlite+aiosqlite:///b.db")
    with pytest.raises(SystemExit):
        await copy_database("postgresql+asyncpg://h/db", "postgresql+asyncpg://h/db")
