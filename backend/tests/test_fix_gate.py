"""The fix contract: three edit operations, and a gate that judges rule and content apart.

A single "same message?" question blocked fixes whose whole point was removing a dig or hype; these
tests pin the two-question gate and the delete operation."""

from __future__ import annotations

from verytas.checks.base import RawFinding, RuleView
from verytas.prism.suggest import ExplainAndFixTask, Fix, FixList, explain_and_fix
from verytas.providers.base import Answer

RIVALS = RuleView(id=1, code="MSG-RIVALS", category="messaging", kind="semantic", severity="must",
                  title="No digs at other platforms", text="Never mock or compare against other platforms.",
                  bad_examples=("Unlike some other apps, we actually teach",),
                  good_examples=("Learn Python in six weeks",))


class OneFixLLM:
    name = "stub/llm"

    def __init__(self, fix: Fix) -> None:
        self.fix, self.seen = fix, []

    async def run(self, task):
        assert isinstance(task, ExplainAndFixTask)
        self.seen.append(task.user_content())
        return FixList(fixes=[self.fix.model_copy(update={"key": key}) for key, _, _ in task.items])


class Judge:
    name = "stub/judge"

    def __init__(self, follows: float = 0.9, keeps: float = 0.9) -> None:
        self.follows, self.keeps, self.states, self.asked = follows, keeps, [], []

    async def ask(self, state, questions):
        self.states.append(state)
        self.asked.append(set(questions))
        return {"follows_rule": Answer("noul", self.follows), "keeps_offer": Answer("noul", self.keeps),
                "keeps_action": Answer("noul", 0.95)}


def _finding(quote: str) -> RawFinding:
    return RawFinding(unit_id="u1", category="messaging", title="Dig at other platforms", explanation="",
                      confidence=0.9, checker="semantic", rule_code="MSG-RIVALS", quote=quote, needs_explanation=True)


async def _run(fix: Fix, judge: Judge, quote: str = "StudyMax is a scam. Come learn with us."):
    f = _finding(quote)
    llm = OneFixLLM(fix)
    await explain_and_fix([f], {"MSG-RIVALS": RIVALS}, llm, judge)
    return f, llm


async def test_a_sentence_that_only_mocks_can_be_deleted():
    f, _ = await _run(Fix(key="", explanation="Mocks a rival.", action="delete", original="StudyMax is a scam.",
                          proposed="ignored when deleting"), Judge())
    assert f.suggestion and f.suggestion.original == "StudyMax is a scam." and f.suggestion.proposed == ""


async def test_an_empty_replacement_without_delete_is_still_no_fix():
    f, _ = await _run(Fix(key="", explanation="x", action="replace", original="StudyMax is a scam.", proposed=""),
                      Judge())
    assert f.suggestion is None


async def test_the_judge_sees_the_rule_and_answers_both_questions():
    judge = Judge()
    await _run(Fix(key="", explanation="x", action="rewrite", original="StudyMax is a scam.",
                   proposed="We teach one lesson at a time."), judge)
    assert judge.asked == [{"follows_rule", "keeps_offer", "keeps_action"}]
    assert "Never mock or compare" in judge.states[0]["rule"]


async def test_a_fix_that_keeps_the_dig_is_dropped_even_if_content_is_kept():
    f, _ = await _run(Fix(key="", explanation="x", action="replace", original="a scam", proposed="not great"),
                      Judge(follows=0.2, keeps=0.95))
    assert f.suggestion is None


async def test_a_fix_that_drops_the_offer_is_dropped_even_if_it_follows_the_rule():
    f, _ = await _run(Fix(key="", explanation="x", action="rewrite", original="StudyMax is a scam. Come learn with us.",
                          proposed="We teach."), Judge(follows=0.95, keeps=0.3))
    assert f.suggestion is None


async def test_the_brands_examples_reach_the_model():
    _, llm = await _run(Fix(key="", explanation="x", action="none", original="", proposed=""), Judge())
    assert "<bad>Unlike some other apps, we actually teach</bad>" in llm.seen[0]
    assert "<good>Learn Python in six weeks</good>" in llm.seen[0]


async def test_a_deleted_sentence_is_judged_as_removed():
    judge = Judge()
    await _run(Fix(key="", explanation="x", action="delete", original="StudyMax is a scam. Come learn with us.",
                   proposed=""), judge)
    assert judge.states[0]["revised"] == "(removed)"


