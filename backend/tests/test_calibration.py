"""Calibration: raw certainty mapped to how often this workspace's reviewers agreed."""

from __future__ import annotations

from tests.helpers import rule
from verytas.checks.base import RawFinding
from verytas.models import DecisionAction
from verytas.prism import calibration
from verytas.prism.calibration import Calibration, agreed, fit, warn_floor


def _f(category="tone", confidence=0.7, model="judge"):
    return RawFinding("p1", category, "t", "x", confidence, "semantic", rule_code="VOICE-01", model=model)


def test_what_counts_as_agreeing():
    assert agreed(DecisionAction.accepted, None) and agreed(DecisionAction.edited, None)
    assert agreed(DecisionAction.rejected, "intentional")  # right, and kept on purpose
    assert agreed(DecisionAction.rejected, "false_positive") is False
    assert agreed(DecisionAction.rejected, "guideline_unclear") is None
    assert agreed(DecisionAction.escalated, None) is None


def test_the_curve_never_falls_as_certainty_rises_and_never_claims_always():
    pts = [(0.6, False), (0.62, True), (0.65, False), (0.7, False), (0.8, True), (0.85, True), (0.9, True),
           (0.95, False), (0.99, True)]
    c = fit(pts)
    ys = [c(x) for x in (0.0, 0.6, 0.65, 0.7, 0.8, 0.9, 0.99, 1.0)]
    assert ys == sorted(ys)
    assert 0 < c(0.6) < c(0.99) < 1  # shrunk towards the overall rate at both ends
    assert c.n == 9 and abs(c.rate - 5 / 9) < 1e-9
    # A judge that is surer where reviewers agree less is flattened to one step, at the overall rate.
    flat = fit([(0.6, True), (0.7, True), (0.8, False), (0.9, False)])
    assert flat(0.6) == flat(0.9) == 0.5


def test_a_family_needs_enough_decisions_of_its_own_before_it_gets_its_own_curve():
    pts = [("claims", False, 1.0, i % 5 != 0) for i in range(25)] + [("tone", True, 0.7, i % 2 == 0) for i in range(8)]
    cal = Calibration.from_points(pts)
    assert cal.of(_f("claims", 1.0))["family"] == "claims"
    tone = cal.of(_f("tone", 0.7))
    assert tone["family"] == "all" and tone["n"] == 33  # too few tone decisions: the workspace curve
    assert Calibration.from_points(pts[:10]).of(_f("claims", 1.0)) is None  # too few in all: nothing claimed


def test_the_warning_floor_rises_only_as_far_as_the_evidence_needs():
    # Reviewers dismiss most warnings under 0.75 and agree with nearly all above it.
    pts = ([(0.62, i % 3 == 0) for i in range(30)] + [(0.72, i % 10 == 0) for i in range(20)]
           + [(0.82, i % 20 != 0) for i in range(30)] + [(0.9, True) for _ in range(20)])
    assert warn_floor(pts) == 0.75
    assert warn_floor(pts[:45]) is None  # under WARN_MIN decisions: the default stands
    assert warn_floor([(0.9, True) for _ in range(60)]) == 0.6
    # Nothing ever controls the risk: the top of the grid, so findings still show, as advisories.
    assert warn_floor([(x / 100, i % 2 == 0) for i, x in enumerate(range(60, 100)) for _ in range(2)]) == 0.85
    cal = Calibration(floor=0.8)
    should, must = rule("VOICE-01", {}, kind="semantic"), rule("LEGAL-01", {}, kind="semantic", severity="must")
    assert cal.warn_confidence(_f(), 0.6, should) == 0.8
    assert cal.warn_confidence(_f(model=None), 0.6, should) == 0.6  # rule-based findings are never moved
    # Fitted on should rules only, so applied only there.
    assert cal.warn_confidence(_f(), 0.6, must) == 0.6 and cal.warn_confidence(_f(), 0.6) == 0.6


def test_a_review_shows_how_often_reviewers_agreed(client, monkeypatch):
    monkeypatch.setattr(calibration, "WORKSPACE_MIN", 1)
    h = {"Authorization": "Bearer " + client.post("/bootstrap", json={
        "workspace_name": "Acme", "admin_email": "a@acme.io", "admin_name": "Meera"}).json()["token"]}
    r = client.post("/rules", headers=h, json={
        "code": "VOICE-01", "category": "tone", "kind": "semantic", "severity": "should", "title": "Plain words",
        "text": "Write plainly. No buzzwords.", "bad_examples": ["leverage synergies to unlock paradigm shifts"],
        "good_examples": ["we help teams publish faster"]}).json()
    client.patch(f"/rules/{r['id']}", headers=h, json={"status": "active"})

    def review(body):
        res = client.post("/contents?wait=true", headers=h, json={"title": "T", "channel": "linkedin", "body": body})
        return client.get(f"/reviews/{res.json()['review_id']}", headers=h).json()

    def voice_of(rev):
        [f] = [f for f in rev["findings"] if f["citations"] and f["citations"][0]["label"].startswith("VOICE-01")]
        return f

    first = voice_of(review("We leverage synergies to unlock paradigm shifts."))
    assert first["calibration"] is None
    client.post(f"/findings/{first['id']}/decision", headers=h, json={
        "action": "rejected", "reason_code": "false_positive", "reason_text": "Our tagline."})
    again = review("This quarter we leverage synergies to unlock paradigm shifts.")
    cal = voice_of(again)["calibration"]
    assert cal["n"] == 1 and cal["family"] == "all" and 0 < cal["agree"] < 0.5
    assert again["coverage"]["calibration"]["decisions"] == {"tone": 1}
