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
from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from verytas.api.content import _aware, list_contents
from verytas.api.deps import CurrentUser, Session
from verytas.api.insights import guideline_health, overview, recurring
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


async def _detail(session: Session, content_id: int) -> dict[str, Any]:
    """One piece's story: latest text, how each version's review went, and what is still open."""
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
                    "rule": f.rule.code if f.rule else None, "quote": (f.quote or "")[:160]}
                   for f in (latest.findings if latest else [])][:15]
    return {"latest_text": versions[-1].body[:1500] if versions else "", "versions": history,
            "open_issues": open_issues}


@router.get("/context")
async def context(session: Session, user: CurrentUser, q: str = Query("", max_length=2000)) -> dict[str, Any]:
    today = date.today()
    terms = (await session.scalars(select(ConfidentialTerm.term).where(
        ConfidentialTerm.workspace_id == user.workspace_id,
        or_(ConfidentialTerm.embargo_until.is_(None), ConfidentialTerm.embargo_until > today)))).all()
    redactor = Redactor(list(terms))

    rows = [r for r in await list_contents(session, user, state=None, mine=False, limit=200)
            if r.tier != Tier.confidential][:MAX_LISTED]
    items = [{"id": r.id, "title": r.title, "channel": r.channel, "status": r.status, "mine": r.created_by == user.id,
              "versions": r.version_count, "updated_at": _aware(r.updated_at).isoformat() if r.updated_at else None,
              "latest_review": r.latest_review.model_dump(mode="json") if r.latest_review else None}
             for r in rows]

    # Retrieval: the pieces the question names (by title words), plus the newest
    # ones when it asks about "latest" or "recent" work, or names nothing at all.
    asked = _words(q)
    scored = sorted(((len(asked & _words(r.title)), i) for i, r in enumerate(rows)), reverse=True)
    picked = [i for score, i in scored if score > 0][:MAX_DETAILED]
    if not picked or _RECENT.search(q):
        newest = [i for i in range(len(rows)) if i not in picked]  # rows come newest first
        picked += newest[:max(1, MAX_DETAILED - len(picked))]
    details = []
    for i in picked[:MAX_DETAILED]:
        content = await session.get(Content, rows[i].id)
        if content is not None:
            details.append({"id": content.id, "title": content.title, **await _detail(session, content.id)})

    out: dict[str, Any] = {"note": NOTE, "you": {"name": user.name, "role": user.role},
                           "content": items, "content_details": details}
    if user.role in ANALYSTS:
        out["overview"] = await overview(session, user)
        out["guideline_health"] = [{k: v for k, v in h.items() if k != "advice"} | {"advice": h["advice"][:2]}
                                   for h in await guideline_health(session, user)]
        out["recurring_problems"] = (await recurring(session, user))[:15]
    else:
        out["analytics"] = "Workspace-wide analytics need a reviewer, approver or auditor role."
    return _redact_all(out, redactor)
