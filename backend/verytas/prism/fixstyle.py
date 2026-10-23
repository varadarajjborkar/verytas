"""Learning from fixes: which kind of edit this workspace's reviewers take, rule by rule.

A model-written fix is one of three operations (prism/suggest.py): swap the offending words, rewrite the
sentence, or delete it. Reviewers answer each one: they accept the finding with its fix, or they accept it
and write their own edit instead ("edited"). A dismissed finding says nothing about its fix. So each rule
keeps, per operation, how often its fixes were taken, and two things reach the fix prompt:

- a preferred operation, chosen by Thompson sampling over a Beta posterior per operation (so an
  operation that has had few chances still gets tried now and then, instead of the first lucky one
  winning for good);
- the reviewers' own edits on the nearest similar lines (Reflexion-style memory: what was done instead,
  in the brand's words), masked, and only from content at or below this content's tier.

Bounded like every learned change here: both are hints in the prompt, the fix gate judges every
proposal exactly as before, a hint appears only once a rule has MIN_DECIDED decided fixes, and nothing
is learned from findings that were dismissed. Counts and edits alike come only from content at or below
the reviewed content's tier, and every learned line is escaped: a reviewer's edit began as a creator's
text, so it must not be able to close its own tag and forge a <prefer> of its own.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.models import Content, ContentVersion, Decision, DecisionAction, Finding, Review, Rule, Suggestion, Tier
from verytas.prism.precedent import words

OPERATIONS = ("replace", "rewrite", "delete")
MIN_DECIDED = 4  # decided fixes on a rule before any operation is preferred
LESSONS = 2
FLOOR = 0.2
_CHARS = 280
MAX_ROWS = 1000


@dataclass(frozen=True)
class Lesson:
    rule_code: str
    original: str  # the flagged words, masked
    edited: str  # what the reviewer wrote instead, masked
    at: datetime
    terms: frozenset[str]


@dataclass
class FixStyle:
    # rule code -> operation -> [taken, not taken]
    tally: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    lessons: dict[str, list[Lesson]] = field(default_factory=dict)  # newest first
    seed: int | None = None  # with a seed, each rule's draw depends only on (seed, rule): reproducible per version
    rng: random.Random = field(default_factory=random.Random)
    chosen: dict[str, str] = field(default_factory=dict)  # what this review preferred, for the record

    def record(self, rule_code: str, operation: str, taken: bool) -> None:
        row = self.tally.setdefault(rule_code, {op: [0, 0] for op in OPERATIONS})
        row[operation][0 if taken else 1] += 1

    def prefer(self, rule_code: str) -> str | None:
        """One draw per rule per review: the operation whose sampled acceptance rate is highest."""
        if rule_code in self.chosen:
            return self.chosen[rule_code]
        row = self.tally.get(rule_code)
        if not row or sum(a + b for a, b in row.values()) < MIN_DECIDED:
            return None
        # Seeded per rule, not shared: fix batches run concurrently, so a shared stream would hand out draws
        # in whatever order the tasks happened to ask.
        rng = random.Random(f"{self.seed}:{rule_code}") if self.seed is not None else self.rng
        draws = {op: rng.betavariate(1 + a, 1 + b) for op, (a, b) in row.items()}
        best = max(draws, key=draws.get)
        self.chosen[rule_code] = best
        return best

    def hint(self, rule_code: str | None, text: str, *, prefer: bool = True) -> str:
        """The prompt lines for one flagged item: the operation to try first and the nearest reviewer edits.
        A repair passes prefer=False: it was told what went wrong, and that outranks any habit."""
        if not rule_code:
            return ""
        out = []
        op = self.prefer(rule_code) if prefer else None
        if op is not None:
            row = self.tally[rule_code]
            seen = ", ".join(f"{name} {a} of {a + b}" for name, (a, b) in row.items() if a + b)
            out.append(f"<prefer>{op}</prefer>\n<record>fixes reviewers took for this rule here: {seen}</record>\n")
        mine = words(text)
        near = sorted(((len(mine & lesson.terms) / len(mine | lesson.terms), lesson)
                       for lesson in self.lessons.get(rule_code, []) if mine and lesson.terms),
                      key=lambda t: (-t[0], -t[1].at.timestamp()))
        for score, lesson in near[:LESSONS]:
            if score >= FLOOR:
                out.append(f"<reviewer_fix>{_esc(lesson.original)} => {_esc(lesson.edited)}</reviewer_fix>\n")
        return "".join(out)

    def summary(self) -> dict:
        return {"rules": {code: {op: {"taken": a, "not_taken": b} for op, (a, b) in row.items() if a + b}
                          for code, row in self.tally.items()},
                "preferred": dict(self.chosen), "lessons": sum(len(v) for v in self.lessons.values())}


def _esc(text: str) -> str:
    # As the judge renders content (providers/ollama_judge.py): no tag can be opened or closed from inside.
    return text.replace("&", "&amp;").replace("<", "&lt;")


def outcome(action: DecisionAction) -> bool | None:
    """Was the fix taken? Accepted with it: yes. The reviewer wrote their own: no. Dismissed: no answer."""
    return True if action is DecisionAction.accepted else False if action is DecisionAction.edited else None


async def load(session: AsyncSession, workspace_id: int, tier: Tier, mask: Callable[[str], str],
               seed: int | None = None) -> FixStyle:
    """This workspace's decided model-written fixes on content at or below `tier`: the reviewers' own words
    and, like calibration's counts, the tallies too, which say how much work there is above it."""
    last = select(func.max(Decision.id)).group_by(Decision.finding_id).scalar_subquery()
    rows = (await session.execute(
        select(Rule.code, Suggestion.action, Decision.action, Decision.edited_text, Finding.quote,
               Decision.created_at)
        .join(Finding, Finding.rule_id == Rule.id).join(Suggestion, Suggestion.finding_id == Finding.id)
        .join(Decision, Decision.finding_id == Finding.id).join(Review, Review.id == Finding.review_id)
        .join(ContentVersion, ContentVersion.id == Review.version_id)
        .join(Content, Content.id == ContentVersion.content_id)
        .where(Rule.workspace_id == workspace_id, Content.workspace_id == workspace_id, Decision.id.in_(last),
               Suggestion.model.is_not(None), Suggestion.action.in_(OPERATIONS),
               Content.tier.in_([t for t in Tier if t.rank <= tier.rank]),
               Decision.action.in_([DecisionAction.accepted, DecisionAction.edited]))
        .order_by(Decision.created_at.desc()).limit(MAX_ROWS))).all()

    def build() -> FixStyle:
        style = FixStyle(seed=seed)
        for code, op, action, edited, original, at in rows:
            taken = outcome(action)
            style.record(code, op, bool(taken))
            # A reviewer's edit replaces the whole flagged span, so the lesson pairs it with the quote.
            if not taken and edited and original:
                before, after = mask(original)[:_CHARS], mask(edited)[:_CHARS]
                style.lessons.setdefault(code, []).append(Lesson(code, before, after, at, words(before)))
        return style

    return await asyncio.to_thread(build)
