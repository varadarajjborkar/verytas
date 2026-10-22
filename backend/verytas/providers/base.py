"""Provider interfaces.

Two kinds of model sit behind the checks:

* a JudgeProvider answers typed questions (yes/no, ordered score, choice) about
  a piece of content with probabilities. TypeSafe Jev in production.
* an LLMProvider produces structured text work: claim extraction, explanations
  and minimal-edit rewrites. Claude in production.

Both have offline implementations so the full pipeline runs in tests and demos
without network access or keys.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel


class ProviderError(Exception):
    """Base for anything that stops a provider from answering."""


class ProviderUnavailable(ProviderError):
    """Network, auth, quota or server failure after retries. The governor treats
    the affected check as "not checked" rather than passing it."""


class ProviderRefusal(ProviderError):
    """The model declined the request."""


class BudgetExceeded(ProviderError):
    """The review's token budget is spent."""


QuestionType = Literal["noul", "score", "choice"]


@dataclass(frozen=True)
class Question:
    type: QuestionType
    instructions: str
    # noul: {"true": "...", "false": "..."}; choice: {label: description};
    # score: ordered list of level descriptions, lowest first.
    criteria: dict[str, str] | list[str] | None = None
    # Local-only context for the offline judge (never sent to the API): example
    # texts that should push the answer towards yes / no.
    hints: dict[str, list[str]] = field(default_factory=dict)

    def to_api(self) -> dict[str, Any]:
        body: dict[str, Any] = {"type": self.type, "instructions": self.instructions}
        if self.criteria is not None:
            body["criteria"] = self.criteria
        return body


@dataclass(frozen=True)
class Answer:
    type: QuestionType
    # noul: P(yes); score: probability-weighted level index; choice: winning label.
    value: float | str
    confidence: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)

    @property
    def p_yes(self) -> float:
        if self.type != "noul":
            raise TypeError("p_yes is only defined for noul answers")
        return float(self.value)


class UsageMeter:
    """Counts tokens per review and enforces the budget (architecture 6.3)."""

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.by_provider: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    @property
    def total(self) -> int:
        return sum(v["input"] + v["output"] for v in self.by_provider.values())

    def check(self) -> None:
        if self.total >= self.budget:
            raise BudgetExceeded(f"review token budget of {self.budget} spent")

    def add(self, provider: str, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            slot = self.by_provider.setdefault(provider, {"input": 0, "output": 0, "calls": 0})
            slot["input"] += input_tokens
            slot["output"] += output_tokens
            slot["calls"] += 1


class JudgeProvider(Protocol):
    name: str

    async def ask(self, state: str | dict[str, Any], questions: dict[str, Question]) -> dict[str, Answer]: ...


class StructuredTask[T: BaseModel](Protocol):
    """A unit of LLM work. `heuristic` is the offline answer, so every task can
    run without a model, and tests exercise the same code path as production."""

    name: str
    system: str
    schema: type[T]
    fast: bool

    def user_content(self) -> str | list[dict[str, Any]]: ...

    def heuristic(self) -> T: ...


class LLMProvider(Protocol):
    name: str

    async def run[T: BaseModel](self, task: StructuredTask[T]) -> T: ...
