"""The dossier behind "Summarize": one piece, or one escalation, for a manager who has to decide on it.

Like Ask Verytas, this leaves Verytas for a hosted model, so the same rules apply and are enforced here
rather than in the web app: the caller must be on the brand team's deciding side, anything above the
caller's clearance is a 404 (as for every other route), confidential-tier material never leaves at all,
and every string passes the workspace's redactor. Text is redacted before it is cut to length so a cut
can't leave half a codename behind.

The dossier is one item deep on purpose. Workspace analytics already belong to Ask Verytas; here the
model should be able to answer only from what the manager is looking at.
"""

from __future__ import annotations

import difflib
import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from verytas.api.assistant import _redact_all, _redactor
from verytas.api.content import _aware, _content
from verytas.api.deps import Session, can_read, require
from verytas.models import (
    BrandEvent,
    Comment,
    Content,
    ContentVersion,
    Dispute,
    Escalation,
    Finding,
    Review,
    Role,
    Tier,
    User,
    WorkflowEvent,
)
from verytas.security.redaction import Redactor

router = APIRouter(prefix="/assist", tags=["assist"])

# Reviewers and approvers decide on pieces; brand admins can do anything a listed role can (see `require`).
# Creators have their own checklist and Ask Verytas, and auditors read the record rather than decide on it.
Manager = Annotated[User, Depends(require(Role.reviewer, Role.approver))]

MAX_BODY = 6_000
MAX_FINDINGS = 40
MAX_OLD_FINDINGS = 15
MAX_CHANGES = 12
MAX_COMMENTS = 40
MAX_EVENTS = 40
MAX_DISPUTES = 30
NOTE = ("This is everything Verytas holds on this one item, already redacted. Verytas reviews content "
        "before publication; it does not see how a post performs afterwards.")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_LEVEL_ORDER = {"blocker": 0, "warning": 1, "advisory": 2}


class ItemRequest(BaseModel):
    kind: Literal["content", "escalation"]
    id: int
    messages: list[Annotated[str, Field(max_length=8_000)]] = Field(default_factory=list, max_length=40)


def _clip(redactor: Redactor, text: str | None, limit: int) -> str:
    """Redact first, then cut: a cut must never leave a fragment of a hidden term."""
    return redactor.redact(text or "")[:limit]


def _iso(t: Any) -> str | None:
    return _aware(t).isoformat() if t else None


def _person(u: User | None) -> dict[str, Any] | None:
    return {"name": u.name, "role": u.role} if u else None


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]


def _what_changed(redactor: Redactor, before: str, after: str) -> dict[str, Any]:
    """The sentences that left and arrived between two versions. Redacted first so the comparison and
    the output agree on placeholders, and a reworded codename doesn't show up as a change."""
    a, b = _sentences(redactor.redact(before)), _sentences(redactor.redact(after))
    removed: list[str] = []
    added: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op in ("delete", "replace"):
            removed += a[i1:i2]
        if op in ("insert", "replace"):
            added += b[j1:j2]
    return {"removed": [s[:240] for s in removed[:MAX_CHANGES]], "added": [s[:240] for s in added[:MAX_CHANGES]],
            "more": max(0, len(removed) - MAX_CHANGES) + max(0, len(added) - MAX_CHANGES)}


def _notes(redactor: Redactor, raw: dict[str, Any] | None) -> dict[str, Any]:
    # Only the creator's words; blob ids and other plumbing stay behind.
    raw = raw or {}
    words = ("intent", "irregularity", "language", "brief")
    out: dict[str, Any] = {k: _clip(redactor, str(raw[k]), 1500) for k in words if raw.get(k)}
    if raw.get("ai_used") is not None:
        out["ai_used"] = bool(raw["ai_used"])
    return out


def _attachments(redactor: Redactor, raw: dict[str, Any] | None) -> dict[str, Any]:
    images = [i for i in (raw or {}).get("images", []) if isinstance(i, dict)]
    return {"images": len(images), "image_alt_texts": [_clip(redactor, i.get("alt"), 200) for i in images[:10]
                                                        if i.get("alt")]}


def _readable_rule_fact(user: User, finding: Finding) -> tuple[bool, bool]:
    """Whether the rule and fact a finding cites may be shown. A finding is dropped from the dossier when
    either is confidential or above the caller's clearance: the model must not learn it through a quote."""
    rule_ok = finding.rule is None or (finding.rule.tier is not Tier.confidential and can_read(user, finding.rule.tier))
    fact_ok = finding.fact is None or (finding.fact.tier is not Tier.confidential and can_read(user, finding.fact.tier))
    return rule_ok, fact_ok


