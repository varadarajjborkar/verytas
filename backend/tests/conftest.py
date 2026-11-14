from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from verytas.config import Settings
from verytas.main import create_app


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "sqlite_file: opens the test database file directly; skipped on Postgres")


def pytest_collection_modifyitems(config, items) -> None:
    if not os.environ.get("VERYTAS_TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="reads the SQLite file directly")
    for item in items:
        if "sqlite_file" in item.keywords:
            item.add_marker(skip)


def _fresh_postgres(url: str) -> str:
    """The hosted demo runs on Postgres. VERYTAS_TEST_DATABASE_URL points the suite at a throwaway one,
    emptied before every test the way a new SQLite file starts empty. Tests run one at a time on it."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    async def reset() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())
    return url


@pytest.fixture
def settings(tmp_path) -> Settings:
    pg = os.environ.get("VERYTAS_TEST_DATABASE_URL")
    return Settings(
        database_url=_fresh_postgres(pg) if pg else f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        db_null_pool=bool(pg),
        llm_mode="offline",
        keys_dir=tmp_path / "keys",
        # The face models are fetched on first use; the suite stays offline (tests/test_faces.py opts in).
        faces_enabled=False,
        db_guard_reads=True,
        # Model-free embeddings and a per-test memory store: the suite stays offline and isolated.
        memory_embed_model="hash",
        memory_dir=tmp_path / "memory",
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c
