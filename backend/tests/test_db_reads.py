"""A request that only reads doesn't take SQLite's write lock, so page loads don't wait on each other or on a
review being written; a request that writes still takes it up front (db.py)."""

from __future__ import annotations

from sqlalchemy import event

from tests.test_media import _auth, world  # noqa: F401  (the fixture is used by name)
from verytas.db import READ


def test_a_get_reads_without_the_write_lock_and_a_post_takes_it(client, world):  # noqa: F811
    seen: list[bool] = []
    engine = client.app.state.db.engine.sync_engine

    def began(conn):
        seen.append(bool(conn.get_execution_options().get(READ)))

    event.listen(engine, "begin", began)
    try:
        assert client.get("/me", headers=_auth(world["creator"])).status_code == 200
        reads, seen[:] = list(seen), []
        made = client.post("/contents", headers=_auth(world["creator"]),
                           json={"title": "T", "channel": "instagram", "body": "Launch post"})
        assert made.status_code == 201, made.text
    finally:
        event.remove(engine, "begin", began)
    assert reads and all(reads)
    assert seen and not seen[0]
