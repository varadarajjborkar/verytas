"""End-to-end workflow through the HTTP API, offline providers."""

from __future__ import annotations

import pytest

BODY = (
    "Verytas is trusted by 1,000+ teams. Sign-in takes seconds.\n\n"
    "Project Lumen brings video review next month!\n\n"
    "We leverage synergies to unlock paradigm shifts. Read [click here](https://verytas.example)."
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def world(client):
    res = client.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "admin@acme.io",
                                          "admin_name": "Ada"})
    assert res.status_code == 201
    admin = res.json()["token"]
    tokens = {"admin": admin}
    for role in ("creator", "reviewer", "approver"):
        r = client.post("/users", headers=_auth(admin),
                        json={"email": f"{role}@acme.io", "name": role.title(), "role": role})
        assert r.status_code == 201
        tokens[role] = r.json()["token"]

    h = _auth(admin)
    assert client.post("/rules", headers=h, json={
        "code": "TERM-01", "category": "terminology", "kind": "deterministic", "severity": "should",
        "title": "House spellings", "text": "Use our house spellings.",
        "pattern": {"type": "preferred_terms", "map": {"sign-in": "sign in"}}, "source_ref": "Style guide p.4",
    }).status_code == 201
    r = client.post("/rules", headers=h, json={
        "code": "VOICE-01", "category": "tone", "kind": "semantic", "severity": "should",
        "title": "Plain words", "text": "Write plainly. No buzzwords or corporate jargon.",
        "bad_examples": ["leverage synergies to unlock paradigm shifts"],
        "good_examples": ["we help teams publish faster"],
    })
    assert r.status_code == 201
    client.patch(f"/rules/{r.json()['id']}", headers=h, json={"status": "active"})
    client.patch("/rules/" + str(_rule_id(client, h, "TERM-01")), headers=h, json={"status": "active"})

    assert client.post("/facts", headers=h, json={
        "statement": "Verytas is used by 800+ teams", "value": 800, "unit": "teams", "subject": "teams",
        "source_ref": "Board deck Q3", "valid_from": "2026-07-01",
    }).status_code == 201
    assert client.post("/confidential-terms", headers=h,
                       json={"term": "Project Lumen", "embargo_until": "2099-01-01"}).status_code == 201
    return tokens


def _rule_id(client, h, code):
    return next(r["id"] for r in client.get("/rules", headers=h).json() if r["code"] == code)


def test_auth_is_required(client):
    assert client.get("/contents").status_code == 401
    assert client.get("/contents", headers=_auth("vt_wrong")).status_code == 401


def test_bootstrap_only_once(client, world):
    res = client.post("/bootstrap", json={"workspace_name": "X", "admin_email": "x@x.io", "admin_name": "X"})
    assert res.status_code == 409


def test_roles_are_enforced(client, world):
    res = client.post("/facts", headers=_auth(world["creator"]),
                      json={"statement": "s", "source_ref": "r", "valid_from": "2026-01-01"})
    assert res.status_code == 403
    assert client.get("/confidential-terms", headers=_auth(world["reviewer"])).status_code == 403


