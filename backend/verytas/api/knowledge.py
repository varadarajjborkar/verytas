"""Brand knowledge base: rules, approved facts and confidential terms."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from verytas.api.deps import CurrentUser, Session, can_read, require
from verytas.checks.base import FactView
from verytas.checks.claims import relevance
from verytas.models import ConfidentialTerm, Fact, Role, Rule, RuleStatus, User
from verytas.schemas import FactIn, FactOut, RuleIn, RuleOut, RulePatch, TermIn, TermOut
from verytas.security.audit import append

router = APIRouter(tags=["knowledge"])
Admin = Annotated[User, Depends(require(Role.brand_admin))]


# --- rules ---------------------------------------------------------------------

@router.get("/rules", response_model=list[RuleOut])
async def list_rules(session: Session, user: CurrentUser, state: RuleStatus | None = None) -> list[Rule]:
    q = select(Rule).where(Rule.workspace_id == user.workspace_id)
    if state:
        q = q.where(Rule.status == state)
    rules = (await session.scalars(q.order_by(Rule.code, Rule.version))).all()
    return [r for r in rules if can_read(user, r.tier)]


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(body: RuleIn, session: Session, admin: Admin) -> Rule:
    latest = await session.scalar(
        select(func.max(Rule.version)).where(Rule.workspace_id == admin.workspace_id, Rule.code == body.code))
    if latest:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.code} exists; PATCH it to create a new version")
    rule = Rule(workspace_id=admin.workspace_id, **body.model_dump())
    session.add(rule)
    await session.flush()
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="rule.created",
                 object_type="rule", object_id=rule.id, detail={"code": rule.code, "status": rule.status})
    await session.commit()
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleOut)
async def update_rule(rule_id: int, body: RulePatch, session: Session, admin: Admin) -> Rule:
    """Content edits create a new version (old findings keep citing the text they
    were judged against); a status-only change updates in place."""
    rule = await session.get(Rule, rule_id)
    if rule is None or rule.workspace_id != admin.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    changes = body.model_dump(exclude_unset=True)
    content_fields = {k: v for k, v in changes.items() if k != "status"}

    target = rule
    if content_fields:
        copied = {c.name: getattr(rule, c.name) for c in Rule.__table__.columns if c.name not in ("id", "created_at")}
        target = Rule(**copied)
        target.version = rule.version + 1
        for k, v in content_fields.items():
            setattr(target, k, v)
        target.status = changes.get("status", rule.status)
        rule.status = RuleStatus.retired
        session.add(target)
    elif "status" in changes:
        rule.status = changes["status"]
    await session.flush()
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="rule.updated",
                 object_type="rule", object_id=target.id,
                 detail={"code": rule.code, "from_version": rule.version, "to_version": target.version,
                         "fields": sorted(changes)})
    await session.commit()
    return target


# --- facts -----------------------------------------------------------------------

@router.get("/facts", response_model=list[FactOut])
async def list_facts(session: Session, user: CurrentUser, valid_on: date | None = None,
                     q: str | None = None) -> list[Fact]:
    facts = [f for f in (await session.scalars(
        select(Fact).where(Fact.workspace_id == user.workspace_id).order_by(Fact.id))).all()
        if can_read(user, f.tier)]
    if valid_on:
        facts = [f for f in facts if f.valid_on(valid_on)]
    if q:
        scored = [(relevance(q, FactView(f.id, f.statement, f.value, f.unit, f.subject, f.source_ref,
                                         f.valid_from, f.valid_to)), f) for f in facts]
        facts = [f for s, f in sorted(scored, key=lambda t: -t[0]) if s > 0]
    return facts


@router.post("/facts", response_model=FactOut, status_code=status.HTTP_201_CREATED)
async def create_fact(body: FactIn, session: Session, admin: Admin) -> Fact:
    fact = Fact(workspace_id=admin.workspace_id, approved=True, **body.model_dump())
    session.add(fact)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid fact") from None
    if body.supersedes_id:
        old = await session.get(Fact, body.supersedes_id)
        if old and old.workspace_id == admin.workspace_id and (old.valid_to is None or old.valid_to > body.valid_from):
            # Close the old fact's window where the new one opens, so exactly
            # one version of the figure is valid on any given day.
            old.valid_to = body.valid_from
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="fact.created",
                 object_type="fact", object_id=fact.id, detail={"supersedes": body.supersedes_id})
    await session.commit()
    return fact


# --- confidential terms ------------------------------------------------------------

@router.get("/confidential-terms", response_model=list[TermOut])
async def list_terms(session: Session, admin: Admin) -> list[ConfidentialTerm]:
    return list((await session.scalars(
        select(ConfidentialTerm).where(ConfidentialTerm.workspace_id == admin.workspace_id))).all())


@router.post("/confidential-terms", response_model=TermOut, status_code=status.HTTP_201_CREATED)
async def create_term(body: TermIn, session: Session, admin: Admin) -> ConfidentialTerm:
    term = ConfidentialTerm(workspace_id=admin.workspace_id, **body.model_dump())
    session.add(term)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "term already listed") from None
    # The audit trail records that a term was added, never the term itself.
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="term.created",
                 object_type="confidential_term", object_id=term.id, detail={"embargo_until": body.embargo_until})
    await session.commit()
    return term
