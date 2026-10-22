from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from verytas.api.deps import CurrentUser, Session, new_token, require
from verytas.models import AuditEntry, Role, User, Workspace
from verytas.schemas import AuditOut, BootstrapIn, TokenOut, UserIn, UserOut
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


@router.get("/users", response_model=list[UserOut])
async def list_users(session: Session, user: CurrentUser) -> list[User]:
    return list((await session.scalars(select(User).where(User.workspace_id == user.workspace_id))).all())


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(session: Session, user: AuditReader, limit: int = 100, object_type: str | None = None) -> list:
    q = select(AuditEntry).where(AuditEntry.workspace_id == user.workspace_id)
    if object_type:
        q = q.where(AuditEntry.object_type == object_type)
    return list((await session.scalars(q.order_by(AuditEntry.id.desc()).limit(min(limit, 500)))).all())


@router.get("/audit/verify")
async def audit_verify(session: Session, user: AuditReader) -> dict:
    report = await verify_chain(session, user.workspace_id)
    return {"ok": report.ok, "entries": report.entries, "first_bad_id": report.first_bad_id,
            "reason": report.reason}
