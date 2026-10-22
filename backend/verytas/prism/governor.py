"""The governor: the board's "unnamed agents that handle load".

Bounds concurrency, enforces timeouts, trips a circuit breaker when a provider
keeps failing, and converts every failure into an explicit "not checked"
outcome. A check that could not run is never reported as a pass.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from verytas.checks.base import RawFinding
from verytas.providers.base import (
    Answer,
    BudgetExceeded,
    JudgeProvider,
    LLMProvider,
    ProviderError,
    ProviderUnavailable,
    Question,
    StructuredTask,
)

log = logging.getLogger("verytas.governor")


@dataclass
class TaskOutcome:
    name: str
    status: Literal["ok", "not_checked", "failed"]
    findings: list[RawFinding] = field(default_factory=list)
    note: str | None = None
    duration_ms: int = 0


class CircuitBreaker:
    """Opens after `threshold` consecutive failures; half-opens after `cooldown_s`."""

    def __init__(self, threshold: int = 3, cooldown_s: float = 30.0) -> None:
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.cooldown_s:
            self.opened_at = None  # half-open: let the next call probe
            self.failures = self.threshold - 1
            return False
        return True

    def record(self, ok: bool) -> None:
        if ok:
            self.failures, self.opened_at = 0, None
        else:
            self.failures += 1
            if self.failures >= self.threshold:
                self.opened_at = time.monotonic()


class GuardedLLM:
    def __init__(self, inner: LLMProvider, breaker: CircuitBreaker) -> None:
        self._inner, self._breaker, self.name = inner, breaker, inner.name

    async def run[T: BaseModel](self, task: StructuredTask[T]) -> T:
        if self._breaker.open:
            raise ProviderUnavailable(f"{self.name} circuit open after repeated failures")
        try:
            result = await self._inner.run(task)
        except ProviderUnavailable:
            self._breaker.record(False)
            raise
        self._breaker.record(True)
        return result


class GuardedJudge:
    def __init__(self, inner: JudgeProvider, breaker: CircuitBreaker) -> None:
        self._inner, self._breaker, self.name = inner, breaker, inner.name

    async def ask(self, state: str | dict[str, Any], questions: dict[str, Question]) -> dict[str, Answer]:
        if self._breaker.open:
            raise ProviderUnavailable(f"{self.name} circuit open after repeated failures")
        try:
            result = await self._inner.ask(state, questions)
        except ProviderUnavailable:
            self._breaker.record(False)
            raise
        self._breaker.record(True)
        return result


class Governor:
    def __init__(self, max_concurrency: int, timeout_s: float) -> None:
        self._sem = asyncio.Semaphore(max_concurrency)
        self._timeout_s = timeout_s

    async def run(self, name: str, work: Callable[[], Awaitable[list[RawFinding]]]) -> TaskOutcome:
        started = time.monotonic()

        def done(status, findings=None, note=None) -> TaskOutcome:
            return TaskOutcome(name, status, findings or [], note, int((time.monotonic() - started) * 1000))

        async with self._sem:
            try:
                findings = await asyncio.wait_for(work(), timeout=self._timeout_s)
            except TimeoutError:
                return done("not_checked", note=f"timed out after {self._timeout_s:g}s")
            except BudgetExceeded as exc:
                return done("not_checked", note=str(exc))
            except ProviderError as exc:
                return done("not_checked", note=str(exc))
            except Exception as exc:  # noqa: BLE001, one bad checker must not sink the review
                log.exception("check %s crashed", name)
                return done("failed", note=f"{type(exc).__name__}: internal error")
        return done("ok", findings)
