"""Telling open screens that something changed, over the conversations stream each person already holds.

The events carry no content, only what changed and on which piece: a screen that hears one asks the API
again, with its own visibility. They go only to people who may read that piece, so even the id never reaches
someone the API would hide it from. Sending is best effort: the work is already committed, so a failure here
is logged and the screens catch up on their next poll.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.api.deps import can_read
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


async def escalations_changed(session: AsyncSession, content_id: int, raised_by: int) -> None:
    """The inbox and badge of everyone on the brand team cleared for the piece, and the creator who asked."""
    try:
        content = await session.get(Content, content_id)
        if content is None:
            return
        team = (await session.scalars(select(User).where(User.workspace_id == content.workspace_id,
                                                         User.role != Role.creator))).all()
        await _publish({u.id for u in team if can_read(u, content.tier)} | {raised_by},
                       {"type": "escalations", "content_id": content_id})
    except Exception:  # noqa: BLE001, see the module docstring
        log.exception("escalation news for content %s was not sent", content_id)


async def review_changed(creator_id: int, actor_id: int, content_id: int) -> None:
    """News on a creator's piece from someone else: their "My reviews" badge and open review look again."""
    if creator_id == actor_id:
        return
    try:
        await _publish({creator_id}, {"type": "review", "content_id": content_id})
    except Exception:  # noqa: BLE001, see the module docstring
        log.exception("review news for content %s was not sent", content_id)
