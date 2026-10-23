"""The brand team's inbox and context: escalations, brand events and public contacts.

Escalations are a creator saying "a person needs to look at this". They are
screened (security/guard.py), land in the brand team's inbox with everything
needed to decide in one place (the passage, the rule or fact the finding cites
in full, and what the creator said), and are resolved into an ordinary
decision on the finding, so approval gating and guideline health see them.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from verytas.api.accounts import SelfServeBudget
from verytas.api.content import _content, _latest_review, _readable_finding, visible
from verytas.api.deps import CurrentUser, PrismDep, Session, can_read, require
from verytas.models import (
    BrandEvent,
    Content,
    ContentVersion,
    Decision,
    DecisionAction,
    Escalation,
    EventImpact,
    Fact,
    Finding,
    Level,
    PublicContact,
    Review,
    Role,
    Rule,
    User,
    utcnow,
)
from verytas.schemas import (
    ContactIn,
    ContactOut,
    EscalationIn,
    EscalationResolveIn,
    EventIn,
    EventOut,
    EventPatch,
)
from verytas.security.audit import append
from verytas.security.guard import normalize_contact
from verytas.services import events as chain
from verytas.services.contacts import screened

router = APIRouter(tags=["governance"])
Admin = Annotated[User, Depends(require(Role.brand_admin))]
Decider = Annotated[User, Depends(require(Role.reviewer, Role.approver))]
Raiser = Annotated[User, Depends(require(Role.creator, Role.reviewer, Role.approver))]
EXCERPT = 180  # characters of context either side of the flagged passage


# --- escalations ------------------------------------------------------------------------

@router.post("/findings/{finding_id}/escalations", status_code=status.HTTP_201_CREATED)
async def raise_escalation(finding_id: int, body: EscalationIn, session: Session, user: Raiser) -> dict:
    """Ask the brand team to review a finding by hand. One open request per finding."""
    finding, content = await _readable_finding(session, user, finding_id)
    if user.role is Role.creator and content.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the author can escalate their piece")
    latest = await _latest_review(session, content.id)
    if latest is None or latest.id != finding.review_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "a newer check exists; escalate the finding there")
    if await session.scalar(select(func.count()).select_from(Escalation).where(
            Escalation.finding_id == finding.id, Escalation.status == "open")):
        raise HTTPException(status.HTTP_409_CONFLICT, "this finding is already with the brand team")
    guard = await screened(session, workspace_id=user.workspace_id, actor_id=user.id, text=body.message,
                           where="escalation")
    esc = Escalation(workspace_id=user.workspace_id, content_id=content.id, finding_id=finding.id,
                     version_id=latest.version_id, raised_by=user.id, message=body.message.strip(),
                     guard=guard.as_dict())
    session.add(esc)
    await session.flush()
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="escalation.raised",
                 object_type="escalation", object_id=esc.id,
                 detail={"finding_id": finding.id, "content_id": content.id, "level": finding.level,
                         "flags": [f["code"] for f in guard.as_dict()["flagged"]]})
    await session.commit()
    return await _view(session, user, esc)


@router.get("/escalations")
async def list_escalations(session: Session, user: CurrentUser,
                           state: Annotated[str, Query(pattern="^(open|resolved|all)$")] = "open",
                           content_id: int | None = None,
                           limit: Annotated[int, Query(ge=1, le=500)] = 200) -> list[dict]:
    """The brand team's inbox, oldest open first. Creators see the requests they raised."""
    q = select(Escalation).where(Escalation.workspace_id == user.workspace_id)
    if state == "open":
        q = q.where(Escalation.status == "open")
    elif state == "resolved":
        q = q.where(Escalation.status != "open")
    if content_id is not None:
        q = q.where(Escalation.content_id == content_id)
    if user.role is Role.creator:
        q = q.where(Escalation.raised_by == user.id)
    rows = (await session.scalars(q.order_by(Escalation.id if state == "open" else Escalation.id.desc())
                                  .limit(limit))).all()
    out = []
    for esc in rows:
        content = await session.get(Content, esc.content_id)
        if content is not None and visible(user, content):
            out.append(await _view(session, user, esc))
    return out


