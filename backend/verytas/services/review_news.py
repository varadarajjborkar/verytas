"""What is new on a creator's own pieces since they last opened each one: the badge on "My reviews".

News is anything the brand team or Prism did to the piece that the creator didn't do themselves: a status
change (approved, sent back, published), a decision on an issue, an escalation answered, a dispute decided,
a comment. A piece counts once however much happened, until the creator opens it (POST
/contents/{id}/seen). Only the last month counts, so a long history doesn't start out as a wall of unread.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.models import (
    Comment,
    Content,
    ContentSeen,
    ContentVersion,
    Decision,
    Dispute,
    Escalation,
    Finding,
    Review,
    User,
    WorkflowEvent,
    utcnow,
)

WINDOW = timedelta(days=30)


def _aware(at: datetime) -> datetime:
    # SQLite hands back naive datetimes; everything here is UTC.
    return at if at.tzinfo else at.replace(tzinfo=utcnow().tzinfo)


async def news_for(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    """The creator's pieces with news they haven't seen, newest first."""
    pieces = {row.id: row for row in (await session.execute(
        select(Content.id, Content.title, Content.status)
        .where(Content.workspace_id == user.workspace_id, Content.created_by == user.id))).all()}
    if not pieces:
        return []
    ids, since = list(pieces), utcnow() - WINDOW
    latest: dict[int, datetime] = {}

    def keep(rows) -> None:
        for content_id, at in rows:
            if at is not None and (content_id not in latest or _aware(at) > latest[content_id]):
                latest[content_id] = _aware(at)

    keep(await session.execute(
        select(WorkflowEvent.content_id, func.max(WorkflowEvent.created_at))
        .where(WorkflowEvent.content_id.in_(ids), WorkflowEvent.actor_id != user.id, WorkflowEvent.created_at >= since)
        .group_by(WorkflowEvent.content_id)))
    keep(await session.execute(
        select(Comment.content_id, func.max(Comment.created_at))
        .where(Comment.content_id.in_(ids), Comment.actor_id != user.id, Comment.created_at >= since)
        .group_by(Comment.content_id)))
    keep(await session.execute(
        select(ContentVersion.content_id, func.max(Decision.created_at))
        .join(Finding, Finding.id == Decision.finding_id).join(Review, Review.id == Finding.review_id)
        .join(ContentVersion, ContentVersion.id == Review.version_id)
        # A call carried onto a re-check is one the creator has already been told about.
        .where(ContentVersion.content_id.in_(ids), Decision.actor_id != user.id, Decision.carried_from_id.is_(None),
               Decision.created_at >= since)
        .group_by(ContentVersion.content_id)))
    keep(await session.execute(
        select(Escalation.content_id, func.max(Escalation.resolved_at))
        .where(Escalation.content_id.in_(ids), Escalation.resolved_at >= since, Escalation.resolved_by != user.id)
        .group_by(Escalation.content_id)))
    keep(await session.execute(
        select(Dispute.content_id, func.max(Dispute.decided_at))
        .where(Dispute.content_id.in_(ids), Dispute.decided_at >= since)
        .group_by(Dispute.content_id)))

    seen = {cid: _aware(at) for cid, at in (await session.execute(
        select(ContentSeen.content_id, ContentSeen.seen_at).where(ContentSeen.user_id == user.id,
                                                                  ContentSeen.content_id.in_(ids))))}
    news = [{"content_id": cid, "title": pieces[cid].title, "status": pieces[cid].status, "at": at}
            for cid, at in latest.items() if cid not in seen or at > seen[cid]]
    return sorted(news, key=lambda n: n["at"], reverse=True)


async def mark_seen(session: AsyncSession, user: User, content_id: int) -> None:
    """Commits. A screen opening a piece can send this twice at once; the second insert loses the race on the
    unique row and becomes an update instead of an error."""
    now = utcnow()
    updated = await session.execute(update(ContentSeen).where(ContentSeen.user_id == user.id,
                                                              ContentSeen.content_id == content_id)
                                    .values(seen_at=now))
    if updated.rowcount:
        await session.commit()
        return
    try:
        session.add(ContentSeen(user_id=user.id, content_id=content_id, seen_at=now))
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await session.execute(update(ContentSeen).where(ContentSeen.user_id == user.id,
                                                        ContentSeen.content_id == content_id).values(seen_at=now))
        await session.commit()
