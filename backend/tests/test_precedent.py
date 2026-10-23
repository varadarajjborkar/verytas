"""Precedent memory: past reviewer decisions on the same rule, found by the words they were about."""

from __future__ import annotations

from datetime import UTC, datetime

from tests.helpers import rule
from verytas.checks.base import RawFinding
from verytas.prism.precedent import Book, Case, words

RIVALS = rule("MSG-RIVALS", {}, category="messaging", kind="semantic", severity="must", rid=1,
              text="No digs at other platforms.", bad_examples=("Other apps just show videos",),
              good_examples=("We teach by doing",))


def _case(quote, action, reason=None, why=None, fid=1, day=4, code="MSG-RIVALS"):
    return Case(code, quote, action, reason, why, "Meera", datetime(2026, 10, day, tzinfo=UTC), fid, words(quote))


def _book(*cases):
    book = Book()
    for c in cases:
        book.cases.setdefault(c.rule_code, []).append(c)
    return book


def test_the_nearest_cases_on_the_same_rule_are_found_by_their_words():
    book = _book(_case("Unlike some other apps, our mentors reply", "rejected", "false_positive", "Names nobody.", 1),
                 _case("Other apps just play videos at you", "accepted", fid=2),
                 _case("Short lessons, real mentors", "accepted", fid=3, code="TONE-PLAIN"))
    near = book.nearest("MSG-RIVALS", "Unlike other apps, our mentors actually reply")
    assert [c.finding_id for c in near][0] == 1
    assert book.nearest("MSG-RIVALS", "Revise a little each day") == []  # nothing like it decided before
    assert near[0].shown()["summary"] == "Dismissed on 4 Oct by Meera: Names nobody."


def test_only_clear_outcomes_become_examples_for_the_judge():
    book = _book(_case("Unlike some other apps, our mentors reply", "rejected", "false_positive", fid=1),
                 _case("Other apps just play videos at you", "accepted", fid=2),
                 _case("Other apps hide their charges from you", "rejected", "intentional", "Campaign line.", 3),
                 _case("Other apps may be fine for some", "rejected", "guideline_unclear", fid=4))
    r = book.with_examples(RIVALS, "Other apps just show videos; our mentors reply")
    assert r.bad_examples[0] == "Other apps just play videos at you" and r.bad_examples[-1] == RIVALS.bad_examples[0]
    assert r.good_examples[0] == "Unlike some other apps, our mentors reply"
    # Kept on purpose, or unclear: neither says whether the words break the rule.
    every = {*r.bad_examples, *r.good_examples}
    assert "Other apps hide their charges from you" not in every and "Other apps may be fine for some" not in every
    # Deterministic rules are matched by their pattern, not by examples.
    plain = rule("TERM-NAME", {"type": "casing", "terms": ["Kitepath"]})
    assert book.with_examples(plain, "x") is plain


def test_only_model_judged_findings_are_given_precedents():
    book = _book(_case("Other apps just play videos at you", "accepted", fid=2))
    judged = RawFinding("p1", "messaging", "May break MSG-RIVALS", "x", 0.7, "semantic", rule_code="MSG-RIVALS",
                        quote="Other apps just play videos", model="judge")
    mechanical = RawFinding("p1", "messaging", "Names a rival", "x", 1.0, "deterministic", rule_code="MSG-RIVALS",
                            quote="Other apps just play videos")
    assert book.attach([judged, mechanical], {}) == 1
    assert judged.precedents[0]["finding_id"] == 2 and mechanical.precedents is None


def test_a_reviewers_dismissal_is_shown_on_the_next_similar_finding(client):
    def auth(t):
        return {"Authorization": f"Bearer {t}"}

    admin = client.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                            "admin_name": "Meera"}).json()["token"]
    h = auth(admin)
    r = client.post("/rules", headers=h, json={
        "code": "VOICE-01", "category": "tone", "kind": "semantic", "severity": "should", "title": "Plain words",
        "text": "Write plainly. No buzzwords.", "bad_examples": ["leverage synergies to unlock paradigm shifts"],
        "good_examples": ["we help teams publish faster"], "tier": "public"}).json()
    client.patch(f"/rules/{r['id']}", headers=h, json={"status": "active"})

    def review(body, tier="public"):
        res = client.post("/contents?wait=true", headers=h, json={"title": "T", "channel": "linkedin", "body": body,
                                                                 "tier": tier})
        return client.get(f"/reviews/{res.json()['review_id']}", headers=h).json()

    def voice_of(rev):
        [f] = [f for f in rev["findings"] if f["citations"] and f["citations"][0]["label"].startswith("VOICE-01")]
        return f

    first = review("We leverage synergies to unlock paradigm shifts for every team.")
    voice = voice_of(first)
    assert voice["precedents"] is None
    client.post(f"/findings/{voice['id']}/decision", headers=h, json={
        "action": "rejected", "reason_code": "false_positive", "reason_text": "Our tagline, approved by the CMO."})

    again = review("This quarter we leverage synergies to unlock paradigm shifts.")
    voice2 = voice_of(again)
    [p] = voice2["precedents"]
    assert p["finding_id"] == voice["id"] and p["summary"].startswith("Dismissed on ")
    assert p["summary"].endswith("by Meera: Our tagline, approved by the CMO.")
    assert again["coverage"]["precedents"]["attached"] == 1

    # Precedents quote other people's pieces: a creator, who sees only their own work, is not shown them.
    creator = client.post("/users", headers=h, json={"email": "c@acme.io", "name": "Cy", "role": "creator"}).json()
    res = client.post("/contents?wait=true", headers=auth(creator["token"]), json={
        "title": "T", "channel": "linkedin", "body": "Next week we leverage synergies to unlock paradigm shifts.",
        "tier": "public"})
    mine = client.get(f"/reviews/{res.json()['review_id']}", headers=auth(creator["token"])).json()
    assert voice_of(mine)["precedents"] is None
    seen = client.get(f"/reviews/{res.json()['review_id']}", headers=h).json()
    assert voice_of(seen)["precedents"]

    # A decision on confidential content is never shown on a public piece.
    secret = review("Internally we leverage synergies to unlock paradigm shifts.", tier="confidential")
    f3 = voice_of(secret)
    client.post(f"/findings/{f3['id']}/decision", headers=h, json={"action": "accepted"})
    public = review("Externally we leverage synergies to unlock paradigm shifts.")
    f4 = voice_of(public)
    assert f3["id"] not in {p["finding_id"] for p in f4["precedents"]}


def test_judge_examples_are_found_inside_a_whole_post_and_masks_hold_across_the_cut():
    from verytas.prism import precedent
    from verytas.security.redaction import Redactor

    book = _book(_case("Other apps just play videos at you", "accepted", fid=2))
    post = ("Exams are close and every minute counts. Revise a chapter a day, ask your mentor when stuck, and "
            "remember: other apps just play videos at you. We sit with you until it clicks. Boards reward steady "
            "practice, so book a weekly slot, bring your doubts, and track progress on the dashboard together.")
    assert book.nearest("MSG-RIVALS", post) == []  # a whole post drowns a short quote in the union
    assert book.with_examples(RIVALS, post).bad_examples[0] == "Other apps just play videos at you"

    mask = Redactor(["Project Falcon"]).mask
    long = "x" * (precedent._QUOTE_CHARS - 5) + " Project Falcon launches"
    assert "Proj" not in mask(long)[:precedent._QUOTE_CHARS]
    assert _case("x", "rejected", "false_positive", fid=9, day=4).shown()["summary"].startswith("Dismissed on 4 Oct")
