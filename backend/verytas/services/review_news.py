"""What happened on pieces while the person was away: the news card on each dashboard, the notice on sign-in
and the badge on "My reviews" / "Review queue".

Both sides wait on each other, so news runs both ways:

- a creator hears what the brand team did to their pieces: approved (ready to publish), sent back, published,
  an issue confirmed or cleared, an escalation answered, a dispute decided, a comment;
- the brand team hears what creators did that waits on them: a piece sent for approval, a new version after
  it was sent back, an issue escalated to a person, a dispute Prism passed to a person, a comment.

Nobody's own actions are news to them. An item is unread until the person opens that piece (POST
/contents/{id}/seen); the badge counts pieces, not items. Only the last two weeks count, so a long history
doesn't start out as a wall of unread, and every piece is checked against what the person may open.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.models import (
    Comment,
    Content,
    ContentSeen,
    ContentStatus,
    ContentVersion,
    Decision,
    DecisionAction,
    Dispute,
    Escalation,
    Finding,
    Review,
    Role,
    Tier,
    User,
    WorkflowEvent,
    utcnow,
)

WINDOW = timedelta(days=14)
# Items read per source: the feed shows the newest few, and the badge needs only which pieces have any.
PER_SOURCE = 200
EXCERPT = 140


def _aware(at: datetime) -> datetime:
    # SQLite hands back naive datetimes; everything here is UTC.
    return at if at.tzinfo else at.replace(tzinfo=utcnow().tzinfo)


def _short(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1].rstrip() + "..."


def _scope(user: User, model) -> list:
    """The conditions that keep a source to pieces whose news this person gets: a creator's own; for the
    brand team, the workspace's pieces within their clearance (api/content.py visible). Joined in SQL, so a
    big workspace never turns into a long IN list."""
    allowed = [t for t in Tier if t.rank <= user.clearance.rank]
    where = [Content.id == model.content_id, Content.workspace_id == user.workspace_id, Content.tier.in_(allowed)]
    if user.role is Role.creator:
        where.append(Content.created_by == user.id)
    return where


async def feed_for(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    """Everything that is news to this person in the window, newest first, each marked read or unread.

    Each source asks only for the other side's actions in SQL, so a busy workspace's own traffic can't push
    them out of the per-source limit. Brand-team items that someone has already acted on (an escalation
    answered, a piece decided) are left out: news for the team is what still waits on it."""
    if user.role is Role.auditor:
        return []  # reads the record; nothing waits on them
    creator = user.role is Role.creator
    since = utcnow() - WINDOW
    people: dict[int, tuple[str, Role]] = {uid: (name, role) for uid, name, role in (await session.execute(
        select(User.id, User.name, User.role).where(User.workspace_id == user.workspace_id))).all()}
    creators = [uid for uid, (_, role) in people.items() if role is Role.creator]
    name = lambda uid, default: people.get(uid, (default, None))[0]  # noqa: E731
    pieces: dict[int, Any] = {}
    items: list[dict[str, Any]] = []

    def add(piece, at: datetime | None, kind: str, text: str, actor: int | None = None,
            note: str | None = None) -> None:
        if at is None:
            return
        pieces[piece.id] = piece
        items.append({"content_id": piece.id, "title": piece.title, "status": piece.status, "kind": kind,
                      "text": text, "actor": name(actor, None) if actor else None, "actor_id": actor,
                      "note": _short(note) or None, "at": _aware(at)})

    # Labelled: a source row also carries its own id columns, and the piece's must not be mistaken for them.
    piece_cols = (Content.id.label("piece_id"), Content.title.label("piece_title"),
                  Content.status.label("piece_status"))

    async def rows(model, *where, order):
        return (await session.execute(
            select(model, *piece_cols).join(Content, Content.id == model.content_id)
            .where(*_scope(user, model), *where).order_by(order.desc()).limit(PER_SOURCE))).all()

    def piece_of(row):
        return SimpleNamespace(id=row.piece_id, title=row.piece_title, status=row.piece_status)

    if creator:
        for row in await rows(WorkflowEvent, WorkflowEvent.actor_id != user.id, WorkflowEvent.created_at >= since,
                              order=WorkflowEvent.id):
            e, who = row[0], name(row[0].actor_id, "Someone")
            text = {ContentStatus.approved: f"Approved by {who}. Ready to publish.",
                    ContentStatus.changes_requested: f"Sent back by {who} with changes to make.",
                    ContentStatus.published: f"Published by {who}.",
                    ContentStatus.withdrawn: f"Withdrawn by {who}.",
                    ContentStatus.in_review: f"Moved back into review by {who}."}.get(e.to_status)
            kind = {ContentStatus.approved: "approved", ContentStatus.changes_requested: "sent_back",
                    ContentStatus.published: "published"}.get(e.to_status, "status")
            if text:
                add(piece_of(row), e.created_at, kind, text, e.actor_id, e.note)
        decided = (await session.execute(
            select(Decision, *piece_cols)
            .join(Finding, Finding.id == Decision.finding_id).join(Review, Review.id == Finding.review_id)
            .join(ContentVersion, ContentVersion.id == Review.version_id)
            .join(Content, Content.id == ContentVersion.content_id)
            # A call carried onto a re-check is one the creator has already been told about.
            .where(Content.workspace_id == user.workspace_id, Content.created_by == user.id,
                   Decision.actor_id != user.id, Decision.carried_from_id.is_(None), Decision.created_at >= since)
            .order_by(Decision.id.desc()).limit(PER_SOURCE))).all()
        for row in decided:
            d, who = row[0], name(row[0].actor_id, "The brand team")
            if d.action is DecisionAction.rejected:
                add(piece_of(row), d.created_at, "cleared", f"{who} cleared an issue.", d.actor_id, d.reason_text)
            elif d.action in (DecisionAction.accepted, DecisionAction.edited):
                add(piece_of(row), d.created_at, "confirmed", f"{who} confirmed an issue to fix.", d.actor_id,
                    d.reason_text)
        for row in await rows(Escalation, Escalation.resolved_at >= since, Escalation.resolved_by != user.id,
                              Escalation.status.in_(("cleared", "upheld")), order=Escalation.resolved_at):
            e, who = row[0], name(row[0].resolved_by, "The brand team")
            text = (f"{who} agreed with your request and cleared the issue." if e.status == "cleared"
                    else f"{who} looked at your request; the issue stands.")
            add(piece_of(row), e.resolved_at, "escalation_cleared" if e.status == "cleared" else "escalation_upheld",
                text, e.resolved_by, e.resolution)
        for row in await rows(Dispute, Dispute.user_id == user.id, Dispute.decided_at >= since,
                              order=Dispute.decided_at):
            d = row[0]
            text = {"overturned": "Your dispute was accepted: the issue is cleared.",
                    "upheld": "Your dispute was read: the issue stands.",
                    "escalated": "Your dispute was passed to the brand team."}.get(d.status)
            if text:
                kind = "dispute_passed" if d.status == "escalated" else f"dispute_{d.status}"
                add(piece_of(row), d.decided_at, kind, text, None, (d.verdict or {}).get("reason"))
        for row in await rows(Comment, Comment.actor_id != user.id, Comment.created_at >= since, order=Comment.id):
            c = row[0]
            add(piece_of(row), c.created_at, "comment", f"{name(c.actor_id, 'Someone')} commented.", c.actor_id,
                c.body)
    else:
        waiting = (ContentStatus.in_review, ContentStatus.changes_requested)
        # Sent in by a creator, and still waiting for a decision.
        for row in await rows(WorkflowEvent, WorkflowEvent.actor_id.in_(creators),
                              WorkflowEvent.to_status == ContentStatus.in_review, WorkflowEvent.created_at >= since,
                              Content.status == ContentStatus.in_review, order=WorkflowEvent.id):
            e = row[0]
            add(piece_of(row), e.created_at, "submitted", f"{name(e.actor_id, 'A creator')} sent it for approval.",
                e.actor_id, e.note)
        # Escalations nobody has answered yet.
        for row in await rows(Escalation, Escalation.status == "open", Escalation.raised_by != user.id,
                              Escalation.created_at >= since, order=Escalation.id):
            e = row[0]
            add(piece_of(row), e.created_at, "escalated",
                f"{name(e.raised_by, 'A creator')} asked for a person to look at an issue.", e.raised_by, e.message)
        # Disputes Prism passed to a person, while the piece is still undecided.
        for row in await rows(Dispute, Dispute.status == "escalated", Dispute.decided_at >= since,
                              Content.status.in_(waiting), order=Dispute.decided_at):
            d = row[0]
            add(piece_of(row), d.decided_at, "dispute_escalated",
                f"A dispute from {name(d.user_id, 'a creator')} needs a person to decide.", d.user_id, d.claim)
        # A new version of a piece that is waiting on the team.
        for row in await rows(ContentVersion, ContentVersion.version_no > 1, ContentVersion.created_by.in_(creators),
                              ContentVersion.created_at >= since, Content.status.in_(waiting),
                              order=ContentVersion.id):
            v = row[0]
            add(piece_of(row), v.created_at, "new_version",
                f"{name(v.created_by, 'The creator')} saved version {v.version_no}.", v.created_by)
        for row in await rows(Comment, Comment.actor_id.in_(creators), Comment.created_at >= since, order=Comment.id):
            c = row[0]
            add(piece_of(row), c.created_at, "comment", f"{name(c.actor_id, 'A creator')} commented.", c.actor_id,
                c.body)

    # One act, one item: answering an escalation also records the decision on the issue, and a piece sent in
    # with a new version is "sent for approval", not that and "saved version N" too.
    answers = [(i["content_id"], i["actor_id"], i["at"]) for i in items if i["kind"].startswith("escalation_")]
    sends = [(i["content_id"], i["actor_id"], i["at"]) for i in items if i["kind"] == "submitted"]

    def echo(i: dict[str, Any], of: list) -> bool:
        return any(c == i["content_id"] and a == i["actor_id"] and abs((t - i["at"]).total_seconds()) < 3
                   for c, a, t in of)

    items = [i for i in items if not (i["kind"] in ("cleared", "confirmed") and echo(i, answers))
             and not (i["kind"] == "new_version" and echo(i, sends))]

    seen = {cid: _aware(at) for cid, at in (await session.execute(
        select(ContentSeen.content_id, ContentSeen.seen_at).where(ContentSeen.user_id == user.id,
                                                                  ContentSeen.content_id.in_(list(pieces)))))}
    for item in items:
        item["unread"] = item["content_id"] not in seen or item["at"] > seen[item["content_id"]]
        del item["actor_id"]
    return sorted(items, key=lambda i: i["at"], reverse=True)


async def news_for(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    """The pieces with unread news, one row each (its newest item), newest first: what the badge counts."""
    out: dict[int, dict[str, Any]] = {}
    for item in await feed_for(session, user):
        if item["unread"] and item["content_id"] not in out:
            out[item["content_id"]] = item
    return list(out.values())


async def mark_seen(session: AsyncSession, user: User, content_id: int) -> None:
    """Commits. A screen opening a piece can send this twice at once; the second insert loses the race on the
    unique row and becomes an update instead of an error."""
    now = utcnow()
    where = (ContentSeen.user_id == user.id, ContentSeen.content_id == content_id)
    if (await session.execute(update(ContentSeen).where(*where).values(seen_at=now))).rowcount:
        await session.commit()
        return
    try:
        session.add(ContentSeen(user_id=user.id, content_id=content_id, seen_at=now))
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await session.execute(update(ContentSeen).where(*where).values(seen_at=now))
        await session.commit()
