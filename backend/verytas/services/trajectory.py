"""A creator's track record, one point per piece, for the brand team's view of that person.

Each point is the piece as the creator sent it: the findings of its first review, not of the version
that was finally fixed, because the line is meant to show how far the writing itself drifted from the
brand. A creator who stays on brand draws a flat line at zero.

Distance from the brand is a plain weighted count, so a manager can do the sum in their head:
each must-fix adds 40, each should-fix 15 and each note 4, capped at 100. Findings the brand team
dismissed (a rejected decision, or an escalation cleared in the creator's favour) don't count: the
creator was right.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from verytas.models import (
    BrandEvent,
    Content,
    ContentStatus,
    ContentVersion,
    DecisionAction,
    Escalation,
    Finding,
    Level,
    Review,
    ReviewStatus,
    Role,
    Tier,
    User,
)

WEIGHT = {Level.blocker: 40, Level.warning: 15, Level.advisory: 4}
# The checks that measure drift itself, as opposed to a slip (a misspelt name, a missing alt text).
DRIFT_RULES = ("TONE-SHIFT", "MSG-OFF-TOPIC")
_OUTCOME = {
    ContentStatus.draft: "Not sent yet",
    ContentStatus.in_review: "Waiting for review",
    ContentStatus.changes_requested: "Sent back for changes",
    ContentStatus.approved: "Approved",
    ContentStatus.published: "Published",
    ContentStatus.withdrawn: "Withdrawn",
}


def _dismissed(f: Finding, staff: set[int]) -> bool:
    """The brand team's latest word on the finding is that it was wrong. A creator may reject their own
    non-blocking findings, but that is their view, not a ruling, and it doesn't clean their record."""
    ruled = [d for d in f.decisions if d.actor_id in staff]
    latest = max(ruled, key=lambda d: (d.created_at, d.id), default=None)
    return latest is not None and latest.action is DecisionAction.rejected


def _summary(issues: list[Finding], status: ContentStatus) -> str:
    outcome = _OUTCOME[status]
    if not issues:
        return f"On brand as sent. {outcome}."
    counts = Counter(f.level for f in issues)
    names = ((Level.blocker, "must-fix", "must-fix"), (Level.warning, "should-fix", "should-fix"),
             (Level.advisory, "note", "notes"))
    parts = [f"{counts[lvl]} {one if counts[lvl] == 1 else many}" for lvl, one, many in names if counts[lvl]]
    ranked = sorted(issues, key=lambda f: (-WEIGHT[f.level], f.id))
    titles = list(dict.fromkeys(f.title for f in ranked))[:2]
    fixed = status in (ContentStatus.approved, ContentStatus.published)
    tail = f"Fixed, then {outcome.lower()}." if fixed else f"{outcome}."
    return f"{', '.join(parts)}: {'; '.join(titles)}. {tail}"


def _tiers(viewer: User, tiers: list[Tier] | None) -> list[Tier]:
    """The viewer's clearance, or a narrower set a caller asks for (Ask Inki leaves confidential out)."""
    return [t for t in Tier if t.rank <= viewer.clearance.rank and (tiers is None or t in tiers)]


async def _points(session: AsyncSession, viewer: User, creator_ids: list[int],
                  tiers: list[Tier] | None = None) -> tuple[dict[int, list[dict]], Counter]:
    """Every reviewed piece of these creators as a point on their line, oldest first, plus how often each
    category came up across them. One set of queries for the whole roster, not one per person."""
    tiers = _tiers(viewer, tiers)
    contents = (await session.scalars(
        select(Content).where(Content.workspace_id == viewer.workspace_id, Content.created_by.in_(creator_ids),
                              Content.tier.in_(tiers)).order_by(Content.created_at, Content.id))).all()
    ids = [c.id for c in contents]
    first: dict[int, Review] = {}
    if ids:
        reviews = (await session.execute(
            select(Review, ContentVersion.content_id).join(ContentVersion, Review.version_id == ContentVersion.id)
            .where(ContentVersion.content_id.in_(ids), Review.status == ReviewStatus.done)
            .options(selectinload(Review.findings).selectinload(Finding.decisions),
                     selectinload(Review.findings).selectinload(Finding.rule)).order_by(Review.id))).all()
        for r, content_id in reviews:
            first.setdefault(content_id, r)
    cleared = set((await session.scalars(
        select(Escalation.finding_id).where(Escalation.workspace_id == viewer.workspace_id,
                                            Escalation.raised_by.in_(creator_ids),
                                            Escalation.status == "cleared"))).all())
    events = {e.id: e.name for e in (await session.scalars(
        select(BrandEvent).where(BrandEvent.workspace_id == viewer.workspace_id, BrandEvent.tier.in_(tiers)))).all()}
    staff = set((await session.scalars(select(User.id).where(User.workspace_id == viewer.workspace_id,
                                                             User.role != Role.creator))).all())

    lines: dict[int, list[dict]] = {i: [] for i in creator_ids}
    categories: Counter = Counter()
    for c in contents:
        review = first.get(c.id)
        if review is None:
            continue  # never reviewed: nothing was measured yet
        issues = [f for f in review.findings if not _dismissed(f, staff) and f.id not in cleared]
        categories.update(f.category for f in issues)
        drift = sorted({f.category for f in issues if f.rule and f.rule.code in DRIFT_RULES})
        lines[c.created_by].append({
            "content_id": c.id, "title": c.title, "channel": c.channel, "status": c.status.value,
            "at": (review.finished_at or c.created_at).isoformat(),
            "distance": min(100, sum(WEIGHT[f.level] for f in issues)),
            "blockers": sum(f.level is Level.blocker for f in issues),
            "warnings": sum(f.level is Level.warning for f in issues),
            "advisories": sum(f.level is Level.advisory for f in issues),
            "drift": drift,
            "issues": [{"category": f.category, "title": f.title, "level": f.level.value}
                       for f in sorted(issues, key=lambda f: (-WEIGHT[f.level], f.id))[:4]],
            "summary": _summary(issues, c.status),
            "event": events.get(c.event_id) if c.event_id else None,
        })
    return lines, categories


