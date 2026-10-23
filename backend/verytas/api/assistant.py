"""What Ask Verytas may know when it answers one person's question.

The assistant runs on a hosted model, so everything here leaves Verytas.
It is assembled on the server, where the rules for that live: confidential
tier content is left out, and every string passes the same redactor Prism
uses, so a codename quoted in a finding or a title never reaches the model.

It holds governance data only. Verytas never sees a post after it ships, so
reach and engagement are not here; the note says so for the model to relay.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from verytas.api.accounts import SelfServeBudget
from verytas.api.content import _aware, list_contents
from verytas.api.deps import CurrentUser, Session
from verytas.api.insights import _visible_tiers, guideline_health_for, overview_for, recurring_for
from verytas.models import ConfidentialTerm, Content, ContentVersion, Finding, Review, Role, Tier
from verytas.security.redaction import Redactor

router = APIRouter(prefix="/assistant", tags=["assistant"])

ANALYSTS = {Role.reviewer, Role.approver, Role.auditor, Role.brand_admin}
MAX_LISTED = 60
MAX_DETAILED = 3
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset({"a", "an", "the", "my", "our", "is", "was", "how", "did", "does", "do", "of", "on", "in", "for",
                   "to", "and", "or", "with", "it", "this", "that", "what", "where"})
_RECENT = re.compile(r"\b(latest|recent|last|newest|today|yesterday)\b", re.IGNORECASE)
NOTE = ("Verytas reviews content before publication. It does not see reach, clicks, likes or ad results "
        "after a post goes live; answer progress questions with review status, scores and open issues.")


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


def _redact_all(value: Any, redactor: Redactor) -> Any:
    if isinstance(value, str):
        return redactor.redact(value)
    if isinstance(value, list):
        return [_redact_all(v, redactor) for v in value]
    if isinstance(value, dict):
        return {k: _redact_all(v, redactor) for k, v in value.items()}
    return value


async def _detail(session: Session, content_id: int, redactor: Redactor) -> dict[str, Any]:
    """One piece's story: latest text, how each version's review went, and what is still open.

    Text is redacted before it is cut to length, so a cut can't leave half a codename behind.
    """
    versions = (await session.scalars(select(ContentVersion).where(ContentVersion.content_id == content_id)
                                      .order_by(ContentVersion.version_no))).all()
    reviews = (await session.scalars(
        select(Review).where(Review.version_id.in_([v.id for v in versions])).order_by(Review.id)
        .options(selectinload(Review.findings).selectinload(Finding.rule)))).all()
    last_review = {r.version_id: r for r in reviews}
    history = []
    for v in versions:
        r = last_review.get(v.id)
        s = (r.summary or {}) if r else {}
        history.append({"version": v.version_no, "created_at": _aware(v.created_at).isoformat(),
                        "review": r.status if r else None, "score": s.get("overall"),
                        "blockers": s.get("blockers", 0), "warnings": s.get("warnings", 0)})
    latest = last_review.get(versions[-1].id) if versions else None
    open_issues = [{"level": f.level, "category": f.category, "title": f.title,
                    "rule": f.rule.code if f.rule else None, "quote": redactor.redact(f.quote or "")[:160]}
                   for f in (latest.findings if latest else [])][:15]
    return {"latest_text": redactor.redact(versions[-1].body)[:1500] if versions else "", "versions": history,
            "open_issues": open_issues}


async def _redactor(session: Session, user: CurrentUser) -> Redactor:
    # Every term is redacted, embargo passed or not, the same as Prism does on egress.
    terms = (await session.scalars(select(ConfidentialTerm.term).where(
        ConfidentialTerm.workspace_id == user.workspace_id))).all()
    return Redactor(list(terms))


class Conversation(BaseModel):
    messages: list[Annotated[str, Field(max_length=8_000)]] = Field(default_factory=list, max_length=40)


@router.post("/context", dependencies=[SelfServeBudget])
async def context_for_conversation(body: Conversation, session: Session, user: CurrentUser) -> dict[str, Any]:
    """The context plus the conversation itself, redacted together.

    The questions leave Verytas too, so a codename typed into one is hidden like
    any other. One redactor covers both, so [[TERM_1]] in a question and in the
    data is the same term.
    """
    redactor = await _redactor(session, user)
    messages = [redactor.redact(m) for m in body.messages]
    out = await _context(session, user, body.messages[-1][:2000] if body.messages else "", redactor)
    return out | {"messages": messages}


@router.get("/context")
async def context(session: Session, user: CurrentUser, q: str = Query("", max_length=2000)) -> dict[str, Any]:
    return await _context(session, user, q, await _redactor(session, user))


async def _context(session: Session, user: CurrentUser, q: str, redactor: Redactor) -> dict[str, Any]:

    rows = [r for r in await list_contents(session, user, state=None, mine=False, limit=200)
            if r.tier != Tier.confidential][:MAX_LISTED]
    items = [{"id": r.id, "title": r.title, "channel": r.channel, "status": r.status, "mine": r.created_by == user.id,
              "versions": r.version_count, "updated_at": _aware(r.updated_at).isoformat() if r.updated_at else None,
              "latest_review": r.latest_review.model_dump(mode="json") if r.latest_review else None}
             for r in rows]

    # Retrieval: the pieces the question names (by title words), plus the newest
    # ones when it asks about "latest" or "recent" work, or names nothing at all.
    asked = _words(q)
    # Ties go to the newer piece; rows come newest first.
    scored = sorted((-len(asked & _words(r.title)), i) for i, r in enumerate(rows))
    picked = [i for score, i in scored if score < 0][:MAX_DETAILED]
    if not picked or _RECENT.search(q):
        newest = [i for i in range(len(rows)) if i not in picked]  # rows come newest first
        picked += newest[:max(1, MAX_DETAILED - len(picked))]
    details = []
    for i in picked[:MAX_DETAILED]:
        content = await session.get(Content, rows[i].id)
        if content is not None:
            details.append({"id": content.id, "title": content.title, **await _detail(session, content.id, redactor)})

    out: dict[str, Any] = {"note": NOTE, "you": {"name": user.name, "role": user.role},
                           "content": items, "content_details": details}
    if user.role in ANALYSTS:
        # The same ceiling as the content list: aggregates quote phrases and count
        # findings, so confidential pieces must not feed them either.
        tiers = [t for t in _visible_tiers(user) if t is not Tier.confidential]
        out["overview"] = await overview_for(session, user, tiers)
        out["guideline_health"] = [{k: v for k, v in h.items() if k != "advice"} | {"advice": h["advice"][:2]}
                                   for h in await guideline_health_for(session, user, tiers)]
        out["recurring_problems"] = (await recurring_for(session, user, tiers))[:15]
    else:
        out["analytics"] = "Workspace-wide analytics need a reviewer, approver or auditor role."
    return _redact_all(out, redactor)