def _finding_out(redactor: Redactor, users: dict[int, User], f: Finding, *, detailed: bool) -> dict[str, Any]:
    rule = f.rule
    out: dict[str, Any] = {
        "id": f.id, "level": f.level, "category": f.category, "title": _clip(redactor, f.title, 300),
        "rule_code": rule.code if rule else None, "rule_title": _clip(redactor, rule.title, 200) if rule else None,
    }
    if not detailed:
        return out
    out |= {
        "rule_text": _clip(redactor, rule.text, 700) if rule else None,
        "rule_severity": rule.severity if rule else None,
        "quote": _clip(redactor, f.quote, 300), "explanation": _clip(redactor, f.explanation, 800),
        "confidence": round(f.confidence, 2), "checker": f.checker, "ai_assisted": bool(f.model),
        "suggestion": ({"original": _clip(redactor, f.suggestions[0].original, 300),
                        "proposed": _clip(redactor, f.suggestions[0].proposed, 300),
                        "why": _clip(redactor, f.suggestions[0].rationale, 400)} if f.suggestions else None),
        "decisions": [{"action": d.action, "by": _person(users.get(d.actor_id)), "reason_code": d.reason_code,
                       "reason": _clip(redactor, d.reason_text, 500), "at": _iso(d.created_at)}
                      for d in f.decisions],
    }
    return out


