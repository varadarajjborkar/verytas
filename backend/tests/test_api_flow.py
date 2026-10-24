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


# --- regression tests for errcheck findings ------------------------------------

def test_insights_respect_clearance_and_roles(client, world):
    admin = _auth(world["admin"])
    for _ in range(2):
        client.post("/contents?wait=true", headers=admin,
                    json={"title": "Board memo", "tier": "confidential", "body": "Project Lumen numbers inside."})
    phrases = [r["phrase"] for r in client.get("/insights/recurring", headers=_auth(world["reviewer"])).json()]
    assert "project lumen" not in phrases
    assert any(r["phrase"] == "project lumen" for r in client.get("/insights/recurring", headers=admin).json())
    assert client.get("/insights/overview", headers=_auth(world["creator"])).status_code == 403


def test_confidential_rules_do_not_apply_to_lower_tier_content(client, world):
    admin = _auth(world["admin"])
    r = client.post("/rules", headers=admin, json={
        "code": "SECRET-01", "category": "terminology", "kind": "deterministic", "severity": "must",
        "title": "Secret naming", "text": "Never say Falcon (launch plan Q4).", "tier": "confidential",
        "pattern": {"type": "banned_terms", "terms": ["Falcon"]},
    })
    client.patch(f"/rules/{r.json()['id']}", headers=admin, json={"status": "active"})
    res = client.post("/contents?wait=true", headers=_auth(world["creator"]),
                      json={"title": "Post", "body": "Falcon is fast."})
    review = client.get(f"/reviews/{res.json()['review_id']}", headers=_auth(world["creator"])).json()
    assert not any("SECRET-01" in c["label"] for f in review["findings"] for c in f["citations"])


def test_audit_limit_is_bounded(client, world):
    assert client.get("/audit?limit=-1", headers=_auth(world["admin"])).status_code == 422


def test_comment_version_must_belong_to_content(client, world):
    creator = _auth(world["creator"])
    a = client.post("/contents?wait=true", headers=creator, json={"title": "A", "body": "Hello there."}).json()
    b = client.post("/contents?wait=true", headers=creator, json={"title": "B", "body": "Hi again."}).json()
    res = client.post(f"/contents/{a['content']['id']}/comments", headers=creator,
                      json={"body": "x", "version_id": b["version"]["id"]})
    assert res.status_code == 422


async def test_editing_a_finding_level_breaks_its_signature(client, world):
    from sqlalchemy import update

    from verytas.models import Finding

    creator = _auth(world["creator"])
    res = client.post("/contents?wait=true", headers=creator,
                      json={"title": "T", "body": "Project Lumen is coming."}).json()
    review = client.get(f"/reviews/{res['review_id']}", headers=creator).json()
    leak = next(f for f in review["findings"] if f["level"] == "blocker")
    db = client.app.state.db
    async with db.sessionmaker() as s:
        await s.execute(update(Finding).where(Finding.id == leak["id"]).values(level="advisory"))
        await s.commit()
    after = client.get(f"/reviews/{res['review_id']}", headers=creator).json()
    assert next(f for f in after["findings"] if f["id"] == leak["id"])["signature_valid"] is False


def _approve(client, world, cid, **extra):
    client.post(f"/contents/{cid}/transition", headers=_auth(world["creator"]), json={"to": "in_review"})
    return client.post(f"/contents/{cid}/transition", headers=_auth(world["approver"]),
                       json={"to": "approved", **extra})


def test_checks_that_did_not_run_block_approval(client, world, monkeypatch):
    import verytas.prism.agents as agents

    def boom(ctx, problems=None):
        raise RuntimeError("worker crashed")

    monkeypatch.setattr(agents, "run_deterministic", boom)
    res = client.post("/contents?wait=true", headers=_auth(world["creator"]),
                      json={"title": "T", "body": "Project Lumen is coming."}).json()
    gated = _approve(client, world, res["content"]["id"])
    assert gated.status_code == 409 and "did not run" in gated.json()["detail"]
    blank = client.post(f"/contents/{res['content']['id']}/transition", headers=_auth(world["approver"]),
                        json={"to": "approved", "override_blockers": True, "note": "   "})
    assert blank.status_code == 409


def test_new_version_after_approval_needs_reapproval(client, world):
    creator = _auth(world["creator"])
    res = client.post("/contents?wait=true", headers=creator, json={"title": "T", "body": "We help teams."}).json()
    cid = res["content"]["id"]
    assert _approve(client, world, cid).status_code == 200
    client.post(f"/contents/{cid}/versions?wait=true", headers=creator, json={"body": "Entirely new text."})
    assert client.get(f"/contents/{cid}", headers=creator).json()["status"] == "in_review"


def test_apply_fixes_refuses_published_content(client, world):
    creator, approver = _auth(world["creator"]), _auth(world["approver"])
    res = client.post("/contents?wait=true", headers=creator, json={"title": "T", "body": "Easy sign-in today."}).json()
    cid = res["content"]["id"]
    review = client.get(f"/reviews/{res['review_id']}", headers=creator).json()
    term = next(f for f in review["findings"] if f["suggestions"])
    client.post(f"/findings/{term['id']}/decision", headers=creator,
                json={"action": "accepted", "suggestion_id": term["suggestions"][0]["id"]})
    assert _approve(client, world, cid).status_code == 200
    assert client.post(f"/contents/{cid}/transition", headers=approver, json={"to": "published"}).status_code == 200
    assert client.post(f"/contents/{cid}/apply-fixes", headers=creator).status_code == 409


