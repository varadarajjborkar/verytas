"""Second look: must-rule questions are also put to the larger model, and its answer decides.

The semantic judge runs on a small, fast model, which is right for most questions. On a must rule a
wrong answer is expensive either way (a real problem missed, or a reviewer sent after a false one), so
those questions get a second judge. The first design was a cascade (FrugalGPT): re-ask only answers
close to the flag threshold. Measured on hand-labelled must-rule sentences (evals/second_look), it
never fired: the small judge's mistakes come back at its highest certainty, not near the line, which
is the overconfidence of verbalised confidence that Xiong et al. (ICLR 2024) describe. The larger model
was right more often (30 of 32 against 27) at no extra time per call, so must-rule questions now go to
both judges at once, and the larger one's answer is the one used.

A review spends at most `budget` second-judge calls (one per paragraph, carrying all its must-rule
questions). Every answer pair is recorded and shown under "How it was checked"; paragraphs left to the
first judge because the budget ran out are counted there too, so nobody reads them as double-checked.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from verytas.checks.base import RuleView, Unit
from verytas.providers.base import Answer, JudgeProvider, ProviderError, Question


@dataclass
class SecondLook:
    judge: JudgeProvider
    budget: int
    log: list[dict[str, Any]] = field(default_factory=list)
    unasked: int = 0  # paragraphs with must-rule questions that only the first judge answered
    meter: Any = None  # its own UsageMeter, so its spend is reported and capped apart from the first judge's

    def at(self, source: str) -> _At:
        """This second look, for the paragraphs of one source (the budget and the record are shared)."""
        return _At(self, source)

    def start(self, paragraphs: list[Unit], questions: dict[str, Question], rules: dict[str, RuleView]
              ) -> list[asyncio.Task | None]:
        """The second judge's calls, started next to the first judge's so they add no wait."""
        must = {k: q for k, q in questions.items() if rules[k].severity == "must" and q.type == "noul"}
        if not must:
            return [None] * len(paragraphs)
        calls: list[asyncio.Task | None] = []
        for p in paragraphs:
            if self.budget > 0:
                self.budget -= 1
                call = asyncio.ensure_future(self._timed(p.text, must))
                # A call left behind when the first judge fails is cancelled unawaited; read its outcome so
                # an error it already raised isn't logged as never retrieved.
                call.add_done_callback(lambda t: t.cancelled() or t.exception())
                calls.append(call)
            else:
                self.unasked += 1
                calls.append(None)
        return calls

    async def _timed(self, text: str, must: dict[str, Question]) -> tuple[dict[str, Answer], int]:
        started = time.monotonic()
        answers = await self.judge.ask(text, must)
        return answers, int((time.monotonic() - started) * 1000)

    async def merge(self, paragraphs: list[Unit], results: list[dict[str, Answer]], calls: list[asyncio.Task | None],
                    rules: dict[str, RuleView], thresholds: dict[str, float], source: str = "body",
                    ) -> tuple[list[dict[str, Answer]], set[tuple[int, str]]]:
        """`results` with the second judge's answers in place of the first's, and which (paragraph, question)
        it answered. A second judge that fails leaves the first answers, and the record says so."""
        out = [dict(a) for a in results]
        answered: set[tuple[int, str]] = set()
        for i, call in enumerate(calls):
            if call is None:
                continue
            para = paragraphs[i]
            try:
                answers, ms = await call
            except ProviderError as exc:
                for key, first in results[i].items():
                    if rules[key].severity == "must" and first.type == "noul":
                        self.log.append(self._entry(rules[key], source, para, first, thresholds[key])
                                        | {"second": None, "outcome": "unavailable", "note": str(exc)[:200]})
                continue
            for key, again in answers.items():
                first = results[i].get(key)
                if first is None or again.type != "noul":
                    continue
                out[i][key] = again
                answered.add((i, key))
                before, after = first.p_yes >= thresholds[key], again.p_yes >= thresholds[key]
                self.log.append(self._entry(rules[key], source, para, first, thresholds[key]) | {
                    "second": round(again.p_yes, 3), "ms": ms,
                    "outcome": ("flagged" if after and not before else "cleared" if before and not after
                                else "confirmed flag" if after else "confirmed clear")})
        return out, answered

    def _entry(self, rule: RuleView, source: str, para: Unit, first: Answer, threshold: float) -> dict[str, Any]:
        return {"rule": rule.code, "source": source, "unit": para.id, "first": round(first.p_yes, 3),
                "threshold": threshold, "model": self.judge.name}

    def summary(self) -> dict[str, Any]:
        return {"model": self.judge.name, "asked": self.log, "unasked": self.unasked,
                "usage": self.meter.by_provider if self.meter is not None else {}}


@dataclass
class _At:
    look: SecondLook
    source: str

    @property
    def judge(self) -> JudgeProvider:
        return self.look.judge

    def start(self, *args: Any) -> list[asyncio.Task | None]:
        return self.look.start(*args)

    async def merge(self, *args: Any) -> tuple[list[dict[str, Answer]], set[tuple[int, str]]]:
        return await self.look.merge(*args, source=self.source)
