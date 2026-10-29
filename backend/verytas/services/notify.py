"""Telling open screens that something changed, over the conversations stream each person already holds.

The events carry no content, only what changed and on which piece: a screen that hears one asks the API
again, with its own visibility. They go only to people who may read that piece, so even the id never reaches
someone the API would hide it from. Sending is best effort: the work is already committed, so a failure here
is logged and the screens catch up on their next poll.

Called after the caller's commit. The lookups here open a transaction of their own, and on SQLite every
transaction takes the write lock (BEGIN IMMEDIATE), so each helper commits before it returns: holding it
until the response ends would make a review starting in the background wait, and time out.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.models import Content, Role, User

log = logging.getLogger(__name__)
_hub: Any = None


def use(hub: Any) -> None:
    """The process's message hub (services/messages.py), set at startup. Without one nothing is sent."""
    global _hub
    _hub = hub


async def _publish(user_ids: set[int], event: dict[str, Any]) -> None:
    if _hub is not None and user_ids:
        await _hub.publish(sorted(user_ids), event)


async def _team(session: AsyncSession, content: Content) -> set[int]:
    """The brand team cleared for the piece. Auditors read the record and act on none of it, so nothing is
    pushed to them."""
    team = (await session.scalars(select(User).where(User.workspace_id == content.workspace_id,
                                                     User.role.not_in((Role.creator, Role.auditor))))).all()
    # api/deps.py can_read, written out: the API package imports Prism, which imports this.
    return {u.id for u in team if content.tier.rank <= u.clearance.rank}


async def escalations_changed(session: AsyncSession, content_id: int, raised_by: int) -> None:
    """The inbox and badge of everyone on the brand team cleared for the piece, and the creator who asked."""
    try:
        content = await session.get(Content, content_id)
        if content is None:
            await session.commit()
            return
        to = await _team(session, content) | {raised_by}
        await session.commit()
        await _publish(to, {"type": "escalations", "content_id": content_id})
    except Exception:  # noqa: BLE001, see the module docstring
        log.exception("escalation news for content %s was not sent", content_id)


async def piece_news(session: AsyncSession, content_id: int, actor_id: int) -> None:
    """Something happened on a piece that the other side waits on. The brand team acting tells the creator;
    the creator acting (sending it in, a new version, a comment) tells the brand team cleared for it."""
    try:
        content = await session.get(Content, content_id)
        if content is None:
            await session.commit()
            return
        if actor_id != content.created_by:
            to = {content.created_by}
        else:
            to = await _team(session, content)
        await session.commit()
        await _publish(to - {actor_id}, {"type": "review", "content_id": content_id})
    except Exception:  # noqa: BLE001, see the module docstring
        log.exception("piece news for content %s was not sent", content_id)


async def dispute_decided(session: AsyncSession, content_id: int, creator_id: int, to_team: bool) -> None:
    """Prism's verdict on a dispute: the creator who disputed hears it, and so does the brand team when it was
    passed to a person."""
    try:
        content = await session.get(Content, content_id)
        to = ({creator_id} | (await _team(session, content) if to_team else set())) if content else set()
        await session.commit()
        await _publish(to, {"type": "review", "content_id": content_id})
    except Exception:  # noqa: BLE001, see the module docstring
        log.exception("dispute news for content %s was not sent", content_id)
