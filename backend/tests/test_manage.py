"""The manager's side: the brand library, brand-book import and a piece's shared timeline."""

from __future__ import annotations

from tests.media_fixtures import b64, mascot_face, png
from tests.test_api_flow import _auth
from tests.test_api_flow import world as world  # noqa: F401, the fixture is used by name
from verytas.models import Tier
from verytas.prism.rulebook import heuristic_rules, to_rules

BOOK = """Our voice
We were founded in 2019.
Always write in a warm, plain voice.
Never promise results we can't prove.
Say "sign in", not "login".
Use alt text on every image.
"""


def test_offline_reading_finds_directives_and_term_swaps():
    found = heuristic_rules(BOOK)
    texts = [p.text for p in found]
    assert "We were founded in 2019." not in texts, "background is not a rule"
    swap = next(p for p in found if p.kind == "deterministic")
    assert swap.pattern == {"type": "preferred_terms", "map": {"login": "sign in"}}
    assert {p.severity for p in found if p.text.startswith(("Always", "Never"))} == {"must"}
    assert next(p for p in found if "alt text" in p.text).category == "accessibility"

    rules, notes = to_rules(found, {"BB-TONE-1"}, "Brand book p.2")
    codes = [r.code for r in rules]
    assert "BB-TONE-1" not in codes and len(codes) == len(set(codes))
    assert all(r.source_ref == "Brand book p.2" for r in rules) and notes == []
    # Public posts are what a brand book is for; an internal-tier rule would never see them.
    assert {r.tier for r in rules} == {Tier.public}


def test_brand_book_import_proposes_drafts_for_admins_only(client, world):
    admin, creator = _auth(world["admin"]), _auth(world["creator"])
    assert client.post("/rules/extract", headers=creator, json={"text": BOOK}).status_code == 403
    out = client.post("/rules/extract", headers=admin, json={"text": BOOK, "source_ref": "Book v1"})
    assert out.status_code == 200, out.text
    proposals = out.json()["rules"]
    assert proposals and all(p["source_ref"] == "Book v1" for p in proposals)
    # Kept proposals become drafts: nothing runs in reviews until someone activates them.
    made = client.post("/rules", headers=admin, json=proposals[0])
    assert made.status_code == 201 and made.json()["status"] == "draft"
    assert client.post("/rules/extract", headers=admin, json={}).status_code == 422


def test_terms_can_be_rescheduled_and_removed(client, world):
    admin = _auth(world["admin"])
    term = next(t for t in client.get("/confidential-terms", headers=admin).json() if t["term"] == "Project Lumen")
    moved = client.patch(f"/confidential-terms/{term['id']}", headers=admin, json={"embargo_until": "2030-05-01"})
    assert moved.status_code == 200 and moved.json()["embargo_until"] == "2030-05-01"
    assert client.patch(f"/confidential-terms/{term['id']}", headers=_auth(world["reviewer"]),
                        json={"note": "x"}).status_code == 403
    assert client.delete(f"/confidential-terms/{term['id']}", headers=admin).status_code == 204
    assert all(t["id"] != term["id"] for t in client.get("/confidential-terms", headers=admin).json())
    # The audit log records the removal, never the term itself.
    audit = client.get("/audit", headers=admin, params={"object_type": "confidential_term"}).json()
    assert "Project Lumen" not in str(audit) and any(a["action"] == "term.deleted" for a in audit)


def test_a_retired_fact_stops_backing_claims(client, world):
    admin = _auth(world["admin"])
    fact = client.get("/facts", headers=admin).json()[0]
    retired = client.post(f"/facts/{fact['id']}/retire", headers=admin)
    assert retired.status_code == 200
    assert fact["id"] not in [f["id"] for f in client.get("/facts", headers=admin,
                                                         params={"valid_on": "2099-01-01"}).json()]


def test_asset_thumbnails_are_served_to_workspace_members(client, world):
    admin = _auth(world["admin"])
    made = client.post("/brand-assets", headers=admin, json={
        "name": "Owly", "kind": "mascot", "part": "face", "data_base64": b64(png(mascot_face()))})
    assert made.status_code == 201, made.text
    img = client.get(f"/brand-assets/{made.json()['id']}/image", headers=_auth(world["creator"]))
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.content.startswith(b"\x89PNG")


def test_the_timeline_tells_one_story_to_both_parties(client, world):
    creator, approver = _auth(world["creator"]), _auth(world["approver"])
    made = client.post("/contents?wait=true", headers=creator, json={
        "title": "Launch post", "channel": "linkedin", "body": "Please login to see what's new."}).json()
    cid = made["content"]["id"]
    said = client.post(f"/contents/{cid}/comments", headers=approver, json={"body": "Use our spelling."})
    assert said.status_code == 201
    assert client.post(f"/contents/{cid}/transition", headers=creator, json={"to": "in_review"}).status_code == 200

    mine = client.get(f"/contents/{cid}/timeline", headers=creator).json()
    theirs = client.get(f"/contents/{cid}/timeline", headers=approver).json()
    assert mine == theirs
    kinds = [i["type"] for i in mine["items"]]
    assert kinds[:2] == ["version", "review"] and "comment" in kinds and kinds[-1] == "status"
    comment = next(i for i in mine["items"] if i["type"] == "comment")
    assert comment["actor"]["name"] == "Approver" and comment["body"] == "Use our spelling."
    assert mine["items"][-1]["to"] == "in_review" and mine["author"]["name"] == "Creator"
    assert all(i["at"].endswith("+00:00") for i in mine["items"])
