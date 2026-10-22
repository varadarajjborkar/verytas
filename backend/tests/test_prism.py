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
