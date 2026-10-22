"""The public-contacts register as the guard and the checks see it."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.checks.base import ContactView
from verytas.models import PublicContact
from verytas.security.audit import append
from verytas.security.guard import GuardResult, screen


async def contacts_for(session: AsyncSession, workspace_id: int) -> list[ContactView]:
    rows = (await session.scalars(select(PublicContact).where(
        PublicContact.workspace_id == workspace_id, PublicContact.active))).all()
    return [ContactView(c.kind, c.value, c.normalized, c.label) for c in rows]


async def screened(session: AsyncSession, *, workspace_id: int, actor_id: int, text: str, where: str) -> GuardResult:
    """Screen user-written text before it is stored; refuse with a 422 that names what to change.

    A refusal is audited by flag code only: the text itself (a phone number, an offer) is not kept."""
    result = screen(text, await contacts_for(session, workspace_id))
    if not result.ok:
        await append(session, workspace_id=workspace_id, actor=f"user:{actor_id}", action="guard.refused",
                     object_type=where, object_id=None, detail={"codes": sorted({f.code for f in result.refused})})
        await session.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={
            "message": result.reason(), "guard": [{"code": f.code, "label": f.label} for f in result.refused]})
    return result
