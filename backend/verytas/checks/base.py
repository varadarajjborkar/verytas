"""Plain data passed into and out of checkers.

Checkers never touch the ORM. They take a CheckContext snapshot and return
RawFindings, which keeps them pure, fast to test, and safe to run in parallel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Unit:
    id: str  # "p2" for a paragraph, "p2.s1" for a sentence, "img:cover" for an image
    kind: str  # paragraph | sentence | image
    text: str
    start: int  # character offsets into the version body; -1 for non-text units
    end: int


@dataclass(frozen=True)
class RuleView:
    id: int
    code: str
    category: str
    kind: str
    severity: str
    title: str
    text: str
    good_examples: tuple[str, ...] = ()
    bad_examples: tuple[str, ...] = ()
    pattern: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactView:
    id: int
    statement: str
    value: float | None
    unit: str | None
    subject: str | None
    source_ref: str
    valid_from: date
    valid_to: date | None

    def valid_on(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day < self.valid_to)


@dataclass(frozen=True)
class TermView:
    id: int
    term: str
    embargo_until: date | None


@dataclass(frozen=True)
class ContactView:
    """A contact detail the company publishes (phone, email, handle or site), from the public register."""

    kind: str  # phone | email | handle | url
    value: str
    normalized: str
    label: str | None = None


@dataclass
class CheckContext:
    body: str
    units: list[Unit]
    rules: list[RuleView]
    facts: list[FactView] = field(default_factory=list)
    terms: list[TermView] = field(default_factory=list)
    contacts: list[ContactView] = field(default_factory=list)
    attachments: dict[str, Any] = field(default_factory=dict)
    channel: str = "general"
    today: date = field(default_factory=date.today)
    # How the brand's published work sounds and what it covers (checks/voice.py BrandProfile). Typed loosely so
    # this module stays import-free; None falls back to the default voice.
    profile: Any = None

    def rules_with(self, pattern_type: str) -> list[RuleView]:
        return [r for r in self.rules if r.pattern.get("type") == pattern_type]

    def rule(self, code: str) -> RuleView | None:
        return next((r for r in self.rules if r.code == code), None)

    def units_of(self, kind: str) -> list[Unit]:
        return [u for u in self.units if u.kind == kind]


@dataclass
class SuggestedEdit:
    original: str
    proposed: str
    rationale: str
    intent_preserved: float | None = None
    model: str | None = None


@dataclass
class RawFinding:
    unit_id: str
    category: str
    title: str
    explanation: str
    confidence: float
    checker: str
    rule_code: str | None = None
    fact_id: int | None = None
    quote: str | None = None
    span_start: int | None = None
    span_end: int | None = None
    suggestion: SuggestedEdit | None = None
    model: str | None = None  # set when an AI model produced or scored this finding
    needs_explanation: bool = False  # deterministic findings arrive pre-explained
    # Surrounding text (containing `quote`) shown to the models that explain, fix
    # and intent-check this finding. Never highlighted or edited itself.
    context: str | None = None
    source: str = "body"  # which text the span points into (see Source)
    locator: dict[str, Any] | None = None  # page / image / pixel box for non-body sources
    # Set by the intent and dispute agents: the highest level this finding may
    # take (e.g. "advisory" once a reading is shown to be far-fetched), and why.
    level_cap: str | None = None
    assessment: dict[str, Any] | None = None


@dataclass
class Source:
    """A piece of text Prism found in a submission, and how it was obtained.

    The body is one source. Others come from documents and images: a PDF's
    text layer, OCR of a screenshot pasted into a page, OCR of a scanned page.
    Every source is checked with the same text pipeline; `route` and
    `confidence` say how much to trust the text itself.
    """

    id: str
    kind: str  # body | pdf_text | docx_text | ocr
    text: str
    route: str  # typed | pdf-text-layer | docx | ocr:local | ocr:vision | ocr:local+vision
    confidence: float = 1.0
    locator: dict[str, Any] = field(default_factory=dict)
    parent: str | None = None
    # For timed sources (captions, speech): (char_start, char_end, t_start, t_end)
    # per cue, so a finding's span maps back to the moment in the video.
    timeline: list[tuple[int, int, float, float]] = field(default_factory=list)
