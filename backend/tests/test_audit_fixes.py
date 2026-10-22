"""Regressions for the security audit's role, approval and threshold findings (docs/security)."""

from __future__ import annotations

from sqlalchemy import select

from tests.test_api_flow import _approve, _auth, world  # noqa: F401, the fixture is used by name
from verytas.models import ContentVersion, Decision, DecisionAction, Dispute, Finding, User
from verytas.prism.disputes import rule_thresholds


def _auditor(client, world):  # noqa: F811
    r = client.post("/users", headers=_auth(world["admin"]),
                    json={"email": "auditor@acme.io", "name": "Audrey", "role": "auditor"})
    assert r.status_code == 201
    return _auth(r.json()["token"])


def test_auditors_read_comments_but_cannot_write_them(client, world):  # noqa: F811
    creator = _auth(world["creator"])
    res = client.post("/contents?wait=true", headers=creator, json={"title": "T", "body": "Hello."}).json()
    cid = res["content"]["id"]
    auditor = _auditor(client, world)
    assert client.post(f"/contents/{cid}/comments", headers=auditor, json={"body": "noted"}).status_code == 403
    assert client.get(f"/contents/{cid}/comments", headers=auditor).status_code == 200
    assert client.post(f"/contents/{cid}/comments", headers=creator, json={"body": "noted"}).status_code == 201


async def test_a_version_without_its_own_review_cannot_be_approved(client, world):  # noqa: F811
    creator = _auth(world["creator"])
    res = client.post("/contents?wait=true", headers=creator, json={"title": "T", "body": "We help teams."}).json()
    cid, v1 = res["content"]["id"], res["version"]["id"]
    client.post(f"/contents/{cid}/transition", headers=creator, json={"to": "in_review"})
    # The moment between a new version's commit and its review's: the newest review is still v1's.
    db = client.app.state.db
    async with db.sessionmaker() as s:
        author = await s.scalar(select(User.id).where(User.email == "creator@acme.io"))
        s.add(ContentVersion(content_id=cid, version_no=2, parent_id=v1, body="Unchecked text.", created_by=author))
        await s.commit()
    gated = client.post(f"/contents/{cid}/transition", headers=_auth(world["approver"]), json={"to": "approved"})
    assert gated.status_code == 409 and "not been reviewed" in gated.json()["detail"]


async def test_repeating_a_dispute_or_decision_counts_once(client, world):  # noqa: F811
    creator = _auth(world["creator"])
    res = client.post("/contents?wait=true", headers=creator,
                      json={"title": "T", "body": "We leverage synergies to unlock paradigm shifts."}).json()
    review = client.get(f"/reviews/{res['review_id']}", headers=creator).json()
    voice = next(f for f in review["findings"] if any("VOICE-01" in c["label"] for c in f["citations"]))
    db = client.app.state.db
    async with db.sessionmaker() as s:
        finding = await s.get(Finding, voice["id"])
        author = await s.scalar(select(User.id).where(User.email == "creator@acme.io"))
        workspace = (await s.get(User, author)).workspace_id
        once = await rule_thresholds(s, workspace, 0.5)
        for _ in range(5):
            s.add(Dispute(finding_id=finding.id, content_id=res["content"]["id"], rule_id=finding.rule_id,
                          user_id=author, claim="it is our tagline", status="overturned"))
            s.add(Decision(finding_id=finding.id, actor_id=author, action=DecisionAction.rejected,
                           reason_code="false_positive"))
        await s.commit()
        repeated = await rule_thresholds(s, workspace, 0.5)
    assert "VOICE-01" not in once
    # One overturned dispute and one false-positive rejection: Beta(3, 1) gives precision 3/6.
    assert repeated["VOICE-01"] == round(0.5 + 0.4 * (0.75 - 0.5), 3)


def test_the_audit_log_hides_entries_about_objects_above_the_readers_clearance(client, world):  # noqa: F811
    admin = _auth(world["admin"])
    assert client.post("/rules", headers=admin, json={
        "code": "SECRET-01", "category": "terminology", "kind": "deterministic", "severity": "should",
        "title": "Codename spellings", "text": "Spell the codename our way.", "tier": "confidential",
        "pattern": {"type": "preferred_terms", "map": {"lumen": "Lumen"}},
    }).status_code == 201
    auditor = _auditor(client, world)
    assert all(r["code"] != "SECRET-01" for r in client.get("/rules", headers=auditor).json())
    seen = client.get("/audit", headers=auditor).json()
    assert seen and all("SECRET-01" not in str(e["detail"]) for e in seen)
    assert any("SECRET-01" in str(e["detail"]) for e in client.get("/audit", headers=admin).json())


def test_unterminated_pdf_streams_are_scanned_in_linear_time():
    import time

    from verytas.media.files import pdf_active_content

    raw = b"%PDF-1.7\n" + b"stream\nx" * 500_000 + b"/JavaScript"
    started = time.perf_counter()
    assert pdf_active_content(raw) == ["JavaScript"]
    assert time.perf_counter() - started < 1


async def test_reviews_beyond_the_admission_limit_wait_their_turn(settings, monkeypatch):
    import asyncio

    from verytas.prism.orchestrator import Prism

    settings.max_concurrent_reviews = 2
    prism = Prism(settings, sessionmaker=lambda: _NullSession())
    running, peak, release = 0, 0, asyncio.Event()

    async def held(session, review_id):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await release.wait()
        running -= 1

    monkeypatch.setattr(prism, "_review", held)
    tasks = [asyncio.create_task(prism.run(i)) for i in range(5)]
    await asyncio.sleep(0.05)
    assert running == 2
    release.set()
    await asyncio.gather(*tasks)
    assert peak == 2


class _NullSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_hidden_audit_entries_never_leave_an_auditor_with_a_short_page(client, world):  # noqa: F811
    admin = _auth(world["admin"])
    auditor = _auditor(client, world)
    for n in range(4):  # newer than anything the auditor may see
        assert client.post("/rules", headers=admin, json={
            "code": f"SECRET-{n}", "category": "terminology", "kind": "deterministic", "severity": "should",
            "title": "Codename", "text": "Spell it our way.", "tier": "confidential",
            "pattern": {"type": "preferred_terms", "map": {"lumen": "Lumen"}},
        }).status_code == 201
    page = client.get("/audit?limit=2", headers=auditor).json()
    assert len(page) == 2 and all("SECRET" not in str(e["detail"]) for e in page)
    older = client.get(f"/audit?limit=2&before={page[-1]['id']}", headers=auditor).json()
    assert older and all(e["id"] < page[-1]["id"] for e in older)


def test_confidential_term_entries_are_for_brand_admins_only(client, world):  # noqa: F811
    auditor = _auditor(client, world)
    assert all(e["object_type"] != "confidential_term" for e in client.get("/audit", headers=auditor).json())
    admin_view = client.get("/audit", headers=_auth(world["admin"])).json()
    assert any(e["object_type"] == "confidential_term" for e in admin_view)
