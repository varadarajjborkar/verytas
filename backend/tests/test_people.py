"""Approved people: the company's record of who may appear in its content, and on what terms."""

from __future__ import annotations

from datetime import date

from tests.media_fixtures import b64, png, text_image
from tests.test_media import _auth, world  # noqa: F401, the fixture is used by name
from verytas.checks.likeness import PersonView, licence

TODAY = date(2026, 10, 23)


def _view(**kw) -> PersonView:
    return PersonView(**{"id": 1, "name": "Riya Sen", "kind": "celebrity", "valid_from": date(2026, 1, 1)} | kw)


def test_licence_follows_the_agreement():
    assert licence(_view(), channel="instagram", event_id=None, on=TODAY, author_id=5)[0]
    ended = licence(_view(valid_to=date(2026, 6, 30)), channel="instagram", event_id=None, on=TODAY, author_id=5)
    assert ended == (False, "the agreement with Riya Sen ended on 2026-06-30")
    early = licence(_view(valid_from=date(2026, 11, 1)), channel="x", event_id=None, on=TODAY, author_id=5)
    assert not early[0] and "starts on 2026-11-01" in early[1]
    wrong_channel = licence(_view(channels=("YouTube",)), channel="instagram", event_id=None, on=TODAY, author_id=5)
    assert not wrong_channel[0] and "covers YouTube, not instagram" in wrong_channel[1]
    assert licence(_view(channels=("Instagram",)), channel="instagram", event_id=None, on=TODAY, author_id=5)[0]
    assert not licence(_view(event_ids=(3,)), channel="x", event_id=4, on=TODAY, author_id=5)[0]
    assert not licence(_view(active=False), channel="x", event_id=None, on=TODAY, author_id=5)[0]


def test_a_creators_face_belongs_in_their_own_posts_only():
    me = _view(kind="creator", name="Aisha Khan", user_id=7)
    own = licence(me, channel="x", event_id=None, on=TODAY, author_id=7)
    assert own == (True, "Aisha Khan appears in their own post")
    assert not licence(me, channel="x", event_id=None, on=TODAY, author_id=8)[0]


def test_the_brand_team_records_people_and_creators_register_only_themselves(client, world):  # noqa: F811
    admin, creator = _auth(world["admin"]), _auth(world["creator"])
    riya = client.post("/people", headers=admin, json={
        "name": "Riya Sen", "kind": "celebrity", "channels": ["instagram"], "valid_from": "2026-01-01",
        "valid_to": "2026-12-31", "tier": "public"})
    assert riya.status_code == 201, riya.text
    assert client.post("/people", headers=creator, json={
        "name": "Someone Famous", "kind": "celebrity", "valid_from": "2026-01-01"}).status_code == 403
    me = client.post("/people/me", headers=creator)
    assert me.status_code == 201 and me.json()["kind"] == "creator" and me.json()["user_id"] is not None
    assert client.post("/people/me", headers=creator).json()["id"] == me.json()["id"]  # one record per creator

    photo = {"media_type": "image/png", "data_base64": b64(png(text_image(["face"], size=(300, 300))))}
    assert client.post(f"/people/{me.json()['id']}/references", headers=creator, json=photo).status_code == 201
    assert client.post(f"/people/{riya.json()['id']}/references", headers=creator, json=photo).status_code == 403
    web = client.post(f"/people/{riya.json()['id']}/references", headers=admin,
                      json=photo | {"source": "web", "source_url": "https://commons.wikimedia.org/wiki/File:x.jpg"})
    assert web.status_code == 201 and web.json()["source_url"].startswith("https://commons")
    listed = {p["name"]: p for p in client.get("/people", headers=creator).json()}
    assert len(listed["Riya Sen"]["references"]) == 1
    rid = listed["Riya Sen"]["references"][0]["id"]
    img = client.get(f"/people/{riya.json()['id']}/references/{rid}/image", headers=creator)
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"


def test_an_agreement_cannot_end_before_it_starts(client, world):  # noqa: F811
    res = client.post("/people", headers=_auth(world["admin"]), json={
        "name": "X", "kind": "ambassador", "valid_from": "2026-05-01", "valid_to": "2026-04-01"})
    assert res.status_code == 422


def test_nulling_a_list_or_switch_is_refused_and_the_list_still_reads(client, world):  # noqa: F811
    # errcheck 241: a null saved here made every later GET /people a 500.
    admin = _auth(world["admin"])
    p = client.post("/people", headers=admin, json={"name": "X", "kind": "ambassador", "valid_from": "2026-01-01"})
    for field in ("aliases", "channels", "event_ids", "active"):
        assert client.patch(f"/people/{p.json()['id']}", headers=admin, json={field: None}).status_code == 422
    assert client.patch(f"/people/{p.json()['id']}", headers=admin, json={"valid_to": None}).status_code == 200
    assert client.get("/people", headers=admin).status_code == 200


def test_agreement_notes_are_for_the_brand_team(client, world):  # noqa: F811
    client.post("/people", headers=_auth(world["admin"]), json={
        "name": "Riya Sen", "kind": "celebrity", "valid_from": "2026-01-01", "notes": "Fee 40 lakh", "tier": "public"})
    seen = {p["name"]: p for p in client.get("/people", headers=_auth(world["creator"])).json()}
    assert seen["Riya Sen"]["notes"] is None
    admin_seen = {p["name"]: p for p in client.get("/people", headers=_auth(world["admin"])).json()}
    assert admin_seen["Riya Sen"]["notes"] == "Fee 40 lakh"


def test_the_same_person_entered_twice_is_one_person(client):
    from tests.test_media import _auth

    admin = client.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                            "admin_name": "Ada"}).json()["token"]
    body = {"name": "Riya Kapoor", "kind": "ambassador", "valid_from": "2026-10-01"}
    assert client.post("/people", headers=_auth(admin), json=body | {"name": "Riya Kapoor  "}).status_code == 201
    again = client.post("/people", headers=_auth(admin), json=body | {"name": " riya kapoor "})
    assert again.status_code == 409
    listed = client.get("/people", headers=_auth(admin)).json()
    assert [p["name"] for p in listed] == ["Riya Kapoor"]
    assert client.post("/people", headers=_auth(admin), json=body | {"name": "   "}).status_code == 422
