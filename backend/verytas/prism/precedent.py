"""Precedent memory: what reviewers decided before, on the same rule, about words like these.

A reviewer who dismisses "Unlike some other apps" as a fair line once should not have to explain it again
next week, and the next reviewer should see that it was decided and why. So each reviewer decision is a
case (case-based reasoning): the rule, the flagged words, what was decided and the reason. At review
time a model-judged finding is shown its two nearest past cases on the same rule in this workspace
("Dismissed on 4 Oct by Meera: tone exception for the Gen Z channel"), and the semantic judge is given
the nearest ones as examples, so the workspace's own past decisions shape how its rules are read.

Bounded the way every learned change here is:
- tier filtered: a case from content above this content's tier is never shown or used;
- redacted: confidential terms in a past quote are masked before it is shown or sent to a model;
- a case is only an example: it never decides a finding, and mechanical findings are not touched;
- only clear outcomes are examples: an "intentional" dismissal (the rule applied, kept on purpose) or a
  "guideline unclear" one says nothing about whether the words break the rule.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.checks.base import RawFinding, RuleView
from verytas.models import (
    Content,
    ContentVersion,
    Decision,
    DecisionAction,
    Finding,
    Review,
    Rule,
    Tier,
    User,
)

SHOWN = 2  # cases shown with a finding
EXAMPLES = 2  # cases per side (breaks / fine) given to the judge for a rule
FLOOR = 0.2  # word overlap below which a past case is not "like these words"
MAX_CASES = 1000  # most recent decisions loaded per review
_QUOTE_CHARS = 280
# Dismissals that say the words don't break the rule. "intentional" says they do, and were kept anyway;
# "guideline_unclear" says nobody is sure. Neither is an example of compliant text.
_CLEARS = {"false_positive", "not_applicable"}
# Letters of any script, with Indic vowel signs and Latin accents, which `\w` alone splits words on.
_MARKS = "\u0300-\u036f\u0900-\u0dff"
_WORD = re.compile(f"(?:[^\\W\\d_]|[{_MARKS}])(?:[\\w'{_MARKS}])+")
_STOP = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "is", "are", "was", "were", "be",
    "our", "we", "us", "you", "your", "it", "its", "this", "that", "at", "as", "from", "but", "so", "if", "not",
    "just", "all", "can", "will", "has", "have", "do", "does", "get",
    # Hinglish and Hindi function words, common in Indian brand captions.
    "hai", "hain", "ka", "ki", "ke", "ko", "se", "mein", "aur", "ye", "yeh", "wo", "woh", "bhi", "toh", "na", "nahi",
    "है", "हैं", "का", "की", "के", "को", "से", "में", "और", "यह", "वह", "भी", "तो", "नहीं",
    # What masking leaves behind: a masked word is no evidence that two lines are alike.
    "confidential", "email", "phone", "card", "secret",
})
_VERB = {DecisionAction.accepted: "Upheld", DecisionAction.edited: "Fixed", DecisionAction.rejected: "Dismissed"}


def words(text: str) -> frozenset[str]:
    return frozenset(_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP)


def _stem(w: str) -> str:
    # Plural to singular, the only folding worth its errors here: "classes" and "class" stay apart from "cla".
    # "-ches" is left to the plain rule: "caches" and "headaches" are e-final, more often than "launches" isn't.
    if len(w) > 4 and w.endswith(("sses", "shes", "xes")):
        return w[:-2]
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) else w


@dataclass(frozen=True)
class Case:
    rule_code: str
    quote: str  # redacted
    action: str  # accepted | edited | rejected
    reason_code: str | None
    reason_text: str | None
    by: str
    at: datetime
    finding_id: int
    terms: frozenset[str] = field(default_factory=frozenset)

    @property
    def breaks(self) -> bool | None:
        """What the case says about its words: they break the rule, they don't, or it doesn't say."""
        if self.action in ("accepted", "edited"):
            return True
        return False if self.reason_code in _CLEARS else None

    def shown(self) -> dict:
        verb = _VERB[DecisionAction(self.action)]
        why = (self.reason_text or (self.reason_code or "").replace("_", " ")).strip()
        return {"finding_id": self.finding_id, "action": self.action, "reason_code": self.reason_code,
                "summary": f"{verb} on {self.at.day} {self.at:%b} by {self.by}" + (f": {why}" if why else ""),
                "quote": self.quote}


@dataclass
class Book:
    cases: dict[str, list[Case]] = field(default_factory=dict)  # by rule code, newest first

    def nearest(self, rule_code: str, text: str, k: int = SHOWN, *, exclude: set[int] | None = None,
                where: Callable[[Case], bool] | None = None, within: bool = False) -> list[Case]:
        """The k closest cases by word overlap. `within` scores how much of each case appears in `text`,
        for a whole post compared with short flagged quotes, where the union would drown every match."""
        mine = words(text)
        if not mine:
            return []
        scored = []
        for c in self.cases.get(rule_code, []):
            if (exclude and c.finding_id in exclude) or (where and not where(c)) or not c.terms:
                continue
            if within and len(c.terms) < 3:
                continue  # one or two words appear in any long post; that is no likeness
            score = len(mine & c.terms) / (len(c.terms) if within else len(mine | c.terms))
            if score >= FLOOR:
                scored.append((score, c.at, c))
        scored.sort(key=lambda t: (-t[0], -t[1].timestamp()))
        return [c for _, _, c in scored[:k]]

    def with_examples(self, rule: RuleView, text: str) -> RuleView:
        """The rule with this workspace's nearest decided cases added to its examples, for the judge."""
        if rule.kind != "semantic" or rule.code not in self.cases:
            return rule
        bad = [c.quote for c in self.nearest(rule.code, text, EXAMPLES, where=lambda c: c.breaks is True, within=True)]
        good = [c.quote for c in self.nearest(rule.code, text, EXAMPLES, where=lambda c: c.breaks is False,
                                              within=True)]
        if not (bad or good):
            return rule
        return dataclasses.replace(rule, bad_examples=(*bad, *rule.bad_examples),
                                   good_examples=(*good, *rule.good_examples))

    def attach(self, findings: list[RawFinding], sources: dict[str, str]) -> int:
        """Give each model-judged finding its nearest past cases. Returns how many got any."""
        n = 0
        for f in findings:
            if f.model is None or not f.rule_code:
                continue
            text = f.quote or sources.get(f.source, "")
            near = self.nearest(f.rule_code, text)
            if near:
                f.precedents = [c.shown() for c in near]
                n += 1
        return n

    def summary(self) -> dict:
        return {"cases": sum(len(v) for v in self.cases.values()), "rules": len(self.cases)}


