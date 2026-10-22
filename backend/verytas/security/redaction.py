"""Egress filter: nothing confidential reaches an external model in the clear.

Confidential terms and common PII are swapped for stable placeholders before a
request leaves the process and swapped back in the reply, so the model can
still quote and reason about "[[TERM_1]]" while never seeing the codename.
The wrappers apply this to every LLM task and judge call without the checks
having to know about it.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from verytas.providers.base import Answer, JudgeProvider, LLMProvider, Question, StructuredTask
from verytas.security.terms import sub_folded, term_pattern

_PII = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("SECRET", re.compile(r"\b(?:sk|pk|api|key|token)[-_][A-Za-z0-9]{16,}\b", re.IGNORECASE)),
]


class Redactor:
    def __init__(self, confidential_terms: list[str]) -> None:
        # Longest first so "Project Lumen Pro" is replaced before "Project Lumen".
        terms = sorted({t for t in confidential_terms if t.strip()}, key=len, reverse=True)
        # Loose matching: hyphenated, glued, re-spaced and plural variants are
        # redacted too. Over-redaction is cheap; a leaked codename is not.
        self._terms = [term_pattern(t, loose=True) for t in terms]
        self._forward: dict[str, str] = {}
        self._reverse: dict[str, str] = {}
        self.count = 0

    def _placeholder(self, kind: str, original: str) -> str:
        key = original.lower() if kind == "TERM" else original
        if key not in self._forward:
            n = sum(1 for p in self._reverse if p.startswith(f"[[{kind}_")) + 1
            ph = f"[[{kind}_{n}]]"
            self._forward[key] = ph
            self._reverse[ph] = original
        self.count += 1
        return self._forward[key]

    def redact(self, text: str) -> str:
        for pattern in self._terms:
            # Folded matching: a codename hidden with a zero-width space or a
            # look-alike letter would otherwise reach the model unredacted.
            text = sub_folded(pattern, text, lambda original: self._placeholder("TERM", original))
        for kind, pattern in _PII:
            text = pattern.sub(lambda m, k=kind: self._pii(k, m.group(0)), text)
        return text

    def _pii(self, kind: str, match: str) -> str:
        # Dates and figures look like phone numbers to a regex; real phone
        # numbers carry at least ten digits.
        if kind == "PHONE" and sum(c.isdigit() for c in match) < 10:
            return match
        return self._placeholder(kind, match)

    def restore(self, text: str) -> str:
        for ph, original in self._reverse.items():
            text = text.replace(ph, original)
        return text

    def redact_any(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, list):
            return [self.redact_any(v) for v in value]
        if isinstance(value, dict):
            # Leave binary payloads (base64 images) alone.
            return {k: v if k == "data" else self.redact_any(v) for k, v in value.items()}
        return value

    def restore_any(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.restore(value)
        if isinstance(value, list):
            return [self.restore_any(v) for v in value]
        if isinstance(value, dict):
            return {k: self.restore_any(v) for k, v in value.items()}
        return value


class _RedactedTask:
    def __init__(self, inner: StructuredTask[Any], redactor: Redactor) -> None:
        self._inner = inner
        self._redactor = redactor
        self.name, self.system, self.schema, self.fast = inner.name, inner.system, inner.schema, inner.fast

    def user_content(self) -> Any:
        return self._redactor.redact_any(self._inner.user_content())

    def heuristic(self) -> Any:
        return self._inner.heuristic()


class RedactingLLM:
    def __init__(self, inner: LLMProvider, redactor: Redactor) -> None:
        self._inner = inner
        self._redactor = redactor
        self.name = inner.name

    async def run[T: BaseModel](self, task: StructuredTask[T]) -> T:
        result = await self._inner.run(_RedactedTask(task, self._redactor))
        return task.schema.model_validate(self._redactor.restore_any(result.model_dump()))


class RedactingJudge:
    def __init__(self, inner: JudgeProvider, redactor: Redactor) -> None:
        self._inner = inner
        self._redactor = redactor
        self.name = inner.name

    async def ask(self, state: str | dict[str, Any], questions: dict[str, Question]) -> dict[str, Answer]:
        # Questions carry rule text, which is internal but may name codenames too.
        safe_q = {
            k: Question(q.type, self._redactor.redact(q.instructions), self._redactor.redact_any(q.criteria), q.hints)
            for k, q in questions.items()
        }
        return await self._inner.ask(self._redactor.redact_any(state), safe_q)
