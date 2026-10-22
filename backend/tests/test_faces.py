"""Faces in content against the brand's approved people, with the face models replaced by fixed
descriptions so the decisions are tested exactly and offline."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.media_fixtures import b64, png, text_image
from tests.test_media import _auth
from verytas.config import Settings
from verytas.main import create_app
from verytas.media import faces as face_model

RIYA, AISHA, STRANGER = np.eye(128, dtype=np.float32)[0], np.eye(128, dtype=np.float32)[1], np.eye(128)[2]


def _photo(word: str) -> str:
    return b64(png(text_image([word], size=(300, 300))))


@pytest.fixture
def faces(tmp_path, monkeypatch):
    """A client with the faces check on; each test says which description the post's face has."""
    shown = {"vector": RIYA, "side": 260}
    by_photo = {"riya": RIYA, "aisha": AISHA}

    def find(img, folder, **_):
        return [face_model.Face((100, 100, 100 + shown["side"], 100 + shown["side"]), 0.99, np.zeros(15),
                                embedding=shown["vector"])]

    def describe(img, folder):
        # Reference photos are text images with the person's key drawn on them; read it back by size.
        key = img.info.get("who") or next((k for k in by_photo if k in getattr(img, "filename", "")), None)
        return by_photo.get(key) if key else RIYA if img.size == (300, 300) else None

    monkeypatch.setattr(face_model, "find", find)
    monkeypatch.setattr(face_model, "describe", describe)
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'f.db'}", llm_mode="offline",
                        keys_dir=tmp_path / "keys", faces_enabled=True, vision_models_dir=tmp_path / "models")
    with TestClient(create_app(settings)) as c:
        admin = c.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                           "admin_name": "Ada"}).json()["token"]
        creator = c.post("/users", headers=_auth(admin),
                         json={"email": "c@acme.io", "name": "Aisha", "role": "creator"}).json()["token"]
        yield c, admin, creator, shown


def _register(c, admin, **person):
    p = c.post("/people", headers=_auth(admin), json={"kind": "celebrity", "valid_from": "2026-01-01",
                                                     "tier": "public", **person}).json()
    c.post(f"/people/{p['id']}/references", headers=_auth(admin), json={"media_type": "image/png",
                                                                      "data_base64": _photo("ref")})
    return p


def _review(c, creator, tier="public"):
    res = c.post("/contents?wait=true", headers=_auth(creator), json={
        "title": "Ad", "channel": "instagram", "tier": tier, "body": "Festive offer",
        "attachments": {"images": [{"id": "ad", "alt": "Our ambassador with the offer",
                                    "data_base64": _photo("ad")}]},
        "creator_notes": {"brief": "Riya Sen holds the offer card"}})
    assert res.status_code == 201, res.text
    return c.get(f"/reviews/{res.json()['review_id']}", headers=_auth(creator)).json()


def _likeness(review):
    return [f for f in review["findings"] if f["checker"] == "faces"]


def test_a_licensed_ambassador_passes(faces):
    c, admin, creator, _ = faces
    _register(c, admin, name="Riya Sen", channels=["instagram"])
    assert _likeness(_review(c, creator)) == []


def test_an_expired_agreement_is_a_blocker_with_its_date(faces):
    c, admin, creator, _ = faces
    _register(c, admin, name="Riya Sen", valid_to="2026-06-30")
    found = _likeness(_review(c, creator))
    assert len(found) == 1 and "isn't licensed" in found[0]["title"]
    assert "ended on 2026-06-30" in found[0]["explanation"]
    assert found[0]["level"] == "blocker" and len(found[0]["locator"]["box"]) == 4


def test_a_prominent_stranger_is_a_warning_and_a_small_one_is_ignored(faces):
    c, admin, creator, shown = faces
    _register(c, admin, name="Riya Sen")
    shown["vector"] = STRANGER
    found = _likeness(_review(c, creator))
    assert [f["title"] for f in found] == ["A person appears who isn't identified"]
    shown["side"] = 30  # a passer-by in the background, under a tenth of the picture
    assert _likeness(_review(c, creator)) == []


def test_a_creators_own_unapproved_photo_identifies_nobody(faces, monkeypatch):
    # errcheck 243: a creator could otherwise register a celebrity's face as their own and be cleared.
    c, admin, creator, _ = faces
    me = c.post("/people/me", headers=_auth(creator)).json()
    ref = c.post(f"/people/{me['id']}/references", headers=_auth(creator),
                 json={"media_type": "image/png", "data_base64": _photo("me")}).json()
    assert ref["approved"] is False
    assert [f["title"] for f in _likeness(_review(c, creator))] == ["A person appears who isn't identified"]
    c.patch(f"/people/{me['id']}/references/{ref['id']}", headers=_auth(admin), json={"approved": True})
    assert _likeness(_review(c, creator)) == []


def test_a_confidential_brief_never_sends_names_out(faces, monkeypatch):
    # A name in a confidential brief can itself be the secret (an unannounced deal).
    import verytas.services.references as refs

    looked: list[str] = []

    async def record(name, **_):
        looked.append(name)

    monkeypatch.setattr(refs, "find_portrait", record)
    c, admin, _, shown = faces
    shown["vector"] = STRANGER
    c.app.state.settings.llm_mode = "live"  # lookups only happen live; no keys, so models stay offline
    _review(c, admin, tier="internal")
    assert looked == ["Riya Sen"]  # the control: an ordinary piece does look the named person up
    looked.clear()
    _review(c, admin, tier="confidential")
    assert looked == []
