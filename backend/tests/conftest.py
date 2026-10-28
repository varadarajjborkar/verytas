from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from verytas.config import Settings
from verytas.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        llm_mode="offline",
        keys_dir=tmp_path / "keys",
        # The face models are fetched on first use; the suite stays offline (tests/test_faces.py opts in).
        faces_enabled=False,
        db_guard_reads=True,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c
