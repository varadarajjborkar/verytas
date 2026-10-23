"""Guideline clarifier: a draft wording from a rule's own decided cases, applied only by an admin."""

from __future__ import annotations

from verytas.prism.clarify import Cases, Draft, grounded, plain, proposal

CURRENT = {"text": "Write plainly. No buzzwords.", "good_examples": ["we help teams publish faster"],
           "bad_examples": ["leverage synergies to unlock paradigm shifts"]}


def test_examples_must_be_real_text_from_the_right_side():
    upheld = ["We leverage synergies across every team. Book a demo."]
    assert grounded("leverage synergies across every team", upheld) == "leverage synergies across every team"
    # The case's own words come back, whatever the model did to case and spacing; never a mid-word slice.
    assert grounded("LEVERAGE   synergies across EVERY team", upheld) == "leverage synergies across every team"
    assert grounded("everage synergies across every tea", upheld) == "We leverage synergies across every team."
    assert plain("Q&amp;A sessions &lt;live&gt;") == "Q&A sessions <live>"
    # Invented, or too short to mean anything: the newest real case's first sentence instead.
    assert grounded("We maximise holistic value", upheld) == "We leverage synergies across every team."
    assert grounded("We", upheld) == "We leverage synergies across every team."
    assert grounded("anything", []) == ""
    found = Cases(upheld=upheld, cleared=[("Our synergy pack bundles three courses.", "Product name.")])
    p = proposal(CURRENT, found, Draft(text="  Write plainly.\nNo buzzwords; product names are fine. ",
                                       bad_example="We leverage synergies across every team.",
                                       good_example="Our synergy pack bundles three courses.", changes="x"))
    assert p["text"] == "Write plainly. No buzzwords; product names are fine."
    assert p["bad_examples"][0] == "We leverage synergies across every team." and len(p["bad_examples"]) == 2
    assert p["good_examples"][0] == "Our synergy pack bundles three courses."
    # An overlong wording is not cut mid-sentence: the current one stays.
    assert proposal(CURRENT, found, Draft(text="x " * 1500, bad_example="", good_example="", changes=""))["text"] \
        == CURRENT["text"]


def test_an_admin_drafts_a_clearer_rule_from_its_cases_and_applies_it(client):
    def auth(t):
        return {"Authorization": f"Bearer {t}"}

    h = auth(client.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                             "admin_name": "Meera"}).json()["token"])
    rule = client.post("/rules", headers=h, json={
        "code": "VOICE-01", "category": "tone", "kind": "semantic", "severity": "should", "title": "Plain words",
        "text": "Write plainly. No buzzwords.", "bad_examples": ["leverage synergies to unlock paradigm shifts"],
        "good_examples": ["we help teams publish faster"]}).json()
    client.patch(f"/rules/{rule['id']}", headers=h, json={"status": "active"})
    assert client.post(f"/rules/{rule['id']}/clarify", headers=h).status_code == 409  # nothing decided yet

    def voice(body, tier="internal"):
        res = client.post("/contents?wait=true", headers=h, json={"title": "T", "channel": "linkedin", "body": body,
                                                                 "tier": tier})
        review = client.get(f"/reviews/{res.json()['review_id']}", headers=h).json()
        [f] = [f for f in review["findings"] if f["citations"] and f["citations"][0]["label"].startswith("VOICE-01")]
        return f

    up = voice("We leverage synergies to unlock paradigm shifts this year.")
    fine = voice("Synergies, our team pack, helps you unlock paradigm shifts in study habits.")
    secret = voice("Project Falcon will leverage synergies to unlock paradigm shifts.", tier="confidential")
    assert client.post("/confidential-terms", headers=h, json={"term": "Kestrel"}).status_code == 201
    masked = voice("Kestrel teams leverage synergies to unlock paradigm shifts, mail a@acme.io.")
    client.post(f"/findings/{masked['id']}/decision", headers=h, json={"action": "accepted"})
    client.post(f"/findings/{up['id']}/decision", headers=h, json={"action": "accepted"})
    client.post(f"/findings/{fine['id']}/decision", headers=h, json={
        "action": "rejected", "reason_code": "false_positive", "reason_text": "Synergies is our product name."})
    client.post(f"/findings/{secret['id']}/decision", headers=h, json={"action": "accepted"})

    res = client.post(f"/rules/{rule['id']}/clarify", headers=h)
    assert res.status_code == 200, res.text
    draft = res.json()
    assert draft["model"] == "offline/llm" and draft["cases"] == {"upheld": 2, "cleared": 1, "unclear": 0}
    p = draft["proposed"]
    # Offline the wording stays; the reasons are listed for the admin, not written into the rule.
    assert p["text"] == "Write plainly. No buzzwords." and "Synergies is our product name" in draft["changes"]
    # Newest upheld case first; every case's codename and address masked for good.
    assert p["bad_examples"][0] == "We leverage synergies to unlock paradigm shifts this year."
    assert all("Kestrel" not in e and "a@acme.io" not in e for e in p["bad_examples"] + p["good_examples"])

    async def read_cases():
        from verytas.models import Rule
        from verytas.prism import clarify
        from verytas.prism.disputes import workspace_redactor
        async with client.app.state.db.sessionmaker() as session:
            redactor = await workspace_redactor(session, 1)
            return await clarify.cases(session, await session.get(Rule, rule["id"]), redactor.mask)

    upheld = client.portal.call(read_cases).upheld
    assert "[confidential] teams leverage synergies to unlock paradigm shifts, mail [email]." in upheld
    assert p["good_examples"][0] == "Synergies, our team pack, helps you unlock paradigm shifts in study habits."
    assert all("Falcon" not in e for e in p["bad_examples"])  # confidential cases never become examples
    # Nothing changed until the admin applies it, as a new version.
    assert client.get("/rules", headers=h).json()[-1]["version"] == 1
    applied = client.patch(f"/rules/{rule['id']}", headers=h, json={**p, "text": "Write plainly. No buzzwords; "
                                                                   "our product names are fine."}).json()
    assert applied["version"] == 2 and applied["text"].endswith("product names are fine.")
