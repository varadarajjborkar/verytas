"""Learning from fixes: which operation reviewers take per rule, and their own edits as lessons."""

from __future__ import annotations

import random
from datetime import UTC, datetime

from verytas.checks.base import RawFinding
from verytas.models import DecisionAction, Suggestion, Tier
from verytas.prism import fixstyle
from verytas.prism.fixstyle import FixStyle, Lesson, outcome
from verytas.prism.precedent import words
from verytas.prism.suggest import ExplainAndFixTask, Fix, _screen


def _flagged(quote="Other apps just play videos at you. Switch to us."):
    return RawFinding("p1", "messaging", "May break MSG-RIVALS", "x", 0.8, "semantic", rule_code="MSG-RIVALS",
                      quote=quote, model="judge")


def test_what_a_decision_says_about_its_fix():
    assert outcome(DecisionAction.accepted) is True
    assert outcome(DecisionAction.edited) is False  # the reviewer wrote their own
    assert outcome(DecisionAction.rejected) is None and outcome(DecisionAction.escalated) is None


def test_the_operation_reviewers_take_wins_most_draws_but_others_still_get_tried():
    style = FixStyle(rng=random.Random(1))
    assert style.prefer("MSG-RIVALS") is None  # nothing decided yet
    for _ in range(8):
        style.record("MSG-RIVALS", "rewrite", True)
    for taken in (False, False, False, True):
        style.record("MSG-RIVALS", "delete", taken)
    picks = []
    for seed in range(200):
        s = FixStyle(tally=style.tally, rng=random.Random(seed))
        picks.append(s.prefer("MSG-RIVALS"))
        assert s.prefer("MSG-RIVALS") == picks[-1]  # one draw per rule per review
    assert picks.count("rewrite") > 150 and set(picks) - {"rewrite"}  # mostly rewrite, still exploring
    few = FixStyle(rng=random.Random(1))
    few.record("TONE-PLAIN", "replace", True)
    assert few.prefer("TONE-PLAIN") is None  # under MIN_DECIDED: no preference


def test_the_fix_prompt_carries_the_preference_and_the_nearest_reviewer_edit():
    style = FixStyle(rng=random.Random(3))
    for _ in range(6):
        style.record("MSG-RIVALS", "rewrite", True)
    at = datetime(2026, 10, 4, tzinfo=UTC)
    q = "Other apps just play videos at you"
    style.lessons["MSG-RIVALS"] = [Lesson("MSG-RIVALS", q, "Videos are half of it; we add a mentor", at, words(q))]
    text = ExplainAndFixTask([("0", _flagged(), None)], style).user_content()
    assert "<prefer>rewrite</prefer>" in text and "rewrite 6 of 6" in text
    assert "<reviewer_fix>Other apps just play videos at you => Videos are half of it; we add a mentor" in text
    assert "<prefer>" not in ExplainAndFixTask([("0", _flagged(), None)]).user_content()
    # Every model-written fix records its operation.
    f = _flagged()
    edit = _screen(f, Fix(key="0", explanation="x", action="delete", original="Other apps just play videos at you.",
                          proposed="anything"), "m", None)
    assert edit.action == "delete" and edit.proposed == ""


def test_decided_fixes_are_counted_and_reviewer_edits_kept_within_the_tier(client):
    h = {"Authorization": "Bearer " + client.post("/bootstrap", json={
        "workspace_name": "Acme", "admin_email": "a@acme.io", "admin_name": "Meera"}).json()["token"]}
    r = client.post("/rules", headers=h, json={
        "code": "VOICE-01", "category": "tone", "kind": "semantic", "severity": "should", "title": "Plain words",
        "text": "Write plainly. No buzzwords.", "bad_examples": ["leverage synergies to unlock paradigm shifts"],
        "good_examples": ["we help teams publish faster"], "tier": "public"}).json()
    client.patch(f"/rules/{r['id']}", headers=h, json={"status": "active"})
    db = client.app.state.db

    def voice(body, tier):
        res = client.post("/contents?wait=true", headers=h, json={"title": "T", "channel": "linkedin", "body": body,
                                                                 "tier": tier})
        review = client.get(f"/reviews/{res.json()['review_id']}", headers=h).json()
        [f] = [f for f in review["findings"] if f["citations"] and f["citations"][0]["label"].startswith("VOICE-01")]
        return f

    async def add_fix(fid, action):
        async with db.sessionmaker() as s:
            s.add(Suggestion(finding_id=fid, original="leverage synergies", proposed="work together", rationale="r",
                             model="m", action=action))
            await s.commit()

    public = voice("We leverage synergies to unlock paradigm shifts.", "public")
    secret = voice("Internally we leverage synergies to unlock paradigm shifts.", "confidential")
    taken = voice("This quarter we leverage synergies to unlock paradigm shifts.", "public")
    for f, op in ((public, "replace"), (secret, "replace"), (taken, "rewrite")):
        client.portal.call(add_fix, f["id"], op)
    client.post(f"/findings/{public['id']}/decision", headers=h, json={
        "action": "edited", "edited_text": "We work as one team."})
    client.post(f"/findings/{secret['id']}/decision", headers=h, json={
        "action": "edited", "edited_text": "Internally, Project Falcon pairs teams."})
    client.post(f"/findings/{taken['id']}/decision", headers=h, json={"action": "accepted"})

    async def load(tier):
        async with db.sessionmaker() as s:
            return await fixstyle.load(s, 1, tier, lambda t: t.replace("Falcon", "[confidential]"), seed=1)

    style = client.portal.call(load, Tier.public)
    assert style.tally["VOICE-01"]["replace"] == [0, 2] and style.tally["VOICE-01"]["rewrite"] == [1, 0]
    assert [x.edited for x in style.lessons["VOICE-01"]] == ["We work as one team."]  # not the confidential one
    inside = client.portal.call(load, Tier.confidential)
    assert "Internally, Project [confidential] pairs teams." in [x.edited for x in inside.lessons["VOICE-01"]]
