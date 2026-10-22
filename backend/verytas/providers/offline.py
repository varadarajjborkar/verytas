"""Deterministic stand-ins for the hosted models.

Used in tests, in CI, and for keyless demos. They are intentionally simple but
not random: same input, same answer, so review results are reproducible.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from verytas.providers.base import Answer, Question, StructuredTask

_TOKEN = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    # Containment rather than Jaccard: a short bad example inside a long unit
    # should still score high.
    return len(ta & tb) / min(len(ta), len(tb))


class OfflineJudge:
    name = "offline/judge"

    async def ask(self, state: str | dict[str, Any], questions: dict[str, Question]) -> dict[str, Answer]:
        # Only the text under judgement counts. List fields carry the evidence the
        # hints are drawn from; scored too, every claim "matched" its own evidence.
        text = state if isinstance(state, str) else " ".join(v for v in state.values() if isinstance(v, str))
        return {name: self._answer(text, q) for name, q in questions.items()}

    def _answer(self, text: str, q: Question) -> Answer:
        if q.type == "noul":
            yes = max((_similarity(text, ex) for ex in q.hints.get("yes", [])), default=0.0)
            no = max((_similarity(text, ex) for ex in q.hints.get("no", [])), default=0.0)
            p = 0.5 + 0.5 * (yes - no) if (yes or no) else 0.2
            return Answer("noul", round(min(max(p, 0.0), 1.0), 4))
        if q.type == "score":
            levels = q.criteria if isinstance(q.criteria, list) else ["low", "high"]
            mid = (len(levels) - 1) / 2
            return Answer("score", mid, 0.5, {str(i): 1 / len(levels) for i in range(len(levels))})
        labels = list(q.criteria) if isinstance(q.criteria, dict) else ["other"]
        return Answer("choice", labels[0], 0.5, {lab: 1 / len(labels) for lab in labels})


class OfflineLLM:
    name = "offline/llm"

    async def run[T: BaseModel](self, task: StructuredTask[T]) -> T:
        return task.heuristic()
