"""The dossier behind Summarize: who may ask, what is left out, and what never leaves unredacted."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from tests.test_api_flow import _auth
from tests.test_api_flow import world as world  # noqa: F401, the fixture is used by name
from verytas.api.deps import hash_token

LEAK = "Project Lumen lands next month, and it is our best release yet."
FIXED = "Our best release yet lands next month. Verytas helps teams publish faster."


def _post(client, token, body, title="Spring launch", **extra):
    out = client.post("/contents?wait=true", headers=_auth(token),
                      json={"title": title, "channel": "linkedin", "body": body, **extra})
    assert out.status_code == 201, out.text
    return out.json()


def _ask(client, token, kind, item_id, messages=()):
    return client.post("/assist/item-context", headers=_auth(token),
                       json={"kind": kind, "id": item_id, "messages": list(messages)})


def _blocker(client, token, review_id):
    findings = client.get(f"/reviews/{review_id}", headers=_auth(token)).json()["findings"]
    return next(f for f in findings if f["level"] == "blocker")


def _db(client) -> sqlite3.Connection:
    return sqlite3.connect(str(client.app.state.settings.database_url).split("///", 1)[1])


def test_only_the_deciding_roles_may_open_a_dossier(client, world):  # noqa: F811
    made = _post(client, world["creator"], LEAK)
    cid = made["content"]["id"]
    assert _ask(client, world["creator"], "content", cid).status_code == 403
    auditor = client.post("/users", headers=_auth(world["admin"]),
                          json={"email": "aud@acme.io", "name": "Aud", "role": "auditor"}).json()["token"]
    assert _ask(client, auditor, "content", cid).status_code == 403
    for role in ("reviewer", "approver", "admin"):
        assert _ask(client, world[role], "content", cid).status_code == 200, role
    assert _ask(client, world["reviewer"], "content", 9999).status_code == 404
    assert _ask(client, world["reviewer"], "escalation", 9999).status_code == 404
    assert client.post("/assist/item-context", headers=_auth(world["reviewer"]),
                       json={"kind": "other", "id": 1}).status_code == 422


def test_other_workspaces_and_higher_clearance_are_a_plain_404(client, world):  # noqa: F811
    made = _post(client, world["creator"], LEAK)
    cid = made["content"]["id"]
    memo = _post(client, world["admin"], "Numbers for the board.", title="Board memo", tier="confidential")
    # The reviewer holds the default internal clearance.
    assert _ask(client, world["reviewer"], "content", memo["content"]["id"]).status_code == 404
    # Even a cleared admin gets nothing for confidential pieces: the dossier goes to a hosted model.
    assert _ask(client, world["admin"], "content", memo["content"]["id"]).status_code == 404

    db = _db(client)
    db.execute("INSERT INTO workspaces (name, created_at) VALUES ('Other', ?)", (datetime.now(UTC).isoformat(),))
    other_ws = db.execute("SELECT id FROM workspaces WHERE name = 'Other'").fetchone()[0]
    db.execute("INSERT INTO users (workspace_id, email, name, role, clearance, token_hash, created_at) "
               "VALUES (?, 'x@other.io', 'Mallory', 'approver', 'confidential', ?, ?)",
               (other_ws, hash_token("vt_other"), datetime.now(UTC).isoformat()))
    db.commit()
    db.close()
    assert _ask(client, "vt_other", "content", cid).status_code == 404


def test_the_dossier_carries_the_story_of_the_piece(client, world):  # noqa: F811
    creator = world["creator"]
    made = _post(client, creator, LEAK, title="Spring launch")
    cid = made["content"]["id"]
    f = _blocker(client, creator, made["review_id"])
    client.post(f"/contents/{cid}/comments", headers=_auth(world["reviewer"]), json={"body": "Why is this late?"})
    resub = client.post(f"/contents/{cid}/resubmit?wait=true", headers=_auth(creator), json={
        "body": FIXED, "disputes": [],
        "creator_notes": {"intent": "A teaser, nothing more.", "ai_used": False}})
    assert resub.status_code == 201, resub.text

    d = _ask(client, world["approver"], "content", cid, ["what changed since round 1?"]).json()
    piece = d["piece"]
    assert d["kind"] == "content" and d["you"]["role"] == "approver"
    assert d["messages"] == ["what changed since round 1?"]
    assert piece["title"] == "Spring launch" and piece["creator"] == {"name": "Creator", "role": "creator"}
    assert [v["version"] for v in piece["versions"]] == [1, 2]
    v1, v2 = piece["versions"]
    assert v1["blockers"] >= 1 and "changed_since_previous" not in v1
    assert any("lands next month" in s for s in v2["changed_since_previous"]["added"])
    assert v1["findings"] and v1["findings"][0]["rule_code"]
    assert piece["latest_version"]["creator_notes"] == {"intent": "A teaser, nothing more.", "ai_used": False}
    assert [c["body"] for c in piece["comments"]] == ["Why is this late?"]
    assert piece["latest_review"]["status"] == "done"
    # The first round's blocker is described by rule and title, not just counted.
    assert f["title"].replace("Project Lumen", "[[TERM_1]]") in {x["title"] for x in v1["findings"]}


def test_findings_carry_rule_text_suggestion_and_the_decision_on_them(client, world):  # noqa: F811
    made = _post(client, world["creator"], "Verytas is trusted by 1,000+ teams, sign-in today.")
    cid = made["content"]["id"]
    findings = client.get(f"/reviews/{made['review_id']}", headers=_auth(world["creator"])).json()["findings"]
    f = next(x for x in findings if x["citations"])
    assert client.post(f"/findings/{f['id']}/decision", headers=_auth(world["approver"]),
                       json={"action": "rejected", "reason_code": "intentional",
                             "reason_text": "Approved by legal on the call."}).status_code == 201
    d = _ask(client, world["reviewer"], "content", cid).json()["piece"]["latest_review"]
    got = next(x for x in d["findings"] if x["id"] == f["id"])
    assert got["rule_text"] and got["explanation"] and got["checker"] and "confidence" in got
    assert got["decisions"][0]["action"] == "rejected"
    assert got["decisions"][0]["by"] == {"name": "Approver", "role": "approver"}
    assert got["decisions"][0]["reason"] == "Approved by legal on the call."


def test_confidential_terms_are_redacted_everywhere_before_text_is_cut(client, world):  # noqa: F811
    creator = world["creator"]
    long_tail = "A very long closing line about nothing in particular. " * 200
    made = _post(client, creator, LEAK + " " + long_tail, title="Project Lumen teaser",
                 creator_notes={"irregularity": "A long-form caption on purpose, for the newsletter."})
    cid = made["content"]["id"]
    client.post(f"/contents/{cid}/comments", headers=_auth(world["reviewer"]),
                json={"body": "Is project-lumen cleared?"})
    out = _ask(client, world["reviewer"], "content", cid, ["Is Project Lumen real?", "PROJECT LUMEN again"])
    assert out.status_code == 200
    text = str(out.json())
    assert "lumen" not in text.lower(), "a confidential term reached the payload"
    d = out.json()
    assert "[[TERM_1]]" in d["messages"][0]
    assert d["piece"]["latest_version"]["text_truncated"] is True
    assert d["piece"]["title"] == "[[TERM_1]] teaser"


def test_a_finding_citing_a_confidential_rule_is_withheld(client, world):  # noqa: F811
    made = _post(client, world["creator"], LEAK)
    cid = made["content"]["id"]
    before = _ask(client, world["reviewer"], "content", cid).json()["piece"]
    assert before["latest_review"]["findings"] and before["findings_withheld_for_clearance"] == 0

    db = _db(client)
    db.execute("UPDATE rules SET tier = 'confidential' WHERE code = 'CONF-LEAK'")
    db.commit()
    db.close()
    after = _ask(client, world["reviewer"], "content", cid).json()["piece"]
    assert all(f["rule_code"] != "CONF-LEAK" for f in after["latest_review"]["findings"])
    assert after["findings_withheld_for_clearance"] >= 1
    assert "CONF-LEAK" not in str(after)


def test_an_escalation_dossier_leads_with_the_escalation_then_its_piece(client, world):  # noqa: F811
    creator = world["creator"]
    made = _post(client, creator, LEAK, title="Spring launch")
    f = _blocker(client, creator, made["review_id"])
    raised = client.post(f"/findings/{f['id']}/escalations", headers=_auth(creator),
                         json={"message": "Project Lumen was announced publicly at the keynote yesterday."})
    assert raised.status_code == 201, raised.text
    eid = raised.json()["id"]

    out = _ask(client, world["approver"], "escalation", eid, ["is the concern real?"])
    assert out.status_code == 200, out.text
    d = out.json()
    assert list(d)[:4] == ["note", "you", "kind", "escalation"] and d["kind"] == "escalation"
    esc = d["escalation"]
    assert esc["status"] == "open" and esc["raised_by"] == {"name": "Creator", "role": "creator"}
    assert "announced publicly" in esc["message"] and "Lumen" not in str(d)
    assert esc["finding"]["id"] == f["id"] and esc["finding"]["rule_text"]
    assert esc["version"] == 1
    assert d["piece"]["title"] == "Spring launch" and d["piece"]["escalations"][0]["id"] == eid
    # Creators can't open it, and an unknown id is a 404 for everyone else.
    assert _ask(client, creator, "escalation", eid).status_code == 403
    assert _ask(client, world["reviewer"], "escalation", eid + 50).status_code == 404

    # Once resolved, the outcome and note travel with it.
    assert client.post(f"/escalations/{eid}/resolve", headers=_auth(world["approver"]),
                       json={"outcome": "cleared", "reason_code": "false_positive",
                             "note": "Confirmed public at the keynote."}).status_code == 200
    esc = _ask(client, world["reviewer"], "escalation", eid).json()["escalation"]
    assert esc["status"] == "cleared" and esc["resolution"]["note"] == "Confirmed public at the keynote."
    assert esc["resolution"]["by"]["role"] == "approver"


def test_what_was_said_about_a_withheld_finding_is_withheld_with_it(client, world):  # noqa: F811
    creator = world["creator"]
    made = _post(client, creator, LEAK, title="Teaser")
    f = _blocker(client, creator, made["review_id"])
    assert client.post(f"/findings/{f['id']}/escalations", headers=_auth(creator),
                       json={"message": "The codename was cleared by legal on Monday."}).status_code == 201
    db = _db(client)
    db.execute("UPDATE rules SET tier = 'confidential' WHERE code = 'CONF-LEAK'")
    db.commit()
    db.close()
    piece = _ask(client, world["reviewer"], "content", made["content"]["id"]).json()["piece"]
    assert piece["escalations"] == [] and "cleared by legal" not in str(piece)
