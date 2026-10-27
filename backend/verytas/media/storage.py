"""How much upload storage a person and a workspace may hold, and reclaiming uploads nothing uses.

Uploads live in the database as `MediaBlob` rows. Without limits one account could fill the host's disk
(security audit, run 1), so each upload is checked against two quotas: one per person, so a single
account can't take a whole workspace's share, and one per workspace, which bounds the host. An upload
that no version references after `orphan_upload_ttl_h` hours (an abandoned draft, a brand book read
by the rule importer) is deleted by a sweep that runs hourly and before a quota refusal.

Check and insert run under a lock per workspace, so uploads arriving together can't each pass the check
and overshoot the quota together. SQLite already serialises them (each write transaction begins
IMMEDIATE); on Postgres two transactions can read before either commits, and the lock is what holds.
The lock is in-process: the API runs as one process (deploy/systemd/verytas-api.service), and more
would need a database lock instead.

The sweep and a submission are not serialised: a submission that attaches an upload in the same moment
the sweep deletes it (only possible after a day unused) fails with a 422 that says to upload again.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from verytas.models import Content, ContentVersion, IntakeItem, MediaBlob, Message, MessageAttachment, utcnow

log = logging.getLogger(__name__)
_MB = 1024 * 1024
_LOCKS: dict[int, asyncio.Lock] = {}


def workspace_lock(workspace_id: int) -> asyncio.Lock:
    """Held from the quota check to the commit of the new upload."""
    return _LOCKS.setdefault(workspace_id, asyncio.Lock())


def blob_ids(attachments: dict[str, Any] | None, notes: dict[str, Any] | None = None) -> set[str]:
    """The upload ids a version points at: its attachments, and the voice note in its creator's brief."""
    ids: set[str] = set()
    for key in ("images", "documents", "videos"):
        ids |= {a["blob_id"] for a in (attachments or {}).get(key, []) if isinstance(a, dict) and a.get("blob_id")}
    if (notes or {}).get("brief_audio_blob_id"):
        ids.add(notes["brief_audio_blob_id"])
    return ids


@dataclass(frozen=True)
class Usage:
    user_bytes: int
    workspace_bytes: int


async def usage(session: AsyncSession, workspace_id: int, user_id: int) -> Usage:
    # Sums over the size column only; the file bytes are never loaded.
    total = func.coalesce(func.sum(MediaBlob.size), 0)
    mine = await session.scalar(select(total).where(MediaBlob.workspace_id == workspace_id,
                                                    MediaBlob.created_by == user_id))
    everyone = await session.scalar(select(total).where(MediaBlob.workspace_id == workspace_id))
    return Usage(int(mine or 0), int(everyone or 0))


def over_quota(now: Usage, incoming: int, *, user_mb: int, workspace_mb: int) -> str | None:
    """Why this upload doesn't fit, worded for the person uploading, or None when it does."""
    if now.user_bytes + incoming > user_mb * _MB:
        return (f"your uploads already use {now.user_bytes / _MB:.0f} of your {user_mb} MB; "
                "files you uploaded but never sent for review are cleared after a day")
    if now.workspace_bytes + incoming > workspace_mb * _MB:
        return f"this workspace's uploads are at their {workspace_mb} MB limit; ask a brand admin to raise it"
    return None


async def reclaim_orphans(session: AsyncSession, *, older_than: timedelta,
                          workspace_id: int | None = None) -> int:
    """Deletes uploads older than `older_than` that no content version references. Returns how many."""
    cutoff = utcnow() - older_than
    q = select(MediaBlob.id, MediaBlob.workspace_id).where(MediaBlob.created_at < cutoff)
    if workspace_id is not None:
        q = q.where(MediaBlob.workspace_id == workspace_id)
    candidates = (await session.execute(q)).all()
    if not candidates:
        return 0
    workspaces = {ws for _, ws in candidates}
    used: set[str] = set()
    # Streamed: attachments may carry inline base64 images, so the versions are never all in memory.
    rows = await session.stream(
        select(ContentVersion.attachments, ContentVersion.creator_notes)
        .join(Content, Content.id == ContentVersion.content_id)
        .where(Content.workspace_id.in_(workspaces)).execution_options(yield_per=100))
    async for attachments, notes in rows:
        used |= blob_ids(attachments, notes)
    # Material handed to Intake is kept while its item exists: an asset draft reads its picture from it.
    used |= set((await session.scalars(select(IntakeItem.blob_id).where(
        IntakeItem.workspace_id.in_(workspaces), IntakeItem.blob_id.is_not(None)))).all())
    # Uploads carried by a message stay while the message does; deleting it releases them.
    used |= set((await session.scalars(select(MessageAttachment.blob_id).join(
        Message, Message.id == MessageAttachment.message_id).where(Message.deleted_at.is_(None)))).all())
    stale = [bid for bid, _ in candidates if bid not in used]
    for i in range(0, len(stale), 500):
        await session.execute(delete(MediaBlob).where(MediaBlob.id.in_(stale[i:i + 500])))
    await session.commit()
    return len(stale)


async def sweep_forever(sessionmaker: async_sessionmaker[AsyncSession], ttl_h: float,
                        every_s: float = 3600) -> None:
    """The hourly sweep the API runs in the background. A failed pass is logged and retried next hour.
    The first pass waits a minute, so it never competes with startup."""
    while True:
        await asyncio.sleep(min(60.0, every_s))
        try:
            async with sessionmaker() as session:
                n = await reclaim_orphans(session, older_than=timedelta(hours=ttl_h))
            if n:
                log.info("reclaimed %d unused upload(s)", n)
        except Exception:  # noqa: BLE001, a storage sweep must never take the API down
            log.exception("upload sweep failed")
        await asyncio.sleep(max(0.0, every_s - 60.0))


async def release(session: AsyncSession, workspace_id: int, ids: set[str]) -> int:
    """Deletes these uploads now if nothing else holds them: no content version, Intake item or live
    message. For a message deleted for everyone, so its files don't wait a day for the sweep."""
    if not ids:
        return 0
    held: set[str] = set()
    # Only versions whose stored JSON mentions one of these ids can hold them; the rest aren't read.
    mentions = or_(*(or_(cast(ContentVersion.attachments, String).contains(i),
                         cast(ContentVersion.creator_notes, String).contains(i)) for i in ids))
    rows = await session.stream(
        select(ContentVersion.attachments, ContentVersion.creator_notes)
        .join(Content, Content.id == ContentVersion.content_id)
        .where(Content.workspace_id == workspace_id, mentions).execution_options(yield_per=100))
    async for attachments, notes in rows:
        held |= blob_ids(attachments, notes)
    held |= set((await session.scalars(select(IntakeItem.blob_id).where(IntakeItem.blob_id.in_(ids)))).all())
    held |= set((await session.scalars(select(MessageAttachment.blob_id).join(
        Message, Message.id == MessageAttachment.message_id)
        .where(MessageAttachment.blob_id.in_(ids), Message.deleted_at.is_(None)))).all())
    gone = [i for i in ids if i not in held]
    if gone:
        await session.execute(delete(MediaBlob).where(MediaBlob.id.in_(gone), MediaBlob.workspace_id == workspace_id))
    return len(gone)
