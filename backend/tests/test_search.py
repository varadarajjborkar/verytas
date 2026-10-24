"""Global search: it finds what the caller may open and nothing else.

Two companies each have a "Lantern" campaign. Inside Acme there are three levels of clearance, two
creators who own one piece each, and a brand admin who alone may see the confidential terms."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.test_api_flow import _auth
from verytas.config import Settings
from verytas.main import create_app

PASSWORD = "correct horse battery"
LEAK = "Lantern Zero lands next month, and it is our best release yet."


def _signup(c, name, email):
    r = c.post("/accounts/signup", json={"kind": "company", "company_name": name, "name": f"{name} admin",
                                         "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def _user(c, admin, role, name, clearance="internal"):
    r = c.post("/users", headers=_auth(admin), json={"email": f"{name.lower()}@acme.example", "name": name,
                                                      "role": role, "clearance": clearance})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def _post(c, token, title, body="A plain note about the week.", **extra):
    r = c.post("/contents?wait=true", headers=_auth(token), json={"title": title, "channel": "linkedin",
                                                                  "body": body, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _hits(c, token, q, **params):
    r = c.get("/search", headers=_auth(token), params={"q": q, **params})
    assert r.status_code == 200, r.text
    return r.json()["results"]


def _titles(hits, kind=None):
    return [h["title"] for h in hits if kind is None or h["type"] == kind]


@pytest.fixture
def town(tmp_path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'search.db'}", llm_mode="offline",
                        keys_dir=tmp_path / "keys", faces_enabled=False, self_signup=True,
                        self_signup_max_workspaces=5, self_signup_per_hour=50, self_serve_actions_per_day=500)
    with TestClient(create_app(settings)) as c:
        admin = _signup(c, "Acme", "boss@acme.example")
        who = {
            "admin": admin,
            "senior": _user(c, admin, "reviewer", "Senior", "confidential"),
            "reviewer": _user(c, admin, "reviewer", "Reviewer", "internal"),
            "intern": _user(c, admin, "reviewer", "Intern", "public"),
            "ana": _user(c, admin, "creator", "Ana"),
            "ben": _user(c, admin, "creator", "Ben"),
            "beta": _signup(c, "Beta", "boss@beta.example"),
        }
        h = _auth(admin)
        for payload in (
            {"statement": "Lantern is used by 800 teams", "source_ref": "Board deck", "valid_from": "2026-01-01"},
            {"statement": "Lantern margin target is 41 percent", "source_ref": "Finance", "tier": "confidential",
             "valid_from": "2026-01-01"},
        ):
            assert c.post("/facts", headers=h, json=payload).status_code == 201
        assert c.post("/rules", headers=h, json={
            "code": "LANTERN-01", "category": "tone", "kind": "semantic", "title": "Lantern voice",
            "text": "Speak about the lantern range warmly.", "tier": "confidential"}).status_code == 201
        assert c.post("/rules", headers=h, json={
            "code": "LANTERN-02", "category": "tone", "kind": "semantic", "title": "Lantern names",
            "text": "Always write Lantern with a capital L."}).status_code == 201
        assert c.post("/confidential-terms", headers=h, json={"term": "Lantern Zero"}).status_code == 201
        assert c.post("/events", headers=h, json={"name": "Lantern week", "starts_on": "2026-11-01"}).status_code == 201
        # The other company has its own Lantern of every kind, which Acme's people must never meet.
        b = _auth(who["beta"])
        assert c.post("/facts", headers=b, json={"statement": "Lantern sells in 9 countries", "source_ref": "Beta",
                                                 "valid_from": "2026-01-01"}).status_code == 201
        assert c.post("/confidential-terms", headers=b, json={"term": "Lantern Beta"}).status_code == 201
        _post(c, who["beta"], "Lantern launch (Beta)")
        yield c, who


def test_a_search_never_crosses_workspaces(town):
    c, who = town
    _post(c, who["ana"], "Lantern launch post")
    acme = _hits(c, who["admin"], "lantern")
    assert "Lantern launch post" in _titles(acme, "content")
    assert not any("Beta" in h["title"] or "9 countries" in h["title"] for h in acme)
    beta = _hits(c, who["beta"], "lantern")
    assert _titles(beta, "content") == ["Lantern launch (Beta)"]
    assert _titles(beta, "fact") == ["Lantern sells in 9 countries"]
    assert _titles(beta, "term") == ["Lantern Beta"]
    # Nothing of Acme's shows from Beta, in any group, and a person is not found by name across the line.
    assert not any(h["type"] in ("event", "creator", "escalation") for h in beta)
    assert not any(t.startswith("LANTERN-0") for t in _titles(beta, "rule"))
    assert _hits(c, who["beta"], "Ana") == []


def test_tier_clearance_holds_for_every_group(town):
    c, who = town
    _post(c, who["senior"], "Lantern margin plan", tier="confidential")
    _post(c, who["senior"], "Lantern note", tier="internal")
    for name, seen in (("senior", True), ("admin", True), ("reviewer", False), ("intern", False)):
        hits = _hits(c, who[name], "lantern")
        assert ("Lantern margin plan" in _titles(hits, "content")) is seen, name
        assert ("Lantern margin target is 41 percent" in _titles(hits, "fact")) is seen, name
        assert any(t.startswith("LANTERN-01") for t in _titles(hits, "rule")) is seen, name
    # Below internal, internal material is out of reach too.
    intern = _hits(c, who["intern"], "lantern")
    assert "Lantern note" not in _titles(intern, "content")
    assert "Lantern is used by 800 teams" not in _titles(intern, "fact")
    # A rule the person may read still shows; one above their clearance leaves no trace of its code.
    reviewer = _hits(c, who["reviewer"], "lantern")
    assert any(t.startswith("LANTERN-02") for t in _titles(reviewer, "rule"))
    assert not any("LANTERN-01" in h["title"] or "LANTERN-01" in h["href"] for h in reviewer)


def test_creators_search_only_their_own_work(town):
    c, who = town
    _post(c, who["ana"], "Lantern ana piece")
    _post(c, who["ben"], "Lantern ben piece")
    ana = _hits(c, who["ana"], "lantern")
    assert _titles(ana, "content") == ["Lantern ana piece"]
    # The library, the roster and the guarded words are not a creator's to search.
    assert not any(h["type"] in ("rule", "fact", "term", "asset", "event", "creator") for h in ana)
    assert _hits(c, who["ana"], "Ben") == []
    assert _hits(c, who["ana"], "ben piece") == []
    team = _hits(c, who["reviewer"], "lantern")
    assert {"Lantern ana piece", "Lantern ben piece"} <= set(_titles(team, "content"))
    assert _titles(_hits(c, who["reviewer"], "ben"), "creator") == ["Ben"]


def test_findings_and_escalations_follow_the_piece(town):
    c, who = town
    made = _post(c, who["ana"], "Launch copy", LEAK)
    finding = next(f for f in c.get(f"/reviews/{made['review_id']}", headers=_auth(who["ana"])).json()["findings"]
                   if f["level"] == "blocker")
    word = finding["title"].split()[0]
    raised = c.post(f"/findings/{finding['id']}/escalations", headers=_auth(who["ana"]),
                    json={"message": "Zeppelin was announced publicly at the keynote."})
    assert raised.status_code == 201, raised.text

    # The author finds her finding, and the request leads back to her piece (the inbox is not her screen).
    assert any(h["type"] == "finding" and h["id"] == finding["id"] for h in _hits(c, who["ana"], word))
    assert any(h["type"] == "escalation" and h["href"] == f"/review?id={made['content']['id']}"
               for h in _hits(c, who["ana"], "zeppelin"))
    # The brand team gets the inbox; another creator and another company get nothing.
    mine = [h for h in _hits(c, who["reviewer"], "zeppelin") if h["type"] == "escalation"]
    assert [h["href"] for h in mine] == [f"/escalations?id={raised.json()['id']}"]
    for name in ("ben", "beta"):
        assert not any(h["type"] in ("finding", "escalation") for h in _hits(c, who[name], word))
        assert _hits(c, who[name], "zeppelin") == []


def test_a_confidential_pieces_findings_stay_with_its_clearance(town):
    c, who = town
    made = _post(c, who["senior"], "Quiet launch", LEAK, tier="confidential")
    blocker = next(f for f in c.get(f"/reviews/{made['review_id']}", headers=_auth(who["senior"])).json()["findings"]
                   if f["level"] == "blocker")
    word = blocker["title"].split()[0]
    assert any(h["type"] == "finding" for h in _hits(c, who["senior"], word))
    assert not any(h["type"] == "finding" for h in _hits(c, who["reviewer"], word))


def test_confidential_terms_are_for_brand_admins_only(town):
    c, who = town
    assert _titles(_hits(c, who["admin"], "lantern zero"), "term") == ["Lantern Zero"]
    for name in ("senior", "reviewer", "intern", "ana"):
        assert not any(h["type"] == "term" for h in _hits(c, who[name], "lantern")), name


def test_matches_rank_by_prefix_then_word_start_then_anywhere_then_newest(town):
    c, who = town
    for title in ("The big orchard", "Orchard report", "Nonorchard note", "Orchard plans"):
        _post(c, who["admin"], title)
    ranked = _titles(_hits(c, who["admin"], "orchard"), "content")
    # Prefix hits first, the newest of them first; then a later word; then inside a word.
    assert ranked == ["Orchard plans", "Orchard report", "The big orchard", "Nonorchard note"]


def test_wildcards_are_searched_for_not_obeyed(town):
    c, who = town
    _post(c, who["admin"], "Hit 100% on brand")
    assert _titles(_hits(c, who["admin"], "100%"), "content") == ["Hit 100% on brand"]
    # A bare % or _ would match everything if it were a wildcard; as text it matches almost nothing.
    assert not _titles(_hits(c, who["admin"], "%"), "content") or _titles(_hits(c, who["admin"], "%"), "content") == [
        "Hit 100% on brand"]
    assert not _titles(_hits(c, who["admin"], "_"), "content")


def test_each_group_is_capped_and_the_cap_is_bounded(town):
    c, who = town
    for i in range(4):
        _post(c, who["admin"], f"Harvest {i}")
    assert len(_titles(_hits(c, who["admin"], "harvest", limit=2), "content")) == 2
    assert len(_titles(_hits(c, who["admin"], "harvest"), "content")) == 4
    assert c.get("/search", headers=_auth(who["admin"]), params={"q": "x", "limit": 11}).status_code == 422
    assert c.get("/search", headers=_auth(who["admin"]), params={"q": "x" * 101}).status_code == 422
    assert c.get("/search", params={"q": "harvest"}).status_code == 401


def test_an_empty_query_suggests_what_needs_the_caller_next(town):
    c, who = town
    mine = _post(c, who["ana"], "Ana's draft")
    _post(c, who["ben"], "Ben's draft")
    _post(c, who["beta"], "Beta's draft")
    ana = _hits(c, who["ana"], "")
    assert ana and {h["section"] for h in ana} <= {"needs_changes", "with_brand_team", "recent"}
    assert {h["title"] for h in ana if h["type"] == "content"} == {"Ana's draft"}
    assert all(h["href"].startswith("/review?id=") for h in ana)
    assert any(h["id"] == mine["content"]["id"] for h in ana)
    team = {h["title"] for h in _hits(c, who["reviewer"], "   ")}
    assert {"Ana's draft", "Ben's draft"} <= team and "Beta's draft" not in team
    # Suggestions respect clearance as search does.
    _post(c, who["senior"], "Board-only plan", tier="confidential")
    assert "Board-only plan" not in {h["title"] for h in _hits(c, who["intern"], "")}
    assert "Board-only plan" in {h["title"] for h in _hits(c, who["senior"], "")}


def test_findings_come_from_the_latest_review_only(town):
    c, who = town
    made = _post(c, who["ana"], "Revised copy", LEAK)
    first = next(f for f in c.get(f"/reviews/{made['review_id']}", headers=_auth(who["ana"])).json()["findings"]
                 if f["level"] == "blocker")
    word = first["title"].split()[0]
    assert any(h["id"] == first["id"] for h in _hits(c, who["ana"], word, limit=10))
    # Three clean revisions later the old blocker is history: the opened review no longer shows it.
    for i in range(3):
        r = c.post(f"/contents/{made['content']['id']}/versions?wait=true", headers=_auth(who["ana"]),
                   json={"body": f"A plain note about the week, take {i}."})
        assert r.status_code == 201, r.text
    assert not any(h["type"] == "finding" and h["id"] == first["id"] for h in _hits(c, who["ana"], word, limit=10))


def test_a_much_revised_piece_does_not_crowd_out_other_pieces(town):
    c, who = town
    old = _post(c, who["ana"], "Revised copy", LEAK)
    word = next(f for f in c.get(f"/reviews/{old['review_id']}", headers=_auth(who["ana"])).json()["findings"]
                if f["level"] == "blocker")["title"].split()[0]
    for _ in range(4):
        assert c.post(f"/contents/{old['content']['id']}/versions?wait=true", headers=_auth(who["ana"]),
                      json={"body": LEAK}).status_code == 201
    _post(c, who["ben"], "Another leak", LEAK)
    found = _hits(c, who["admin"], word, limit=2)
    pieces = {h["subtitle"].split(" in ", 1)[1] for h in found if h["type"] == "finding"}
    assert {"Revised copy", "Another leak"} <= pieces


def test_searching_is_throttled_per_person(town, monkeypatch):
    from verytas.api import search as module

    c, who = town
    monkeypatch.setattr(module, "SEARCH_MAX_IN_WINDOW", 3)
    for _ in range(3):
        assert c.get("/search", headers=_auth(who["admin"]), params={"q": "lantern"}).status_code == 200
    assert c.get("/search", headers=_auth(who["admin"]), params={"q": "lantern"}).status_code == 429
    # The window belongs to the person, not the workspace.
    assert c.get("/search", headers=_auth(who["reviewer"]), params={"q": "lantern"}).status_code == 200
