"""Brand events and the update chain that carries them into reviews.

An event is written once by the brand team and then reaches every review on
its own: saving it rewrites the rules it owns, and re-checks the pieces it
touches. The rules are ordinary Rule rows (so findings cite them, and old
findings keep citing the text they were judged against); the orchestrator
applies them only while the event runs, or to pieces made for it.

  EVT-<id>-BRIEF   model-judged: the event's guidance, plus "promotional posts
                   are paused" for a blackout
  EVT-<id>-AVOID   exact match: the words to avoid while it runs
  EVT-<id>-TAGS    exact: a piece tagged with the event carries its hashtag

The chain is bounded (MAX_RECHECKS per change) and audited, so one edit can't
start an unbounded number of model calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.models import (
    BrandEvent,
    Content,
    ContentStatus,
    ContentVersion,
    EventImpact,
    Review,
    Rule,
    RuleKind,
    RuleStatus,
    Severity,
)
from verytas.security.audit import append

MAX_RECHECKS = 40
# Pieces still on their way out. Drafts get the event at their next check anyway.
IN_FLIGHT = (ContentStatus.in_review, ContentStatus.approved, ContentStatus.changes_requested)


@dataclass
class ChainResult:
    rules: list[str]
    rechecked: list[int]
    skipped: int


def _window(e: BrandEvent) -> str:
    return f"{e.starts_on.isoformat()} to {e.ends_on.isoformat()}" if e.ends_on else f"from {e.starts_on.isoformat()}"


def desired_rules(e: BrandEvent) -> dict[str, dict]:
    """The rules this event should own right now, by code. Empty when cancelled."""
    if e.status != "active":
        return {}
    ref = f"Event: {e.name} ({_window(e)})"
    out: dict[str, dict] = {}
    brief = e.guidance.strip()
    if e.blackout:
        brief = (brief + " " if brief else "") + ("Promotional and celebratory posts are paused while this runs; "
                                                  "only service updates and messages about the event itself go out.")
    if brief:
        out[f"EVT-{e.id}-BRIEF"] = {
            "category": "messaging", "kind": RuleKind.semantic,
            "severity": Severity.must if e.blackout else Severity.should,
            "title": f"{e.name}: {'blackout' if e.blackout else 'event brief'}"[:200],
            "text": f"During {e.name} ({_window(e)}): {brief}", "pattern": {}, "source_ref": ref}
    if e.avoid_terms:
        out[f"EVT-{e.id}-AVOID"] = {
            "category": "messaging", "kind": RuleKind.deterministic, "severity": Severity.must,
            "title": f"{e.name}: words to avoid"[:200],
            "text": f"While {e.name} runs, these words must not appear.",
            "pattern": {"type": "banned_terms", "terms": list(e.avoid_terms)}, "source_ref": ref}
    if e.hashtags:
        out[f"EVT-{e.id}-TAGS"] = {
            "category": "messaging", "kind": RuleKind.deterministic, "severity": Severity.should,
            "title": f"{e.name}: use the event hashtag"[:200],
            "text": f"Posts made for {e.name} carry its hashtag.",
            "pattern": {"type": "event_hashtags", "terms": [t.lstrip("#") for t in e.hashtags]}, "source_ref": ref}
    return out


async def sync_rules(session: AsyncSession, e: BrandEvent) -> list[str]:
    """Make the event's rules match the event. A changed rule becomes a new version; a dropped one retires."""
    want = desired_rules(e)
    owned = (await session.scalars(select(Rule).where(Rule.workspace_id == e.workspace_id, Rule.event_id == e.id)
                                   .order_by(Rule.code, Rule.version))).all()
    latest: dict[str, Rule] = {}
    for r in owned:
        latest[r.code] = r
    for code, rule in latest.items():
        if code not in want and rule.status is not RuleStatus.retired:
            rule.status = RuleStatus.retired
    for code, spec in want.items():
        cur = latest.get(code)
        same = cur is not None and all(getattr(cur, k) == v for k, v in spec.items())
        if same:
            cur.status = RuleStatus.active
            continue
        if cur is not None:
            cur.status = RuleStatus.retired
        session.add(Rule(workspace_id=e.workspace_id, code=code, version=(cur.version + 1) if cur else 1,
                         status=RuleStatus.active, tier=e.tier, event_id=e.id, **spec))
    await session.flush()
    return sorted(want)


async def run_chain(session: AsyncSession, prism, e: BrandEvent, change: str, actor: str,
                    was_live: bool = False) -> ChainResult:
    """Event saved: rewrite its rules, then re-check every piece it touches. Commits.

    An event's rules reach every piece in flight while it runs, and only the pieces made for it otherwise.
    So a change touches every piece in flight if the event was running before it or is running after it
    (a blackout ending, a start moved into today, a live event cancelled); otherwise only its own pieces."""
    codes = await sync_rules(session, e)
    # Same calendar as the checks (CheckContext.today), so "live" means the same thing everywhere.
    today = date.today()
    q = select(Content).where(Content.workspace_id == e.workspace_id, Content.status.in_(IN_FLIGHT))
    if not (was_live or e.live_on(today)):
        q = q.where(Content.event_id == e.id)
    pieces = (await session.scalars(q.order_by(Content.id.desc()))).all()
    # Tagged pieces first: they are the ones the event is about.
    pieces.sort(key=lambda c: c.event_id != e.id)
    picked, skipped = pieces[:MAX_RECHECKS], max(0, len(pieces) - MAX_RECHECKS)

    review_ids: list[int] = []
    for c in picked:
        latest = await session.scalar(select(func.max(ContentVersion.id)).where(ContentVersion.content_id == c.id))
        if latest is None:
            continue
        review = Review(version_id=latest)
        session.add(review)
        await session.flush()
        session.add(EventImpact(event_id=e.id, content_id=c.id, revision=e.revision, change=change,
                                review_id=review.id))
        review_ids.append(review.id)
    await append(session, workspace_id=e.workspace_id, actor=actor, action=f"event.{change}", object_type="event",
                 object_id=e.id, detail={"revision": e.revision, "rules": codes, "rechecked": [c.id for c in picked],
                                         "skipped": skipped})
    await session.commit()
    for rid in review_ids:
        prism.schedule(rid)
    return ChainResult(rules=codes, rechecked=[c.id for c in picked], skipped=skipped)
