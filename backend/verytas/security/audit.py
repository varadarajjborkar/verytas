"""Hash-chained audit log (X.800 notarization + audit trail).

Each entry stores sha256(prev_hash || canonical(entry)). Editing or deleting
any row breaks every hash after it, which `verify_chain` detects. The same idea
underpins Certificate Transparency logs (RFC 6962), minus the Merkle tree.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.models import AuditEntry, utcnow

GENESIS = "0" * 64

# Appends for one workspace must be serialised or two writers would chain off
# the same predecessor. A process-local lock is enough for the single-process
# deployment; a multi-worker Postgres setup would take a row lock instead.
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()


def _ts(dt: datetime) -> str:
    # SQLite hands timestamps back naive; normalise both sides to naive UTC.
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def _payload(e: AuditEntry) -> dict[str, Any]:
    return {
        "workspace_id": e.workspace_id, "actor": e.actor, "action": e.action,
        "object_type": e.object_type, "object_id": e.object_id, "detail": e.detail,
        "created_at": _ts(e.created_at),
    }


def entry_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(prev_hash.encode() + canonical(payload)).hexdigest()


async def append(session: AsyncSession, *, workspace_id: int, actor: str, action: str, object_type: str,
                 object_id: str | int | None = None, detail: dict[str, Any] | None = None) -> AuditEntry:
    """Add an audit entry to the session. The caller owns the commit, so the
    entry lands atomically with the change it describes."""
    async with _locks[workspace_id]:
        prev = await session.scalar(
            select(AuditEntry.hash).where(AuditEntry.workspace_id == workspace_id)
            .order_by(AuditEntry.id.desc()).limit(1)
        )
        entry = AuditEntry(
            workspace_id=workspace_id, actor=actor, action=action, object_type=object_type,
            object_id=None if object_id is None else str(object_id), detail=detail or {},
            created_at=utcnow(), prev_hash=prev or GENESIS, hash="",
        )
        entry.hash = entry_hash(entry.prev_hash, _payload(entry))
        session.add(entry)
        await session.flush()
        return entry


@dataclass
class ChainReport:
    ok: bool
    entries: int
    first_bad_id: int | None = None
    reason: str | None = None


async def verify_chain(session: AsyncSession, workspace_id: int) -> ChainReport:
    rows = (await session.scalars(
        select(AuditEntry).where(AuditEntry.workspace_id == workspace_id).order_by(AuditEntry.id)
    )).all()
    prev = GENESIS
    for e in rows:
        if e.prev_hash != prev:
            return ChainReport(False, len(rows), e.id, "link broken: an entry before this one was removed or altered")
        if entry_hash(prev, _payload(e)) != e.hash:
            return ChainReport(False, len(rows), e.id, "content altered after it was written")
        prev = e.hash
    return ChainReport(True, len(rows))