async def test_a_fix_with_a_number_the_creator_never_wrote_is_dropped_before_the_judge():
    judge = Judge()
    f, _ = await _run(Fix(key="", explanation="x", action="rewrite", original="StudyMax is a scam.",
                          proposed="Join 500 learners who love us."), judge)
    assert f.suggestion is None and judge.states == []


async def test_action_none_is_no_fix_even_with_text_filled_in():
    f, _ = await _run(Fix(key="", explanation="x", action="none", original="StudyMax is a scam.",
                          proposed="We teach."), Judge())
    assert f.suggestion is None


async def test_the_floors_apply_to_the_weaker_content_answer_and_the_rule_answer():
    fix = Fix(key="", explanation="x", action="rewrite", original="StudyMax is a scam.", proposed="We teach.")
    assert (await _run(fix, Judge(follows=0.5, keeps=0.6)))[0].suggestion is not None  # both exactly at the floor
    assert (await _run(fix, Judge(follows=0.49, keeps=0.9)))[0].suggestion is None
    assert (await _run(fix, Judge(follows=0.9, keeps=0.59)))[0].suggestion is None
    f, _ = await _run(fix, Judge(follows=0.9, keeps=0.7))
    assert f.suggestion.intent_preserved == 0.7  # the weaker of offer and action


def test_numbers_are_compared_by_value_not_spelling():
    from verytas.prism.suggest import _new_numbers

    assert not _new_numbers("Only $5.00 today", "Just $5 today")
    assert not _new_numbers("Two days left", "2 days left")
    assert not _new_numbers("1,200 learners", "1200 learners")
    assert _new_numbers("Save 40%", "Save 50%")


def test_a_deletion_takes_one_space_with_it_unless_an_edit_starts_there():
    from verytas.api.content import _splice

    text = "Learn with us. StudyMax is a scam. Enrol today."
    start = text.index("StudyMax")
    end = start + len("StudyMax is a scam.")
    assert _splice(text, [(start, end, "", 1)])[0] == "Learn with us. Enrol today."
    # Deleting the last sentence takes the space before it instead.
    last = text.index("Enrol")
    assert _splice(text, [(last, len(text), "", 1)])[0] == "Learn with us. StudyMax is a scam."
    # An edit starting right after the deletion keeps its offsets and the space stays.
    nxt = end + 1
    out, done = _splice(text, [(start, end, "", 1), (end, nxt, " ", 2)])
    assert out == "Learn with us.  Enrol today." and done[0][:2] == (start, end)


class FlakyJudge(Judge):
    """Passes the first fix it sees, rejects the second, and is down by the time a repair asks."""

    async def ask(self, state, questions):
        self.states.append(state)
        if len(self.states) == 1:
            return {"follows_rule": Answer("noul", 0.9), "keeps_offer": Answer("noul", 0.9),
                    "keeps_action": Answer("noul", 0.95)}
        if len(self.states) == 2:
            return {"follows_rule": Answer("noul", 0.9), "keeps_offer": Answer("noul", 0.1),
                    "keeps_action": Answer("noul", 0.95)}
        raise ConnectionError("judge unreachable")


def test_a_repair_that_fails_keeps_the_fixes_that_already_passed():
    import asyncio

    def finding(quote: str) -> RawFinding:
        return RawFinding(unit_id="u", category="messaging", title="Dig at a rival", explanation="",
                          confidence=0.8, checker="semantic", rule_code="MSG-RIVALS", quote=quote,
                          needs_explanation=True)

    from verytas.prism.suggest import RepairTask

    class RepairingLLM(OneFixLLM):
        async def run(self, task):
            if isinstance(task, RepairTask):  # a different edit, so the repair reaches the judge
                return FixList(fixes=[Fix(key=k, explanation="x", action="replace", original="Unlike other apps",
                                          proposed="With us") for k, _, _ in task.items])
            return await super().run(task)

    good, bad = finding("Unlike other apps, we teach."), finding("Unlike other apps, save 20% today.")
    llm = RepairingLLM(Fix(key="0", explanation="Digs at rivals.", action="delete", original="Unlike other apps, ",
                           proposed=""))
    judge = FlakyJudge()
    asyncio.run(explain_and_fix([good, bad], {"MSG-RIVALS": RIVALS}, llm, judge))
    assert len(judge.states) == 3  # the repair did ask, and the judge was down
    assert good.suggestion is not None and good.suggestion.gate["keeps_offer"] == 0.9
    assert bad.suggestion is None
