"""One search over everything the caller may open: pieces, findings, escalations, creators and the brand
library.

Every group applies the same rules the screens behind it do, in the query itself rather than after it, so
a hit is never fetched only to be dropped: the caller's workspace, tier clearance (`can_read`), creators
seeing their own pieces and requests only (`visible` in content.py), and confidential terms for brand
admins only. Library material is left out for creators altogether, because the console has no screen for
it on their side and a result must lead somewhere.

Matching is deliberately plain: case-insensitive substring, ranked prefix of the title first, then the
start of a later word, then anywhere, and within a rank the newest first (ids grow with time).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, case, func, or_, select

from verytas.api.content import _latest_review, visible
from verytas.api.deps import CurrentUser, Session
from verytas.api.insights import guideline_health_for
from verytas.models import (
    BrandAsset,
    BrandEvent,
    ConfidentialTerm,
    Content,
    ContentStatus,
    ContentVersion,
    Escalation,
    Fact,
    Finding,
    Review,
    Role,
    Rule,
    Tier,
    User,
)

router = APIRouter(tags=["search"])

QUERY_MAX = 100
_ESC = "\\"
# A health score at or above this is the point where guideline health itself says to clarify the wording.
UNCLEAR_AMBIGUITY = 0.5

_STATUS = {
    ContentStatus.draft: "Draft", ContentStatus.in_review: "In review",
    ContentStatus.changes_requested: "Changes requested", ContentStatus.approved: "Approved",
    ContentStatus.published: "Published", ContentStatus.withdrawn: "Withdrawn",
}


class Hit(BaseModel):
    type: str
    id: int
    title: str
    subtitle: str = ""
    href: str
    # Set only on the suggestions shown for an empty query: why this is offered.
    section: str | None = None


class SearchOut(BaseModel):
    query: str
    results: list[Hit]


def _like(q: str, *, before: str = "%", after: str = "%") -> str:
    """The query as a LIKE pattern. Its own % and _ are escaped, so typing them searches for them."""
    body = q.replace(_ESC, _ESC * 2).replace("%", _ESC + "%").replace("_", _ESC + "_")
    return f"{before}{body}{after}"


def _anywhere(q: str, *cols) -> ColumnElement[bool]:
    return or_(*(c.ilike(_like(q), escape=_ESC) for c in cols))


def _rank(q: str, col) -> ColumnElement[int]:
    """0 when the title starts with the query, 1 when a later word does, 2 for any other match."""
    return case((col.ilike(_like(q, before=""), escape=_ESC), 0),
                (col.ilike(_like(q, before="% "), escape=_ESC), 1), else_=2)


def _tiers(user: User) -> list[Tier]:
    return [t for t in Tier if t.rank <= user.clearance.rank]


def _piece_href(user: User, content_id: int) -> str:
    # The brand team's queue shows only what is waiting by default; "all" makes any piece openable.
    return f"/review?id={content_id}" if user.role is Role.creator else f"/review?queue=all&id={content_id}"


def _own(user: User, column):
    """Creators are held to their own rows; everyone else is not narrowed by author."""
    return column == user.id if user.role is Role.creator else column.is_not(None)


async def _outcome(session, content: Content) -> str:
    review = await _latest_review(session, content.id)
    summary = (review.summary or {}) if review is not None else {}
    parts = [f"{n} {word}" for n, word in ((summary.get("blockers", 0), "must-fix"),
                                           (summary.get("warnings", 0), "should-fix")) if n]
    return " · ".join([_STATUS[content.status], *parts])


async def _pieces(session, user: User, q: str, limit: int) -> list[Hit]:
    stmt = select(Content).where(Content.workspace_id == user.workspace_id, Content.tier.in_(_tiers(user)),
                                 _own(user, Content.created_by))
    if q:
        in_body = Content.id.in_(select(ContentVersion.content_id).where(
            ContentVersion.body.ilike(_like(q), escape=_ESC)))
        stmt = stmt.where(or_(_anywhere(q, Content.title, Content.channel), in_body)).order_by(
            _rank(q, Content.title), Content.id.desc())
    else:
        stmt = stmt.order_by(Content.id.desc())
    rows = [c for c in (await session.scalars(stmt.limit(limit))).all() if visible(user, c)]
    return [Hit(type="content", id=c.id, title=c.title,
                subtitle=f"{c.channel} · {await _outcome(session, c)}", href=_piece_href(user, c.id)) for c in rows]


async def _findings(session, user: User, q: str, limit: int) -> list[Hit]:
    stmt = (select(Finding, Content)
            .join(Review, Finding.review_id == Review.id)
            .join(ContentVersion, Review.version_id == ContentVersion.id)
            .join(Content, ContentVersion.content_id == Content.id)
            .where(Content.workspace_id == user.workspace_id, Content.tier.in_(_tiers(user)),
                   _own(user, Content.created_by), _anywhere(q, Finding.title, Finding.quote, Finding.explanation))
            .order_by(_rank(q, Finding.title), Finding.id.desc()))
    seen: set[tuple[int, str]] = set()
    out: list[Hit] = []
    # The same finding recurs on every version of a piece; one hit per piece and title is enough.
    for finding, content in (await session.execute(stmt.limit(limit * 4))).all():
        if (content.id, finding.title) in seen:
            continue
        seen.add((content.id, finding.title))
        out.append(Hit(type="finding", id=finding.id, title=finding.title,
                       subtitle=f"{finding.level.value} · in {content.title}", href=_piece_href(user, content.id)))
        if len(out) == limit:
            break
    return out


def _escalation_scope(user: User) -> list[ColumnElement[bool]]:
    scope = [Escalation.workspace_id == user.workspace_id, Content.tier.in_(_tiers(user))]
    if user.role is Role.creator:
        # The same rule as the nav badge: their own request on their own piece.
        scope += [Escalation.raised_by == user.id, Content.created_by == user.id]
    return scope


def _escalation_hit(user: User, esc: Escalation, finding: Finding, content: Content) -> Hit:
    if user.role is Role.creator:
        href = _piece_href(user, content.id)  # the brand team's inbox is not their screen
    else:
        href = f"/escalations?id={esc.id}" if esc.status == "open" else f"/escalations?tab=resolved&id={esc.id}"
    return Hit(type="escalation", id=esc.id, title=finding.title, subtitle=f"Escalation {esc.status} · {content.title}",
               href=href)


async def _escalations(session, user: User, q: str, limit: int) -> list[Hit]:
    stmt = (select(Escalation, Finding, Content)
            .join(Content, Escalation.content_id == Content.id)
            .join(Finding, Escalation.finding_id == Finding.id)
            .where(*_escalation_scope(user), _anywhere(q, Escalation.message, Finding.title, Content.title))
            .order_by(_rank(q, Finding.title), Escalation.id.desc()).limit(limit))
    return [_escalation_hit(user, *row) for row in (await session.execute(stmt)).all()]


async def _creators(session, user: User, q: str, limit: int) -> list[Hit]:
    if user.role is Role.creator:
        return []
    stmt = (select(User).where(User.workspace_id == user.workspace_id, User.role == Role.creator,
                               _anywhere(q, User.name)).order_by(_rank(q, User.name), User.id.desc()).limit(limit))
    return [Hit(type="creator", id=p.id, title=p.name, subtitle="Creator", href=f"/creators?id={p.id}")
            for p in (await session.scalars(stmt)).all()]


async def _rules(session, user: User, q: str, limit: int) -> list[Hit]:
    if user.role is Role.creator:
        return []
    # Only the version in force: older wordings are history, and an above-clearance latest hides the code.
    newest = (select(Rule.code, func.max(Rule.version).label("v")).where(Rule.workspace_id == user.workspace_id)
              .group_by(Rule.code).subquery())
    stmt = (select(Rule).join(newest, and_(Rule.code == newest.c.code, Rule.version == newest.c.v))
            .where(Rule.workspace_id == user.workspace_id, Rule.tier.in_(_tiers(user)), Rule.event_id.is_(None),
                   _anywhere(q, Rule.code, Rule.title, Rule.text))
            .order_by(_rank(q, Rule.title), Rule.id.desc()).limit(limit))
    return [Hit(type="rule", id=r.id, title=f"{r.code} · {r.title}", subtitle=f"{r.category} · {r.severity.value} · "
                f"{r.status.value}", href=f"/library?q={r.code}&state={r.status.value}")
            for r in (await session.scalars(stmt)).all()]


async def _facts(session, user: User, q: str, limit: int) -> list[Hit]:
    if user.role is Role.creator:
        return []
    stmt = (select(Fact).where(Fact.workspace_id == user.workspace_id, Fact.tier.in_(_tiers(user)),
                               _anywhere(q, Fact.statement, Fact.subject, Fact.source_ref))
            .order_by(_rank(q, Fact.statement), Fact.id.desc()).limit(limit))
    return [Hit(type="fact", id=f.id, title=f.statement, subtitle=f"{f.source_ref} · from {f.valid_from.isoformat()}",
                href="/library?tab=facts") for f in (await session.scalars(stmt)).all()]


async def _terms(session, user: User, q: str, limit: int) -> list[Hit]:
    # The guarded words are themselves confidential: brand admins only, as on GET /confidential-terms.
    if user.role is not Role.brand_admin:
        return []
    stmt = (select(ConfidentialTerm).where(ConfidentialTerm.workspace_id == user.workspace_id,
                                           _anywhere(q, ConfidentialTerm.term, ConfidentialTerm.note))
            .order_by(_rank(q, ConfidentialTerm.term), ConfidentialTerm.id.desc()).limit(limit))
    return [Hit(type="term", id=t.id, title=t.term,
                subtitle="Confidential term" + (f" · embargo until {t.embargo_until.isoformat()}" if t.embargo_until
                                                else ""), href="/library?tab=terms")
            for t in (await session.scalars(stmt)).all()]


async def _assets(session, user: User, q: str, limit: int) -> list[Hit]:
    if user.role is Role.creator:
        return []
    stmt = (select(BrandAsset).where(BrandAsset.workspace_id == user.workspace_id, BrandAsset.active,
                                     BrandAsset.tier.in_(_tiers(user)),
                                     _anywhere(q, BrandAsset.name, BrandAsset.wordmark, BrandAsset.notes))
            .order_by(_rank(q, BrandAsset.name), BrandAsset.id.desc()).limit(limit))
    return [Hit(type="asset", id=a.id, title=a.name, subtitle=f"{a.kind} · {a.part}", href="/library?tab=assets")
            for a in (await session.scalars(stmt)).all()]


async def _events(session, user: User, q: str, limit: int) -> list[Hit]:
    if user.role is Role.creator:
        return []
    stmt = (select(BrandEvent).where(BrandEvent.workspace_id == user.workspace_id, BrandEvent.tier.in_(_tiers(user)),
                                     _anywhere(q, BrandEvent.name, BrandEvent.summary, BrandEvent.guidance))
            .order_by(_rank(q, BrandEvent.name), BrandEvent.starts_on.desc()).limit(limit))
    return [Hit(type="event", id=e.id, title=e.name, subtitle=f"{e.kind} · from {e.starts_on.isoformat()}"
                + (" · cancelled" if e.status == "cancelled" else ""), href="/library?tab=events")
            for e in (await session.scalars(stmt)).all()]


async def _suggestions(session, user: User, limit: int) -> list[Hit]:
    """What to offer before anything is typed: the pieces and requests that need this person next."""
    def tag(hits: list[Hit], section: str) -> list[Hit]:
        for h in hits:
            h.section = section
        return hits

    async def pieces(*statuses: ContentStatus, oldest_first: bool = False) -> list[Hit]:
        stmt = select(Content).where(Content.workspace_id == user.workspace_id, Content.tier.in_(_tiers(user)),
                                     _own(user, Content.created_by), Content.status.in_(statuses))
        rows = (await session.scalars(stmt.order_by(Content.id if oldest_first else Content.id.desc())
                                      .limit(limit))).all()
        return [Hit(type="content", id=c.id, title=c.title, subtitle=f"{c.channel} · {await _outcome(session, c)}",
                    href=_piece_href(user, c.id)) for c in rows if visible(user, c)]

    def distinct(hits: list[Hit]) -> list[Hit]:
        # A piece that needs attention is not offered a second time under "recent".
        seen: set[tuple[str, int]] = set()
        return [h for h in hits if not ((h.type, h.id) in seen or seen.add((h.type, h.id)))]

    if user.role is Role.creator:
        return distinct([*tag(await pieces(ContentStatus.changes_requested, ContentStatus.draft), "needs_changes"),
                         *tag(await pieces(ContentStatus.in_review), "with_brand_team"),
                         *tag(await _pieces(session, user, "", limit), "recent")])
    health = await guideline_health_for(session, user, _tiers(user))
    unclear = [Hit(type="rule", id=h["rule_id"], title=f"{h['code']} · {h['title']}",
                   subtitle=f"Reviewers override {round(h['override_rate'] * 100)}% of its findings",
                   href="/guidelines")
               for h in health if h["ambiguity"] is not None and h["ambiguity"] >= UNCLEAR_AMBIGUITY][:limit]
    stmt = (select(Escalation, Finding, Content).join(Content, Escalation.content_id == Content.id)
            .join(Finding, Escalation.finding_id == Finding.id)
            .where(*_escalation_scope(user), Escalation.status == "open").order_by(Escalation.id).limit(limit))
    waiting = [_escalation_hit(user, *row) for row in (await session.execute(stmt)).all()]
    return distinct([*tag(await pieces(ContentStatus.in_review, oldest_first=True), "review_queue"),
                     *tag(waiting, "open_escalations"), *tag(unclear, "unclear_rules"),
                     *tag(await _pieces(session, user, "", limit), "recent")])


@router.get("/search", response_model=SearchOut)
async def search(session: Session, user: CurrentUser, q: Annotated[str, Query(max_length=QUERY_MAX)] = "",
                 limit: Annotated[int, Query(ge=1, le=10, description="Hits per group")] = 5) -> SearchOut:
    q = " ".join(q.split())
    if not q:
        return SearchOut(query="", results=await _suggestions(session, user, limit))
    results: list[Hit] = []
    for group in (_pieces, _findings, _escalations, _creators, _rules, _facts, _terms, _assets, _events):
        results += await group(session, user, q, limit)
    return SearchOut(query=q, results=results)