def test_full_review_cycle(client, world):
    creator, approver = _auth(world["creator"]), _auth(world["approver"])

    res = client.post("/contents?wait=true", headers=creator, json={
        "title": "Launch post", "channel": "linkedin", "body": BODY,
        "attachments": {"images": [{"id": "cover", "alt": ""}]},
    })
    assert res.status_code == 201, res.text
    content_id, review_id = res.json()["content"]["id"], res.json()["review_id"]

    review = client.get(f"/reviews/{review_id}", headers=creator).json()
    assert review["status"] == "done", review
    by_rule = {}
    for f in review["findings"]:
        assert f["signature_valid"], f
        assert f["citations"], f  # every finding is cited
        by_rule.setdefault(f["citations"][0]["label"].split(" ")[0], []).append(f)

    assert {"TERM-01", "CONF-LEAK", "A11Y-ALT", "A11Y-LINKTEXT", "VOICE-01", "CLAIM-CONTRADICTED"} <= set(by_rule)
    leak = by_rule["CONF-LEAK"][0]
    assert leak["level"] == "blocker" and leak["quote"] == "Project Lumen"
    claim = by_rule["CLAIM-CONTRADICTED"][0]
    assert any(c["kind"] == "fact" and "800+" in c["label"] for c in claim["citations"])
    assert claim["suggestions"][0]["proposed"] == "Verytas is trusted by 800+ teams."
    voice = by_rule["VOICE-01"][0]
    assert voice["model"] == "offline/judge" and voice["level"] != "blocker"  # model-only never blocks
    assert review["coverage"]["models"]["judge"] == "offline/judge"
    assert review["summary"]["overall"] < 1

    # Rejections need a reason; creators cannot dismiss blockers.
    assert client.post(f"/findings/{voice['id']}/decision", headers=creator,
                       json={"action": "rejected"}).status_code == 422
    assert client.post(f"/findings/{leak['id']}/decision", headers=creator,
                       json={"action": "rejected", "reason_code": "intentional"}).status_code == 403

    term = by_rule["TERM-01"][0]
    for f, sugg in ((term, term["suggestions"][0]), (claim, claim["suggestions"][0])):
        r = client.post(f"/findings/{f['id']}/decision", headers=creator,
                        json={"action": "accepted", "suggestion_id": sugg["id"]})
        assert r.status_code == 201
    client.post(f"/findings/{voice['id']}/decision", headers=creator,
                json={"action": "rejected", "reason_code": "guideline_unclear", "reason_text": "this is our tagline"})

    # Approval is gated on the open blockers.
    submit = client.post(f"/contents/{content_id}/transition", headers=creator, json={"to": "in_review"})
    assert submit.status_code == 200
    gated = client.post(f"/contents/{content_id}/transition", headers=approver, json={"to": "approved"})
    assert gated.status_code == 409 and "blocker" in gated.json()["detail"]

    # Apply accepted fixes: new version, new review, change log recorded.
    res = client.post(f"/contents/{content_id}/apply-fixes?wait=true", headers=creator)
    assert res.status_code == 201, res.text
    new_body = res.json()["version"]["body"]
    assert "800+ teams" in new_body and "Sign in takes" in new_body and "1,000+" not in new_body
    changes = client.get(f"/contents/{content_id}/changes", headers=creator).json()
    assert len(changes[0]["diff"]) == 2

    detail = client.get(f"/contents/{content_id}", headers=creator).json()
    assert [v["version_no"] for v in detail["versions"]] == [1, 2]
    assert detail["versions"][1]["parent_id"] == detail["versions"][0]["id"]

    # The leak is still there, so the gate still holds; an approver may override with a note.
    no_note = client.post(f"/contents/{content_id}/transition", headers=approver,
                          json={"to": "approved", "override_blockers": True})
    assert no_note.status_code == 409
    ok = client.post(f"/contents/{content_id}/transition", headers=approver,
                     json={"to": "approved", "override_blockers": True, "note": "Legal cleared the codename"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"

    overview = client.get("/insights/overview", headers=approver).json()
    assert overview["findings"]["total"] >= 6 and overview["decisions"]["rejected"] == 1
    health = client.get("/insights/guideline-health", headers=approver).json()
    voice_health = next(h for h in health if h["code"] == "VOICE-01")
    assert voice_health["rejected"] == 1 and voice_health["unclear_share"] == 1.0

    audit = client.get("/audit/verify", headers=_auth(world["admin"])).json()
    assert audit["ok"] and audit["entries"] > 10
    actions = {a["action"] for a in client.get("/audit", headers=_auth(world["admin"])).json()}
    assert {"review.completed", "finding.decided", "fixes.applied", "content.transition"} <= actions


def test_clearance_hides_confidential_content(client, world):
    admin = _auth(world["admin"])
    res = client.post("/contents?wait=true", headers=admin,
                      json={"title": "Board memo", "tier": "confidential", "body": "Numbers for the board."})
    cid = res.json()["content"]["id"]
    # Reviewer has the default "internal" clearance: same 404 as a missing item.
    assert client.get(f"/contents/{cid}", headers=_auth(world["reviewer"])).status_code == 404
    assert client.get(f"/contents/{cid}", headers=admin).status_code == 200