@router.get("/escalations/count")
async def count_escalations(session: Session, user: CurrentUser) -> dict:
    """Open requests for the nav badge: one cheap query instead of the full inbox rows.
    Counts only pieces the caller may see (a creator: their own requests)."""
    q = (select(Escalation.id, Content.tier, Content.created_by, Escalation.raised_by)
         .join(Content, Escalation.content_id == Content.id)
         .where(Escalation.workspace_id == user.workspace_id, Escalation.status == "open"))
    rows = (await session.execute(q)).all()
    n = sum(1 for _, tier, owner, raiser in rows if can_read(user, tier)
            and (user.role is not Role.creator or (owner == user.id and raiser == user.id)))
    return {"open": n}


@router.get("/escalations/{esc_id}")
async def get_escalation(esc_id: int, session: Session, user: CurrentUser) -> dict:
    return await _view(session, user, await _escalation(session, user, esc_id))


@router.post("/escalations/{esc_id}/resolve")
async def resolve_escalation(esc_id: int, body: EscalationResolveIn, session: Session, user: Decider) -> dict:
    """Uphold (the finding stands) or clear it (dismissed, with a reason). Recorded as a decision."""
    esc = await _escalation(session, user, esc_id)
    if esc.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"already {esc.status}")
    finding = await session.get(Finding, esc.finding_id)
    approver = user.role in (Role.approver, Role.brand_admin)
    if body.outcome == "cleared" and finding.level is Level.blocker and not approver:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only approvers can clear a must-fix finding")
    if body.note:
        # The brand team's words go back to the creator: the same rails apply both ways.
        await screened(session, workspace_id=user.workspace_id, actor_id=user.id, text=body.note, where="escalation")
    action = DecisionAction.rejected if body.outcome == "cleared" else DecisionAction.accepted
    session.add(Decision(finding_id=finding.id, actor_id=user.id, action=action, reason_code=body.reason_code,
                         reason_text=body.note))
    esc.status, esc.resolved_by, esc.resolved_at = body.outcome, user.id, utcnow()
    esc.resolution_code, esc.resolution = body.reason_code, body.note
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="escalation.resolved",
                 object_type="escalation", object_id=esc.id,
                 detail={"outcome": body.outcome, "reason_code": body.reason_code, "finding_id": finding.id,
                         "rule_id": finding.rule_id, "level": finding.level})
    await session.commit()
    return await _view(session, user, esc)


@router.post("/escalations/{esc_id}/withdraw")
async def withdraw_escalation(esc_id: int, session: Session, user: CurrentUser) -> dict:
    esc = await _escalation(session, user, esc_id)
    if esc.raised_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the person who raised it can withdraw it")
    if esc.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"already {esc.status}")
    esc.status, esc.resolved_at = "withdrawn", utcnow()
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="escalation.withdrawn",
                 object_type="escalation", object_id=esc.id, detail={})
    await session.commit()
    return await _view(session, user, esc)


async def _escalation(session, user: User, esc_id: int) -> Escalation:
    esc = await session.get(Escalation, esc_id)
    if esc is None or esc.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "escalation not found")
    await _content(session, user, esc.content_id)  # same visibility as the piece itself
    if user.role is Role.creator and esc.raised_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "escalation not found")
    return esc


def _person(u: User | None) -> dict | None:
    return {"id": u.id, "name": u.name, "role": u.role} if u else None