async def load(session: AsyncSession, workspace_id: int, tier: Tier, mask: Callable[[str], str]) -> Book:
    """The workspace's decided cases on content at or below `tier`, newest first, confidential terms and
    personal data masked (for showing; anything sent to a model is redacted again on the way out)."""
    allowed = [t for t in Tier if t.rank <= tier.rank]
    last = select(func.max(Decision.id)).group_by(Decision.finding_id).scalar_subquery()
    rows = await session.execute(
        select(Rule.code, Finding.id, Finding.quote, Decision.action, Decision.reason_code, Decision.reason_text,
               Decision.created_at, User.name)
        .join(Finding, Finding.rule_id == Rule.id)
        .join(Decision, Decision.finding_id == Finding.id)
        .join(User, User.id == Decision.actor_id)
        .join(Review, Review.id == Finding.review_id)
        .join(ContentVersion, ContentVersion.id == Review.version_id)
        .join(Content, Content.id == ContentVersion.content_id)
        .where(Rule.workspace_id == workspace_id, Content.workspace_id == workspace_id, Content.tier.in_(allowed),
               Decision.id.in_(last), Decision.carried_from_id.is_(None),
               Decision.action.in_([DecisionAction.accepted, DecisionAction.edited, DecisionAction.rejected]),
               Finding.quote.is_not(None))
        .order_by(Decision.created_at.desc()).limit(MAX_CASES))
    found = rows.all()

    def build() -> Book:
        book = Book()
        for code, fid, quote, action, reason, why, at, by in found:
            # Masked before the cut, so a codename across the cut can't leave a readable prefix.
            q = mask(quote)[:_QUOTE_CHARS]
            book.cases.setdefault(code, []).append(Case(code, q, action.value, reason, mask(why) if why else None,
                                                        by, at, fid, words(q)))
        return book

    # Hundreds of term patterns over a thousand quotes is CPU work; keep it off the event loop.
    return await asyncio.to_thread(build)
