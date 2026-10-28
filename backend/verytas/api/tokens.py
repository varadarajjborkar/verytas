"""Personal tokens: what a person gives their own AI client to use /mcp as them (docs/mcp.md).

Management lives here, on the normal REST side, behind the person's web session. It is deliberately not an
MCP tool: a token must never be able to mint or revoke tokens, so a leaked one can't extend its own life.
The full secret is returned once, at creation; only its SHA-256 is stored, and no listing, log or audit
entry ever carries it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from verytas.api.deps import CurrentUser, Session, new_personal_token
from verytas.models import PersonalToken, utcnow
from verytas.schemas import ORM
from verytas.security.audit import append

router = APIRouter(tags=["tokens"])

MAX_ACTIVE = 5
DEFAULT_DAYS = 30
MAX_DAYS = 90
Scope = Literal["read", "write"]


def aware(t: datetime) -> datetime:
    """SQLite hands timestamps back naive; they are always UTC."""
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def is_active(token: PersonalToken) -> bool:
    return token.revoked_at is None and aware(token.expires_at) > utcnow()


class TokenIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=60)]
    scopes: list[Scope] = Field(default_factory=lambda: ["read"], max_length=2)
    days: int = Field(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS)

    @field_validator("name")
    @classmethod
    def _tidy(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("a token needs a name")
        return v


class TokenOut(ORM):
    id: int
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    revoked_at: datetime | None


class TokenCreated(TokenOut):
    # The only time the secret is ever sent.
    token: str


def _out(t: PersonalToken) -> dict:
    return {"id": t.id, "name": t.name, "prefix": t.prefix, "scopes": list(t.scopes),
            "created_at": t.created_at, "last_used_at": t.last_used_at, "expires_at": t.expires_at,
            "revoked_at": t.revoked_at}


@router.post("/me/tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(body: TokenIn, session: Session, user: CurrentUser) -> dict:
    scopes = ["read", "write"] if "write" in body.scopes else ["read"]
    now = utcnow()
    held = (await session.scalars(select(PersonalToken).where(
        PersonalToken.user_id == user.id, PersonalToken.revoked_at.is_(None)))).all()
    if sum(1 for t in held if is_active(t)) >= MAX_ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"you already have {MAX_ACTIVE} active tokens; revoke one before making another")
    secret, digest, prefix = new_personal_token()
    token = PersonalToken(user_id=user.id, workspace_id=user.workspace_id, name=body.name, token_hash=digest,
                          prefix=prefix, scopes=scopes, created_at=now, expires_at=now + timedelta(days=body.days))
    session.add(token)
    await session.flush()
    # The detail names the token, never its value or its prefix.
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="token.created",
                 object_type="token", object_id=token.id,
                 detail={"name": token.name, "scopes": scopes, "expires_at": token.expires_at})
    return _out(token) | {"token": secret}


@router.get("/me/tokens", response_model=list[TokenOut])
async def list_tokens(session: Session, user: CurrentUser) -> list[dict]:
    rows = (await session.scalars(select(PersonalToken).where(PersonalToken.user_id == user.id)
                                  .order_by(PersonalToken.id.desc()).limit(50))).all()
    return [_out(t) for t in rows]


@router.delete("/me/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: int, session: Session, user: CurrentUser) -> Response:
    token = await session.get(PersonalToken, token_id)
    # Someone else's token is the same 404 as a missing one.
    if token is None or token.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "token not found")
    if token.revoked_at is None:
        token.revoked_at = utcnow()
        await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="token.revoked",
                     object_type="token", object_id=token.id, detail={"name": token.name})
    return Response(status_code=status.HTTP_204_NO_CONTENT)

