from __future__ import annotations

import asyncio
import contextlib

from tests.helpers import rule
from verytas.checks.base import RawFinding
from verytas.models import Level
from verytas.prism.governor import CircuitBreaker, Governor, GuardedJudge
from verytas.prism.judge import level_for, scorecard
from verytas.providers.base import BudgetExceeded, ProviderUnavailable, Question


def _f(category="tone", confidence=0.9, model=None) -> RawFinding:
    return RawFinding(unit_id="p1", category=category, title="t", explanation="e", confidence=confidence,
                      checker="x", rule_code="R", model=model)


async def test_governor_turns_failures_into_not_checked():
    gov = Governor(max_concurrency=2, timeout_s=0.05)

    async def unavailable():
        raise ProviderUnavailable("down")

    async def slow():
        await asyncio.sleep(1)
        return []

    async def over_budget():
        raise BudgetExceeded("spent")

    async def crash():
        raise KeyError("bug")

    outcomes = await asyncio.gather(gov.run("a", unavailable), gov.run("b", slow), gov.run("c", over_budget),
                                    gov.run("d", crash))
    assert [o.status for o in outcomes] == ["not_checked", "not_checked", "not_checked", "failed"]
    assert "timed out" in outcomes[1].note
    assert outcomes[3].note == "KeyError: internal error"  # no internals leak into the review


async def test_circuit_breaker_opens_then_half_opens():
    calls = {"n": 0}

    class Flaky:
        name = "flaky"

        async def ask(self, state, questions):
            calls["n"] += 1
            raise ProviderUnavailable("nope")

    breaker = CircuitBreaker(threshold=2, cooldown_s=0.05)
    judge = GuardedJudge(Flaky(), breaker)
    q = {"q": Question("noul", "?")}
    for _ in range(4):
        with contextlib.suppress(ProviderUnavailable):
            await judge.ask("x", q)
    assert calls["n"] == 2 and breaker.open  # third and fourth calls short-circuited
    await asyncio.sleep(0.06)
    assert not breaker.open  # half-open lets one probe through


def test_model_only_findings_never_block():
    must = rule("R", {}, severity="must")
    assert level_for(_f(confidence=0.99), must, blocker_confidence=0.85) is Level.blocker
    assert level_for(_f(confidence=0.99, model="typesafe/jev"), must, blocker_confidence=0.85) is Level.warning
    assert level_for(_f(confidence=0.5), must, blocker_confidence=0.85) is Level.warning


def test_should_and_may_levels():
    should, may = rule("R", {}, severity="should"), rule("R", {}, severity="may")
    assert level_for(_f(confidence=0.7), should, blocker_confidence=0.85) is Level.warning
    assert level_for(_f(confidence=0.4), should, blocker_confidence=0.85) is Level.advisory
    assert level_for(_f(confidence=1.0), may, blocker_confidence=0.85) is Level.advisory


def test_scorecard_headline_is_weakest_checked_category():
    levelled = [(_f("confidentiality", 1.0), Level.blocker), (_f("tone", 0.6), Level.advisory)]
    card = scorecard(levelled, checked={"confidentiality", "tone", "claims"})
    assert card.categories["claims"]["score"] == 1.0
    assert card.categories["visual"]["score"] is None and not card.categories["visual"]["checked"]
    assert card.overall == card.categories["confidentiality"]["score"] == 0.5
    assert card.blockers == 1


async def test_no_unchecked_fix_survives_a_failing_intent_check():
    import pytest

    from verytas.prism.suggest import Fix, FixList, explain_and_fix

    class Writer:
        name = "fake/llm"

        async def run(self, task):
            return FixList(fixes=[Fix(key=k, explanation="Too jargony.", original="leverage synergies",
                                      proposed="work together") for k, _, _ in task.items])

    class DownJudge:
        name = "typesafe/jev"

        async def ask(self, state, questions):
            raise ProviderUnavailable("judge down")

    f = RawFinding(unit_id="p1", category="tone", title="t", explanation="e", confidence=0.8, checker="semantic",
                   rule_code="VOICE-01", quote="We leverage synergies.", needs_explanation=True)
    with pytest.raises(ProviderUnavailable):
        await explain_and_fix([f], {}, Writer(), DownJudge())
    assert f.suggestion is None and f.explanation == "Too jargony."


async def test_shared_slots_cap_concurrent_provider_calls():
    from verytas.providers.base import Answer

    live = {"now": 0, "peak": 0}

    class Slow:
        name = "slow"

        async def ask(self, state, questions):
            live["now"] += 1
            live["peak"] = max(live["peak"], live["now"])
            await asyncio.sleep(0.01)
            live["now"] -= 1
            return {k: Answer("noul", 0.1) for k in questions}

    judge = GuardedJudge(Slow(), CircuitBreaker(), asyncio.Semaphore(3))
    await asyncio.gather(*(judge.ask("x", {"q": Question("noul", "?")}) for _ in range(20)))
    assert live["peak"] == 3
