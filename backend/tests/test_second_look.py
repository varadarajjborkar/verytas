"""Second look: must-rule questions also go to the larger model, within a budget, and every pair is recorded."""

from __future__ import annotations

import asyncio

from tests.helpers import make_ctx, rule
from verytas.checks.semantic import check_semantic
from verytas.prism.second_look import SecondLook
from verytas.providers.base import Answer, ProviderUnavailable

MUST = rule("MSG-RIVALS", {}, category="messaging", kind="semantic", severity="must", rid=1,
            text="No digs at other platforms.")
SHOULD = rule("TONE-PLAIN", {}, category="tone", kind="semantic", severity="should", rid=2, text="Plain words.")


class Judge:
    """Answers p(yes) per rule id from a table; counts what it was asked."""

    def __init__(self, name: str, p: dict[int, float], fail: bool = False) -> None:
        self.name, self.p, self.fail, self.asked = name, p, fail, []

    async def ask(self, state, questions):
        self.asked.append((state, sorted(questions)))
        if self.fail:
            raise ProviderUnavailable("larger model down")
        return {k: Answer("noul", self.p[int(k.split("_")[1])]) for k in questions}


def _run(body: str, first: Judge, second: SecondLook | None, rules=(MUST, SHOULD), per_rule=None):
    return asyncio.run(check_semantic(make_ctx(body, list(rules)), first, threshold=0.6, per_rule=per_rule,
                                      second=second.at("body") if second else None))


def test_a_must_rule_question_is_decided_by_the_larger_model():
    # The small judge is sure, and wrong: certainty is no guide to its mistakes (evals/second_look).
    small, big = Judge("small", {1: 0.1, 2: 0.9}), Judge("big", {1: 0.9, 2: 0.1})
    look = SecondLook(big, budget=6)
    found = _run("Toppers start today. Everyone else starts too late.", small, look)
    # The must rule takes the larger model's answer, attributed to it; the should rule stays with the first judge.
    assert sorted((f.rule_code, f.model) for f in found) == [("MSG-RIVALS", "big"), ("TONE-PLAIN", "small")]
    assert big.asked == [("Toppers start today. Everyone else starts too late.", ["rule_1"])]
    [entry] = look.log
    assert entry["outcome"] == "flagged" and entry["first"] == 0.1 and entry["second"] == 0.9
    assert entry["source"] == "body" and entry["unit"] == "p1"


def test_the_larger_model_can_clear_a_flag_and_agreement_is_recorded():
    look = SecondLook(Judge("big", {1: 0.1}), budget=6)
    assert _run("x", Judge("small", {1: 0.9, 2: 0.1}), look) == []
    assert look.log[0]["outcome"] == "cleared"
    look = SecondLook(Judge("big", {1: 0.9}), budget=6)
    assert [f.rule_code for f in _run("x", Judge("small", {1: 0.9, 2: 0.1}), look)] == ["MSG-RIVALS"]
    assert look.log[0]["outcome"] == "confirmed flag"


def test_learned_thresholds_still_decide_the_larger_models_answer():
    look = SecondLook(Judge("big", {1: 0.75}), budget=6)
    assert _run("x", Judge("small", {1: 0.1, 2: 0.1}), look, per_rule={"MSG-RIVALS": 0.8}) == []
    assert look.log[0]["threshold"] == 0.8 and look.log[0]["outcome"] == "confirmed clear"


def test_no_must_rules_costs_no_second_call():
    big = Judge("big", {})
    look = SecondLook(big, budget=6)
    _run("x", Judge("small", {2: 0.1}), look, rules=(SHOULD,))
    assert big.asked == [] and look.log == [] and look.budget == 6


def test_the_budget_is_counted_in_paragraphs_and_the_rest_are_reported():
    big = Judge("big", {1: 0.9})
    look = SecondLook(big, budget=1)
    _run("First paragraph here.\n\nSecond paragraph here.", Judge("small", {1: 0.1}), look, rules=(MUST,))
    assert len(big.asked) == 1 and look.unasked == 1 and look.budget == 0
    assert look.summary()["unasked"] == 1


def test_a_larger_model_that_fails_leaves_the_first_answer_and_says_so():
    look = SecondLook(Judge("big", {}, fail=True), budget=6)
    found = _run("x", Judge("small", {1: 0.9, 2: 0.1}), look)
    assert [(f.rule_code, f.model) for f in found] == [("MSG-RIVALS", "small")]
    assert look.log[0]["outcome"] == "unavailable" and "down" in look.log[0]["note"]


def test_reviews_run_offline_have_no_second_look(client):
    from tests.test_media import _auth

    admin = client.post("/bootstrap", json={"workspace_name": "A", "admin_email": "a@a.io",
                                            "admin_name": "A"}).json()["token"]
    res = client.post("/contents?wait=true", headers=_auth(admin), json={
        "title": "T", "channel": "linkedin", "body": "Hello there."})
    review = client.get(f"/reviews/{res.json()['review_id']}", headers=_auth(admin)).json()
    assert review["coverage"]["second_looks"] is None
