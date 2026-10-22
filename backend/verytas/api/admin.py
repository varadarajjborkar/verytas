from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from verytas.api.deps import CurrentUser, Session, can_read, new_token, require
from verytas.models import (
    AuditEntry,
    BrandAsset,
    BrandEvent,
    Content,
    ContentVersion,
    Dispute,
    Escalation,
    Fact,
    Finding,
    Person,
    Review,
    Role,
    Rule,
    Tier,
    User,
    Workspace,
)
from verytas.schemas import AuditOut, BootstrapIn, PersonOut, TokenOut, UserIn, UserOut
from verytas.security.audit import append, verify_chain
from verytas.services.workspace import create_workspace

router = APIRouter(tags=["admin"])
Admin = Annotated[User, Depends(require(Role.brand_admin))]
AuditReader = Annotated[User, Depends(require(Role.auditor))]


@router.post("/bootstrap", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def bootstrap(body: BootstrapIn, session: Session) -> TokenOut:
    """First-run setup. Only works while no workspace exists."""
    if await session.scalar(select(func.count(Workspace.id))):
        raise HTTPException(status.HTTP_409_CONFLICT, "already bootstrapped; ask a brand admin for an account")
    _, admin, token = await create_workspace(session, name=body.workspace_name, admin_email=body.admin_email,
                                             admin_name=body.admin_name)
    await session.commit()
    return TokenOut(user=UserOut.model_validate(admin), token=token)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/users", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserIn, session: Session, admin: Admin) -> TokenOut:
    token, token_hash = new_token()
    user = User(workspace_id=admin.workspace_id, email=body.email, name=body.name, role=body.role,
                clearance=body.clearance, token_hash=token_hash)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from None
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="user.created",
                 object_type="user", object_id=user.id, detail={"role": body.role, "clearance": body.clearance})
    await session.commit()
    return TokenOut(user=UserOut.model_validate(user), token=token)


@router.get("/users", response_model=list[UserOut] | list[PersonOut])
async def list_users(session: Session, user: CurrentUser) -> list[UserOut] | list[PersonOut]:
    """Brand admins manage accounts and see emails and clearances; everyone else gets names and roles."""
    users = (await session.scalars(select(User).where(User.workspace_id == user.workspace_id))).all()
    if user.role is Role.brand_admin:
        return [UserOut.model_validate(u) for u in users]
    return [PersonOut.model_validate(u) for u in users]


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(session: Session, user: AuditReader, limit: Annotated[int, Query(ge=1, le=500)] = 100,
                    object_type: str | None = None, before: int | None = None) -> list:
    """Newest first; pass the last id as `before` for the next page."""
    q = select(AuditEntry).where(AuditEntry.workspace_id == user.workspace_id)
    if object_type:
        q = q.where(AuditEntry.object_type == object_type)
    # Hidden entries are dropped after the query, so keep reading back until the page is full: a run of
    # confidential activity must not leave a lower-clearance reader with an empty page and no way past it.
    out: list[AuditEntry] = []
    cursor = before
    for _ in range(_AUDIT_SCAN_PAGES):
        page = q if cursor is None else q.where(AuditEntry.id < cursor)
        batch = list((await session.scalars(page.order_by(AuditEntry.id.desc()).limit(limit))).all())
        tiers = await _object_tiers(session, batch)
        out += [e for e in batch if _visible(user, e, tiers)]
        if len(out) >= limit or len(batch) < limit:
            break
        cursor = batch[-1].id
    return out[:limit]


_AUDIT_SCAN_PAGES = 10


def _visible(user: User, entry: AuditEntry, tiers: dict[tuple[str, str], Tier]) -> bool:
    # The term list itself is brand-admin only; its entries (embargo dates) follow it.
    if entry.object_type == "confidential_term":
        return user.role is Role.brand_admin
    return can_read(user, tiers.get((entry.object_type, entry.object_id or ""), Tier.public))


# Each tiered object type, and how to reach the row that carries its tier. Entries keep their labels
# (rule codes, asset names, notes) because the chain hashes them, so the read side hides the whole
# entry from anyone the object itself is hidden from.
_TIER_OF = {
    "rule": lambda ids: select(Rule.id, Rule.tier).where(Rule.id.in_(ids)),
    "fact": lambda ids: select(Fact.id, Fact.tier).where(Fact.id.in_(ids)),
    "brand_asset": lambda ids: select(BrandAsset.id, BrandAsset.tier).where(BrandAsset.id.in_(ids)),
    "person": lambda ids: select(Person.id, Person.tier).where(Person.id.in_(ids)),
    "content": lambda ids: select(Content.id, Content.tier).where(Content.id.in_(ids)),
    "event": lambda ids: select(BrandEvent.id, BrandEvent.tier).where(BrandEvent.id.in_(ids)),
    "dispute": lambda ids: select(Dispute.id, Content.tier).join(Content, Content.id == Dispute.content_id)
    .where(Dispute.id.in_(ids)),
    "escalation": lambda ids: select(Escalation.id, Content.tier).join(Content, Content.id == Escalation.content_id)
    .where(Escalation.id.in_(ids)),
    "review": lambda ids: select(Review.id, Content.tier).join(ContentVersion, ContentVersion.id == Review.version_id)
    .join(Content, Content.id == ContentVersion.content_id).where(Review.id.in_(ids)),
    "finding": lambda ids: select(Finding.id, Content.tier).join(Review, Review.id == Finding.review_id)
    .join(ContentVersion, ContentVersion.id == Review.version_id).join(Content, Content.id == ContentVersion.content_id)
    .where(Finding.id.in_(ids)),
}


async def _object_tiers(session, entries: list[AuditEntry]) -> dict[tuple[str, str], Tier]:
    wanted: dict[str, set[int]] = {}
    for e in entries:
        if e.object_type in _TIER_OF and e.object_id and e.object_id.isdigit():
            wanted.setdefault(e.object_type, set()).add(int(e.object_id))
    out = {}
    for kind, ids in wanted.items():
        for oid, tier in (await session.execute(_TIER_OF[kind](ids))).all():
            out[(kind, str(oid))] = tier
    return out


@router.get("/audit/verify")
async def audit_verify(session: Session, user: AuditReader) -> dict:
    report = await verify_chain(session, user.workspace_id)
    return {"ok": report.ok, "entries": report.entries, "first_bad_id": report.first_bad_id,
            "reason": report.reason}