async def _view(session, user: User, esc: Escalation) -> dict[str, Any]:
    """Everything a reviewer needs to decide without leaving the row: the passage, the cited record in
    full (as stored now, plus the version the finding was judged against), and the creator's words."""
    content = await session.get(Content, esc.content_id)
    finding = await session.get(Finding, esc.finding_id)
    version = await session.get(ContentVersion, esc.version_id)
    body = version.body if version else ""
    if finding.span_start is not None and finding.span_end is not None and finding.source == "body":
        s, e = finding.span_start, finding.span_end
        excerpt = {"before": body[max(0, s - EXCERPT):s], "quote": body[s:e], "after": body[e:e + EXCERPT],
                   "clipped_start": s > EXCERPT, "clipped_end": e + EXCERPT < len(body)}
    else:
        excerpt = {"before": "", "quote": finding.quote or "", "after": body[:EXCERPT * 2] if not finding.quote else "",
                   "clipped_start": False, "clipped_end": len(body) > EXCERPT * 2}
    citations: list[dict] = []
    if finding.rule_id:
        r = await session.get(Rule, finding.rule_id)
        if r is not None and can_read(user, r.tier):
            latest = await session.scalar(select(func.max(Rule.version)).where(
                Rule.workspace_id == r.workspace_id, Rule.code == r.code))
            citations.append({"kind": "rule", "id": r.id, "code": r.code, "version": r.version,
                              "latest_version": latest, "title": r.title, "text": r.text,
                              "severity": r.severity, "category": r.category,
                              "rule_kind": r.kind, "good_examples": r.good_examples, "bad_examples": r.bad_examples,
                              "pattern": r.pattern, "source_ref": r.source_ref, "status": r.status,
                              "event_id": r.event_id, "system": r.system})
    if finding.fact_id:
        f = await session.get(Fact, finding.fact_id)
        if f is not None and can_read(user, f.tier):
            citations.append({"kind": "fact", "id": f.id, "statement": f.statement, "value": f.value, "unit": f.unit,
                              "subject": f.subject, "source_ref": f.source_ref, "valid_from": f.valid_from.isoformat(),
                              "valid_to": f.valid_to.isoformat() if f.valid_to else None, "approved": f.approved,
                              "valid_today": f.approved and f.valid_on(date.today())})
    author = await session.get(User, content.created_by)
    raised_by = await session.get(User, esc.raised_by)
    resolved_by = await session.get(User, esc.resolved_by) if esc.resolved_by else None
    others = await session.scalar(select(func.count()).select_from(Escalation).where(
        Escalation.raised_by == esc.raised_by, Escalation.id != esc.id))
    return {
        "id": esc.id, "status": esc.status, "created_at": _iso(esc.created_at), "resolved_at": _iso(esc.resolved_at),
        "message": esc.message, "guard": esc.guard or {"refused": [], "flagged": []},
        "raised_by": _person(raised_by), "raised_before": others or 0,
        "content": {"id": content.id, "title": content.title, "channel": content.channel, "status": content.status,
                    "tier": content.tier, "author": _person(author), "event_id": content.event_id},
        "version": {"id": version.id, "version_no": version.version_no} if version else None,
        "finding": {"id": finding.id, "title": finding.title, "level": finding.level, "category": finding.category,
                    "explanation": finding.explanation, "checker": finding.checker, "model": finding.model,
                    "confidence": finding.confidence, "source": finding.source},
        "excerpt": excerpt, "citations": citations,
        "resolution": None if esc.status == "open" else {
            "outcome": esc.status, "code": esc.resolution_code, "note": esc.resolution, "by": _person(resolved_by)},
    }


def _iso(t) -> str | None:
    if t is None:
        return None
    from verytas.api.content import _aware

    return _aware(t).isoformat()


# --- brand events ---------------------------------------------------------------------------

async def _event_out(session, e: BrandEvent, rechecked: list[int] | None = None) -> EventOut:
    out = EventOut.model_validate(e)
    out.live = e.live_on(date.today())
    out.rules = sorted(set((await session.scalars(select(Rule.code).where(
        Rule.event_id == e.id, Rule.status == "active"))).all()))
    out.pieces = await session.scalar(select(func.count()).select_from(Content).where(Content.event_id == e.id)) or 0
    out.rechecked = rechecked or []
    return out


@router.get("/events", response_model=list[EventOut])
async def list_events(session: Session, user: CurrentUser) -> list[EventOut]:
    rows = (await session.scalars(select(BrandEvent).where(BrandEvent.workspace_id == user.workspace_id)
                                  .order_by(BrandEvent.starts_on.desc()))).all()
    return [await _event_out(session, e) for e in rows if can_read(user, e.tier)]


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED, dependencies=[SelfServeBudget])
async def create_event(body: EventIn, session: Session, admin: Admin, prism: PrismDep) -> EventOut:
    """New event: its rules are written and every piece it touches is re-checked (the update chain)."""
    e = BrandEvent(workspace_id=admin.workspace_id, created_by=admin.id, **body.model_dump())
    session.add(e)
    await session.flush()
    result = await chain.run_chain(session, prism, e, "created", f"user:{admin.id}")
    return await _event_out(session, e, result.rechecked)


