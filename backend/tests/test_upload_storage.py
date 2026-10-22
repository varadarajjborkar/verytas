"""Upload storage: per-person and per-workspace quotas, and reclaiming uploads no version uses."""

from __future__ import annotations

import io
from datetime import timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, update

from verytas.config import Settings
from verytas.main import create_app
from verytas.media.storage import reclaim_orphans
from verytas.models import MediaBlob, utcnow


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _noise_png(seed: int, side: int = 460) -> bytes:
    # Random pixels don't compress, so the file is about side * side * 3 bytes (here a little over 0.6 MB).
    px = np.random.default_rng(seed).integers(0, 256, (side, side, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(px).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def make(tmp_path):
    clients = []

    def build(**limits) -> tuple[TestClient, dict]:
        settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'store.db'}", llm_mode="offline",
                            keys_dir=tmp_path / "keys", **limits)
        c = TestClient(create_app(settings))
        c.__enter__()
        clients.append(c)
        admin = c.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                           "admin_name": "Ada"}).json()["token"]
        tokens = {"admin": admin}
        for role in ("creator", "reviewer"):
            tokens[role] = c.post("/users", headers=_auth(admin),
                                  json={"email": f"{role}@acme.io", "name": role, "role": role}).json()["token"]
        return c, tokens

    yield build
    for c in clients:
        c.__exit__(None, None, None)


def _upload(c: TestClient, token: str, raw: bytes):
    return c.post("/media", headers=_auth(token), files={"file": ("art.png", raw, "image/png")})


def _age_all(c: TestClient, hours: float) -> None:
    async def run():
        async with c.app.state.db.sessionmaker() as s:
            await s.execute(update(MediaBlob).values(created_at=utcnow() - timedelta(hours=hours)))
            await s.commit()
    c.portal.call(run)


def _ids(c: TestClient) -> set[str]:
    async def run():
        async with c.app.state.db.sessionmaker() as s:
            return set((await s.scalars(select(MediaBlob.id))).all())
    return c.portal.call(run)


def test_one_person_cannot_upload_past_their_quota(make):
    c, t = make(upload_quota_user_mb=1)
    assert _upload(c, t["creator"], _noise_png(1)).status_code == 201
    res = _upload(c, t["creator"], _noise_png(2))
    assert res.status_code == 413
    assert "your uploads already use" in res.json()["detail"]
    # The limit is per person: a colleague in the same workspace still has room.
    assert _upload(c, t["reviewer"], _noise_png(3)).status_code == 201


def test_a_workspace_cannot_grow_past_its_quota(make):
    c, t = make(upload_quota_user_mb=10, upload_quota_workspace_mb=1)
    assert _upload(c, t["creator"], _noise_png(1)).status_code == 201
    res = _upload(c, t["reviewer"], _noise_png(2))
    assert res.status_code == 413
    assert "workspace" in res.json()["detail"]


def test_the_sweep_deletes_old_unused_uploads_and_keeps_used_and_recent_ones(make):
    c, t = make()
    used = _upload(c, t["creator"], _noise_png(1)).json()["id"]
    unused = _upload(c, t["creator"], _noise_png(2)).json()["id"]
    res = c.post("/contents?wait=true", headers=_auth(t["creator"]), json={
        "title": "Poster", "channel": "instagram", "tier": "public", "body": "New poster",
        "attachments": {"images": [{"id": "poster", "blob_id": used, "alt": "A poster"}]}})
    assert res.status_code == 201, res.text

    async def sweep(hours: float):
        async with c.app.state.db.sessionmaker() as s:
            return await reclaim_orphans(s, older_than=timedelta(hours=hours))

    # Nothing is old enough yet: an upload waiting to be sent for review is left alone.
    assert c.portal.call(sweep, 24) == 0
    _age_all(c, 48)
    assert c.portal.call(sweep, 24) == 1
    assert _ids(c) == {used} and unused not in _ids(c)
    # The piece's image is still served.
    out = res.json()
    image = c.get(f"/contents/{out['content']['id']}/versions/{out['version']['id']}/images/poster",
                  headers=_auth(t["creator"]))
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"


def test_a_refusal_clears_abandoned_uploads_first(make):
    c, t = make(upload_quota_user_mb=1, orphan_upload_ttl_h=24)
    assert _upload(c, t["creator"], _noise_png(1)).status_code == 201
    _age_all(c, 48)
    # The first upload was never used and is two days old, so it makes room instead of a refusal.
    assert _upload(c, t["creator"], _noise_png(2)).status_code == 201
    assert len(_ids(c)) == 1


def test_uploads_arriving_together_cannot_overshoot_the_quota_together(make):
    # errcheck 232: on a database that lets two transactions read before either commits (Postgres), every
    # concurrent upload could pass the same check. SQLite already serialises them (BEGIN IMMEDIATE), so
    # here this pins the behaviour; the workspace lock is what keeps it true elsewhere.
    import asyncio

    import httpx

    c, t = make(upload_quota_user_mb=1)
    files = [_noise_png(i) for i in range(3)]

    async def burst():
        transport = httpx.ASGITransport(app=c.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(*(ac.post("/media", headers=_auth(t["creator"]),
                                                  files={"file": ("art.png", raw, "image/png")}) for raw in files))

    codes = sorted(r.status_code for r in c.portal.call(burst))
    assert codes == [201, 413, 413]