def _average(points: list[dict]) -> float | None:
    return round(sum(p["distance"] for p in points) / len(points), 1) if points else None


# The roster's sparkline: enough recent pieces to show a direction, few enough to read at a glance.
RECENT = 10


async def creators(session: AsyncSession, viewer: User, tiers: list[Tier] | None = None) -> list[dict]:
    tiers = _tiers(viewer, tiers)
    people = (await session.scalars(select(User).where(User.workspace_id == viewer.workspace_id,
                                                       User.role == Role.creator).order_by(User.name))).all()
    rows = (await session.execute(
        select(Content.created_by, Content.status, func.count(), func.max(Content.created_at))
        .where(Content.workspace_id == viewer.workspace_id, Content.tier.in_(tiers))
        .group_by(Content.created_by, Content.status))).all()
    above = dict((await session.execute(
        select(Content.created_by, func.count()).where(Content.workspace_id == viewer.workspace_id,
                                                       Content.tier.not_in(tiers))
        .group_by(Content.created_by))).all())
    escalations = dict((await session.execute(
        select(Escalation.raised_by, func.count()).join(Content, Escalation.content_id == Content.id)
        .where(Escalation.workspace_id == viewer.workspace_id, Escalation.status == "open", Content.tier.in_(tiers))
        .group_by(Escalation.raised_by))).all())
    lines, _ = await _points(session, viewer, [p.id for p in people], tiers)
    out = []
    for p in people:
        mine = [r for r in rows if r[0] == p.id]
        by_status = {r[1].value: r[2] for r in mine}
        last = max((r[3] for r in mine), default=None)
        line = lines[p.id]
        out.append({"id": p.id, "name": p.name, "role": p.role.value, "pieces": sum(by_status.values()),
                    "by_status": by_status, "open_escalations": escalations.get(p.id, 0),
                    "above_clearance": above.get(p.id, 0),
                    "last_at": last.isoformat() if isinstance(last, datetime) else None,
                    "reviewed": len(line), "on_brand_as_sent": sum(pt["distance"] == 0 for pt in line),
                    "average_distance": _average(line),
                    "recent": [pt["distance"] for pt in line[-RECENT:]]})
    return out


async def trajectory(session: AsyncSession, viewer: User, creator: User, tiers: list[Tier] | None = None) -> dict:
    tiers = _tiers(viewer, tiers)
    contents = (await session.scalars(
        select(Content.status).where(Content.workspace_id == viewer.workspace_id, Content.created_by == creator.id,
                                     Content.tier.in_(tiers)))).all()
    hidden = (await session.scalar(select(func.count()).select_from(Content).where(
        Content.workspace_id == viewer.workspace_id, Content.created_by == creator.id,
        Content.tier.not_in(tiers)))) or 0
    open_esc = (await session.scalar(
        select(func.count()).select_from(Escalation).join(Content, Escalation.content_id == Content.id)
        .where(Escalation.raised_by == creator.id, Escalation.status == "open", Content.tier.in_(tiers)))) or 0
    lines, categories = await _points(session, viewer, [creator.id], tiers)
    points = lines[creator.id]
    return {
        "person": {"id": creator.id, "name": creator.name, "role": creator.role.value},
        "stats": {
            "pieces": len(contents), "reviewed": len(points), "above_clearance": hidden,
            "on_brand_as_sent": sum(p["distance"] == 0 for p in points),
            "published": sum(s is ContentStatus.published for s in contents),
            "in_review": sum(s is ContentStatus.in_review for s in contents),
            "changes_requested": sum(s is ContentStatus.changes_requested for s in contents),
            "open_escalations": open_esc,
            "average_distance": _average(points),
        },
        "categories": dict(categories.most_common()),
        "points": points,
    }