async def _users(session: Session, workspace_id: int, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    return {u.id: u for u in (await session.scalars(
        select(User).where(User.id.in_(ids), User.workspace_id == workspace_id))).all()}


async def _piece(session: Session, user: User, content: Content, redactor: Redactor) -> dict[str, Any]:
    versions = (await session.scalars(select(ContentVersion).where(ContentVersion.content_id == content.id)
                                      .order_by(ContentVersion.version_no))).all()
    reviews = (await session.scalars(
        select(Review).where(Review.version_id.in_([v.id for v in versions])).order_by(Review.id)
        .options(selectinload(Review.findings).selectinload(Finding.rule),
                 selectinload(Review.findings).selectinload(Finding.fact),
                 selectinload(Review.findings).selectinload(Finding.suggestions),
                 selectinload(Review.findings).selectinload(Finding.decisions)))).all()
    review_of = {r.version_id: r for r in reviews}  # the last review of each version wins
    comments = (await session.scalars(select(Comment).where(Comment.content_id == content.id)
                                      .order_by(Comment.id))).all()
    events = (await session.scalars(select(WorkflowEvent).where(WorkflowEvent.content_id == content.id)
                                    .order_by(WorkflowEvent.id))).all()
    disputes = (await session.scalars(select(Dispute).where(Dispute.content_id == content.id)
                                      .order_by(Dispute.id))).all()
    escalations = (await session.scalars(select(Escalation).where(Escalation.content_id == content.id)
                                         .order_by(Escalation.id))).all()
    users = await _users(session, content.workspace_id, (
        {content.created_by} | {v.created_by for v in versions} | {c.actor_id for c in comments}
        | {e.actor_id for e in events} | {d.user_id for d in disputes}
        | {x.raised_by for x in escalations} | {x.resolved_by for x in escalations if x.resolved_by}
        | {d.actor_id for r in reviews for f in r.findings for d in f.decisions}))
    version_no = {v.id: v.version_no for v in versions}

    # Findings the caller can't be shown are counted, never described.
    withheld = 0

    def shown(review: Review | None) -> list[Finding]:
        nonlocal withheld
        if review is None:
            return []
        keep = [f for f in review.findings if all(_readable_rule_fact(user, f))]
        withheld += len(review.findings) - len(keep)
        return sorted(keep, key=lambda f: (_LEVEL_ORDER.get(f.level, 9), f.id))

    history: list[dict[str, Any]] = []
    for i, v in enumerate(versions):
        r = review_of.get(v.id)
        s = (r.summary or {}) if r else {}
        entry: dict[str, Any] = {
            "version": v.version_no, "by": _person(users.get(v.created_by)), "saved_at": _iso(v.created_at),
            "review_status": r.status if r else None, "score": s.get("overall"),
            "blockers": s.get("blockers", 0), "warnings": s.get("warnings", 0), "advisories": s.get("advisories", 0),
            "creator_notes": _notes(redactor, v.creator_notes), "attachments": _attachments(redactor, v.attachments),
        }
        if i:
            entry["changed_since_previous"] = _what_changed(redactor, versions[i - 1].body, v.body)
        if r is not None and v is not versions[-1]:
            # Earlier rounds in brief; the latest round is given in full below.
            old = shown(r)
            entry["findings"] = [_finding_out(redactor, users, f, detailed=False) for f in old[:MAX_OLD_FINDINGS]]
        history.append(entry)

    latest_version = versions[-1] if versions else None
    latest = review_of.get(latest_version.id) if latest_version else None
    latest_findings = shown(latest)
    event = None
    if content.event_id:
        ev = await session.get(BrandEvent, content.event_id)
        if ev is not None and ev.workspace_id == content.workspace_id and ev.tier is not Tier.confidential \
                and can_read(user, ev.tier):
            event = {"name": ev.name, "kind": ev.kind, "starts_on": ev.starts_on.isoformat(),
                     "ends_on": ev.ends_on.isoformat() if ev.ends_on else None, "blackout": ev.blackout,
                     "status": ev.status, "summary": _clip(redactor, ev.summary, 600),
                     "guidance": _clip(redactor, ev.guidance, 1200), "avoid_terms": ev.avoid_terms[:20]}

    return {
        "id": content.id, "title": _clip(redactor, content.title, 300), "channel": content.channel,
        "status": content.status, "tier": content.tier, "created_at": _iso(content.created_at),
        "creator": _person(users.get(content.created_by)), "event": event,
        "latest_version": {
            "version": latest_version.version_no, "text": _clip(redactor, latest_version.body, MAX_BODY),
            "text_truncated": len(latest_version.body) > MAX_BODY,
            "creator_notes": _notes(redactor, latest_version.creator_notes),
            "attachments": _attachments(redactor, latest_version.attachments),
        } if latest_version else None,
        "versions": history,
        "latest_review": {
            "status": latest.status, "summary": {k: (latest.summary or {}).get(k) for k in
                                                 ("overall", "blockers", "warnings", "advisories")},
            "findings": [_finding_out(redactor, users, f, detailed=True) for f in latest_findings[:MAX_FINDINGS]],
            "findings_not_shown": max(0, len(latest_findings) - MAX_FINDINGS),
        } if latest else None,
        "findings_withheld_for_clearance": withheld,
        "disputes": [{"finding_id": d.finding_id, "by": _person(users.get(d.user_id)), "status": d.status,
                      "claim": _clip(redactor, d.claim, 800), "language": d.language,
                      "verdict": {k: _clip(redactor, str(v), 500) for k, v in (d.verdict or {}).items()
                                  if isinstance(v, str | int | float | bool)},
                      "filed_at": _iso(d.created_at), "decided_at": _iso(d.decided_at)}
                     for d in disputes[-MAX_DISPUTES:]],
        "escalations": [_escalation_out(redactor, users, x, version_no) for x in escalations],
        "comments": [{"by": _person(users.get(c.actor_id)), "version": version_no.get(c.version_id),
                      "reply": c.parent_id is not None, "body": _clip(redactor, c.body, 600), "at": _iso(c.created_at)}
                     for c in comments[-MAX_COMMENTS:]],
        "timeline": [{"from": e.from_status, "to": e.to_status, "by": _person(users.get(e.actor_id)),
                      "note": _clip(redactor, e.note, 400), "at": _iso(e.created_at)} for e in events[-MAX_EVENTS:]],
    }


def _escalation_out(redactor: Redactor, users: dict[int, User], x: Escalation,
                    version_no: dict[int, int]) -> dict[str, Any]:
    return {"id": x.id, "status": x.status, "finding_id": x.finding_id, "version": version_no.get(x.version_id),
            "raised_by": _person(users.get(x.raised_by)), "message": _clip(redactor, x.message, 1500),
            "raised_at": _iso(x.created_at),
            "resolution": None if x.status == "open" else {
                "outcome": x.status, "reason_code": x.resolution_code, "note": _clip(redactor, x.resolution, 800),
                "by": _person(users.get(x.resolved_by)) if x.resolved_by else None, "at": _iso(x.resolved_at)}}


async def _readable_content(session: Session, user: User, content_id: int) -> Content:
    content = await _content(session, user, content_id)  # workspace, clearance and creator scoping, one 404
    if content.tier is Tier.confidential:
        # The same line Ask Verytas draws: this text goes to a hosted model, so confidential pieces don't.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    return content


@router.post("/item-context")
async def item_context(body: ItemRequest, session: Session, user: Manager) -> dict[str, Any]:
    """The redacted dossier for one piece or escalation, plus the conversation redacted with it, so
    [[TERM_1]] in a question and in the data are the same term."""
    redactor = await _redactor(session, user)
    messages = [redactor.redact(m) for m in body.messages]

    focus: Escalation | None = None
    if body.kind == "escalation":
        focus = await session.get(Escalation, body.id)
        if focus is None or focus.workspace_id != user.workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "escalation not found")
        content = await _readable_content(session, user, focus.content_id)
    else:
        content = await _readable_content(session, user, body.id)

    piece = await _piece(session, user, content, redactor)
    out: dict[str, Any] = {"note": NOTE, "you": {"name": user.name, "role": user.role}, "kind": body.kind}
    if focus is not None:
        finding = await session.scalar(select(Finding).where(Finding.id == focus.finding_id).options(
            selectinload(Finding.rule), selectinload(Finding.fact), selectinload(Finding.suggestions),
            selectinload(Finding.decisions)))
        if finding is None or not all(_readable_rule_fact(user, finding)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "escalation not found")
        users = await _users(session, user.workspace_id, {focus.raised_by, focus.resolved_by or focus.raised_by,
                                                          *[d.actor_id for d in finding.decisions]})
        judged = await session.get(ContentVersion, focus.version_id)
        esc_view = _escalation_out(redactor, users, focus, {focus.version_id: judged.version_no if judged else 0})
        esc_view["finding"] = _finding_out(redactor, users, finding, detailed=True)
        out["escalation"] = esc_view
    out["piece"] = piece
    return _redact_all(out, redactor) | {"messages": messages}