@router.patch("/events/{event_id}", response_model=EventOut)
async def update_event(event_id: int, body: EventPatch, session: Session, admin: Admin, prism: PrismDep) -> EventOut:
    e = await _event(session, admin, event_id)
    if e.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "a cancelled event can't be edited")
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k == "ends_on"}
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "nothing to change")
    # Re-validate the whole event, so a patch can't make an invalid one (ends before it starts, say).
    try:
        merged = EventIn.model_validate({**{k: getattr(e, k) for k in EventIn.model_fields}, **changes})
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors()[0]["msg"]) from None
    was_live = e.live_on(date.today())
    for k, v in merged.model_dump().items():
        setattr(e, k, v)
    e.revision += 1
    e.updated_at = utcnow()
    result = await chain.run_chain(session, prism, e, "updated", f"user:{admin.id}", was_live=was_live)
    return await _event_out(session, e, result.rechecked)


@router.post("/events/{event_id}/cancel", response_model=EventOut)
async def cancel_event(event_id: int, session: Session, admin: Admin, prism: PrismDep) -> EventOut:
    e = await _event(session, admin, event_id)
    if e.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "already cancelled")
    was_live = e.live_on(date.today())
    e.status, e.revision, e.updated_at = "cancelled", e.revision + 1, utcnow()
    result = await chain.run_chain(session, prism, e, "cancelled", f"user:{admin.id}", was_live=was_live)
    return await _event_out(session, e, result.rechecked)


async def _event(session, user: User, event_id: int) -> BrandEvent:
    e = await session.get(BrandEvent, event_id)
    if e is None or e.workspace_id != user.workspace_id or not can_read(user, e.tier):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return e


@router.get("/events/{event_id}/impacts")
async def event_impacts(event_id: int, session: Session, user: CurrentUser) -> list[dict]:
    """The update chain's record: which pieces each change of this event re-checked, and how it went."""
    await _event(session, user, event_id)
    rows = (await session.execute(
        select(EventImpact, Content.title, Content.created_by, Content.tier, Review.status, Review.summary)
        .join(Content, EventImpact.content_id == Content.id).outerjoin(Review, EventImpact.review_id == Review.id)
        .where(EventImpact.event_id == event_id).order_by(EventImpact.id.desc()).limit(200))).all()
    return [{"content_id": i.content_id, "title": title, "revision": i.revision, "change": i.change,
             "review_id": i.review_id, "review_status": rs, "blockers": (summary or {}).get("blockers"),
             "at": _iso(i.created_at)}
            for i, title, created_by, tier, rs, summary in rows
            # The same visibility as the pieces themselves: clearance for everyone, and creators their own.
            if can_read(user, tier) and (user.role is not Role.creator or created_by == user.id)]


# --- public contacts ----------------------------------------------------------------------------

@router.get("/public-contacts", response_model=list[ContactOut])
async def list_contacts(session: Session, user: CurrentUser) -> list[PublicContact]:
    """Published contact details are public by definition, so every member may read the register."""
    return list((await session.scalars(select(PublicContact).where(
        PublicContact.workspace_id == user.workspace_id).order_by(PublicContact.kind, PublicContact.id))).all())


@router.post("/public-contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def add_contact(body: ContactIn, session: Session, admin: Admin) -> PublicContact:
    norm = normalize_contact(body.kind, body.value)
    if body.kind == "phone" and len(norm) < 7:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "a phone number needs at least seven digits")
    retired = await session.scalar(select(PublicContact).where(
        PublicContact.workspace_id == admin.workspace_id, PublicContact.kind == body.kind,
        PublicContact.normalized == norm, PublicContact.active.is_(False)))
    if retired is not None:
        # Listing a retired contact again brings the same row back, so its history stays in one place.
        retired.active, retired.value = True, body.value.strip()
        retired.label, retired.source_ref = body.label, body.source_ref
        await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="contact.added",
                     object_type="public_contact", object_id=retired.id, detail={"kind": body.kind, "relisted": True})
        await session.commit()
        return retired
    c = PublicContact(workspace_id=admin.workspace_id, kind=body.kind, value=body.value.strip(), normalized=norm,
                      label=body.label, source_ref=body.source_ref, created_by=admin.id)
    session.add(c)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "that contact is already listed") from None
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="contact.added",
                 object_type="public_contact", object_id=c.id, detail={"kind": body.kind})
    await session.commit()
    return c


@router.delete("/public-contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retire_contact(contact_id: int, session: Session, admin: Admin) -> None:
    c = await session.get(PublicContact, contact_id)
    if c is None or c.workspace_id != admin.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    # Kept, not deleted: findings explained against it stay explainable.
    c.active = False
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="contact.retired",
                 object_type="public_contact", object_id=c.id, detail={})
    await session.commit()