def test_overlapping_fixes_are_refused_not_dropped(client, world):
    creator = _auth(world["creator"])
    body = "We leverage synergies to unlock paradigm shifts with easy sign-in."
    res = client.post("/contents?wait=true", headers=creator, json={"title": "T", "body": body}).json()
    review = client.get(f"/reviews/{res['review_id']}", headers=creator).json()
    voice = next(f for f in review["findings"] if any("VOICE-01" in c["label"] for c in f["citations"]))
    term = next(f for f in review["findings"] if any("TERM-01" in c["label"] for c in f["citations"]))
    client.post(f"/findings/{voice['id']}/decision", headers=creator,
                json={"action": "edited", "edited_text": "We help teams publish faster with easy sign-in."})
    client.post(f"/findings/{term['id']}/decision", headers=creator,
                json={"action": "accepted", "suggestion_id": term["suggestions"][0]["id"]})
    res = client.post(f"/contents/{res['content']['id']}/apply-fixes", headers=creator)
    assert res.status_code == 409 and "overlap" in res.json()["detail"]


def test_rule_patterns_are_validated(client, world):
    admin = _auth(world["admin"])
    bad = client.post("/rules", headers=admin, json={
        "code": "TERM-09", "category": "terminology", "kind": "deterministic", "title": "x", "text": "x",
        "pattern": {"type": "preferred_terms", "map": ["a", "b"]}})
    assert bad.status_code == 422
    rid = _rule_id(client, admin, "TERM-01")
    assert client.patch(f"/rules/{rid}", headers=admin, json={"pattern": {"type": "nope"}}).status_code == 422
    assert client.patch(f"/rules/{rid}", headers=admin, json={"title": None}).status_code == 422


def test_only_the_latest_rule_version_is_editable(client, world):
    admin = _auth(world["admin"])
    rid = _rule_id(client, admin, "TERM-01")
    v2 = client.patch(f"/rules/{rid}", headers=admin, json={"title": "House spellings v2"}).json()
    assert v2["version"] == 2
    assert client.patch(f"/rules/{rid}", headers=admin, json={"status": "active"}).status_code == 409


def test_superseding_fact_must_start_later(client, world):
    admin = _auth(world["admin"])
    old = client.get("/facts", headers=admin).json()[0]
    res = client.post("/facts", headers=admin, json={
        "statement": "Verytas is used by 900+ teams", "value": 900, "source_ref": "x",
        "valid_from": "2026-01-01", "supersedes_id": old["id"]})
    assert res.status_code == 422


def test_scorecard_is_honest_about_coverage(client, world):
    # Legal is covered by built-in rules (AI labels, disclosure placement, likeness);
    # retiring them must show the category as not configured, never as passed.
    admin = _auth(world["admin"])
    for code in ("AI-DISCLOSURE", "PRES-FOLD", "LIKENESS-UNLICENSED", "LIKENESS-UNKNOWN"):
        assert client.patch(f"/rules/{_rule_id(client, admin, code)}", headers=admin,
                            json={"status": "retired"}).status_code == 200
    res = client.post("/contents?wait=true", headers=_auth(world["creator"]),
                      json={"title": "T", "body": "Plain words here."}).json()
    review = client.get(f"/reviews/{res['review_id']}", headers=_auth(world["creator"])).json()
    cats = review["summary"]["categories"]
    assert cats["legal"]["status"] == "not_configured" and cats["legal"]["score"] is None
    assert cats["tone"]["status"] == "degraded"  # offline judge in tests
    assert "legal" in review["coverage"]["not_configured"]


def test_built_in_checks_apply_to_public_content(client, world):
    # Found by the black-box simulator: built-in rules were seeded "internal",
    # so the tier ceiling skipped every leak, claim and accessibility check on
    # public posts. A public post is exactly where a leak hurts most.
    res = client.post("/contents?wait=true", headers=_auth(world["creator"]), json={
        "title": "Teaser", "channel": "x", "tier": "public",
        "body": "Psst, Project Lumen is coming. DO NOT SCROLL PAST THIS ONE SERIOUSLY.",
    })
    assert res.status_code == 201
    review = client.get(f"/reviews/{res.json()['review_id']}", headers=_auth(world["creator"])).json()
    categories = {f["category"] for f in review["findings"]}
    assert {"confidentiality", "accessibility"} <= categories
    assert "confidentiality" not in review["coverage"]["not_configured"]


def test_a_review_cut_off_by_a_restart_runs_again(settings, tmp_path):
    import sqlite3
    import time

    from fastapi.testclient import TestClient

    from verytas.main import create_app

    with TestClient(create_app(settings)) as c:
        admin = c.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                           "admin_name": "Ada"}).json()["token"]
        res = c.post("/contents?wait=true", headers=_auth(admin),
                     json={"title": "Post", "channel": "linkedin", "body": "We ship on Monday."})
        version_id = c.get(f"/reviews/{res.json()['review_id']}", headers=_auth(admin)).json()["version_id"]

    # What a deploy mid-review leaves behind: a review marked running, with no process working on it.
    db = sqlite3.connect(settings.database_url.split("///", 1)[1])
    cur = db.execute("insert into reviews (version_id, status, summary, coverage, started_at) "
                     "values (?, 'running', '{}', '{}', '2026-10-25 00:00:00')", (version_id,))
    stuck = cur.lastrowid
    db.commit()
    db.close()

    with TestClient(create_app(settings)) as c:
        for _ in range(100):
            status = c.get(f"/reviews/{stuck}", headers=_auth(admin)).json()["status"]
            if status == "done":
                break
            time.sleep(0.1)
        assert status == "done"
