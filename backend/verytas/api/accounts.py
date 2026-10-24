"""Self-service accounts: sign up, sign in with a password.

Everyone else gets a token from a brand admin; this is for visitors to the public demo who want their own
account next to the seeded companies. A manager signs up with a company name and becomes the brand admin
of a new, empty workspace, with a join code to hand to creators; a creator signs up with that code. The
seeded demo workspaces can't be joined this way: their data is shared by every visitor.

Off unless `self_signup` is set. Every workspace made here can spend model calls, so sign-ups are capped
per hour and in total, and reviews per self-serve workspace per day (api/content.py).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
from collections import deque
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from verytas.api.deps import CurrentUser, Session, new_token
from verytas.models import Role, Tier, User, Workspace, utcnow
from verytas.schemas import UserOut
from verytas.security.audit import append
from verytas.services.workspace import create_workspace

router = APIRouter(tags=["accounts"])

# scrypt at the interactive-login cost the docs suggest (about 50 ms here): slow enough to make a stolen
# database expensive to crack, cheap enough for a sign-in.
_N, _R, _P = 2**14, 8, 1
# Unambiguous letters and digits, so a code read aloud or off a screen is typed right.
_CODE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
# Wrong passwords per email before sign-in for it pauses, and for how long.
_MAX_FAILURES, _FAILURE_WINDOW_S = 8, 15 * 60


def _hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${key.hex()}"


def _verify(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, key = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), key)


# A hash of nothing, checked when the email is unknown so that a miss takes as long as a wrong password.
_DUMMY = _hash(secrets.token_hex(8))


def _join_code() -> str:
    return "".join(secrets.choice(_CODE) for _ in range(8))


class _Limits:
    """In-process counters: one API process serves the demo, and a restart forgetting them is harmless."""

    def __init__(self) -> None:
        self.signups: deque[float] = deque()
        self.failures: dict[str, deque[float]] = {}

    def signup_allowed(self, per_hour: int) -> bool:
        now = time.monotonic()
        while self.signups and now - self.signups[0] > 3600:
            self.signups.popleft()
        if len(self.signups) >= per_hour:
            return False
        self.signups.append(now)
        return True

    def locked(self, email: str) -> bool:
        seen = self.failures.get(email)
        now = time.monotonic()
        while seen and now - seen[0] > _FAILURE_WINDOW_S:
            seen.popleft()
        return bool(seen) and len(seen) >= _MAX_FAILURES

    def failed(self, email: str) -> None:
        if len(self.failures) > 10_000:
            # Bounded memory under a spray of made-up emails: drop the stale entries, and only if that is
            # not enough, everything (which also lifts current pauses; the per-visitor limit still holds).
            now = time.monotonic()
            self.failures = {e: d for e, d in self.failures.items() if d and now - d[-1] < _FAILURE_WINDOW_S}
            if len(self.failures) > 10_000:
                self.failures.clear()
        self.failures.setdefault(email, deque()).append(time.monotonic())


class _Spend:
    """Model-spending actions by self-serve workspaces today: per workspace and in all. In process, so a
    restart forgets them; the totals are a cost ceiling for a demo, not billing."""

    def __init__(self) -> None:
        self.day = ""
        self.per_ws: dict[int, int] = {}
        self.total = 0

    def take(self, ws: int, per_ws: int, total: int) -> str | None:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self.day:
            self.day, self.per_ws, self.total = today, {}, 0
        if self.total >= total:
            return "the demo's accounts have used today's checks; try again tomorrow or use a demo company"
        if self.per_ws.get(ws, 0) >= per_ws:
            return f"this company has used its {per_ws} checks for today; try again tomorrow"
        self.per_ws[ws] = self.per_ws.get(ws, 0) + 1
        self.total += 1
        return None


async def self_serve_budget(request: Request, session: Session, user: CurrentUser) -> None:
    """A dependency for every endpoint that spends model calls (reviews, re-reviews, disputes, AI edits,
    rule extraction, assistant context). Seeded and bootstrapped workspaces are not limited."""
    ws = await session.get(Workspace, user.workspace_id)
    if ws is None or not ws.self_serve:
        return
    state = request.app.state
    if not hasattr(state, "self_serve_spend"):
        state.self_serve_spend = _Spend()
    refused = state.self_serve_spend.take(ws.id, state.settings.self_serve_actions_per_day,
                                          state.settings.self_serve_actions_per_day_total)
    if refused:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, refused)


SelfServeBudget = Depends(self_serve_budget)


def _limits(request: Request) -> _Limits:
    if not hasattr(request.app.state, "account_limits"):
        request.app.state.account_limits = _Limits()
    return request.app.state.account_limits


def _enabled(request: Request) -> None:
    if not request.app.state.settings.self_signup:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "self-service accounts are not enabled here")


Enabled = Depends(_enabled)
Password = Annotated[str, Field(min_length=10, max_length=128)]


class CompanySignup(BaseModel):
    kind: Literal["company"]
    company_name: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: Password


class CreatorSignup(BaseModel):
    kind: Literal["creator"]
    join_code: str = Field(min_length=6, max_length=16)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: Password


class SignIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccountOut(BaseModel):
    user: UserOut
    token: str = Field(description="Shown once. Send as 'Authorization: Bearer <token>'.")
    company: str
    join_code: str | None = Field(default=None, description="For a new company: what its creators sign up with.")


@router.get("/accounts/config")
async def config(request: Request) -> dict:
    """Whether this server takes sign-ups, so the sign-in page offers them only where they work."""
    return {"self_signup": bool(request.app.state.settings.self_signup)}


@router.post("/accounts/signup", response_model=AccountOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Enabled])
async def signup(body: Annotated[CompanySignup | CreatorSignup, Field(discriminator="kind")], request: Request,
                 session: Session) -> AccountOut:
    settings = request.app.state.settings
    email = body.email.lower()
    if await session.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "that email already has an account; sign in instead")
    if isinstance(body, CreatorSignup):
        ws = await session.scalar(select(Workspace).where(Workspace.join_code == body.join_code.strip().upper(),
                                                          Workspace.self_serve.is_(True)))
        if ws is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no company has that join code")
    elif await session.scalar(select(func.count(Workspace.id)).where(Workspace.self_serve.is_(True))) \
            >= settings.self_signup_max_workspaces:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "this demo has all the companies it can hold")
    if not _limits(request).signup_allowed(settings.self_signup_per_hour):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many sign-ups right now; try again later")
    hashed = await asyncio.to_thread(_hash, body.password)

    try:
        if isinstance(body, CompanySignup):
            ws, user, token = await create_workspace(session, name=body.company_name.strip(), admin_email=email,
                                                     admin_name=body.name.strip())
            ws.self_serve, ws.join_code = True, _join_code()
            user.password_hash, user.token_issued_at = hashed, utcnow()
            await session.flush()
            action = "account.signed_up_company"
        else:
            token, token_hash = new_token()
            user = User(workspace_id=ws.id, email=email, name=body.name.strip(), role=Role.creator,
                        clearance=Tier.internal, token_hash=token_hash, password_hash=hashed,
                        token_issued_at=utcnow())
            session.add(user)
            await session.flush()
            action = "account.signed_up_creator"
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "that email already has an account; sign in instead") from None
    await append(session, workspace_id=ws.id, actor=f"user:{user.id}", action=action, object_type="user",
                 object_id=user.id, detail={"role": user.role.value})
    return AccountOut(user=UserOut.model_validate(user), token=token, company=ws.name,
                      join_code=ws.join_code if user.role is Role.brand_admin else None)


@router.post("/accounts/signin", response_model=AccountOut, dependencies=[Enabled])
async def signin(body: SignIn, request: Request, session: Session) -> AccountOut:
    """A fresh token for a signed-up account. Tokens are stored only as hashes, so the old one can't be
    handed back: it is replaced, and a session elsewhere signs out."""
    email, limits = body.email.lower(), _limits(request)
    if limits.locked(email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many wrong passwords; try again in 15 minutes")
    user = await session.scalar(select(User).where(func.lower(User.email) == email, User.password_hash.is_not(None)))
    ok = await asyncio.to_thread(_verify, body.password, user.password_hash if user else _DUMMY)
    if user is None or not ok:
        limits.failed(email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    token, user.token_hash = new_token()
    user.token_issued_at = utcnow()
    ws = await session.get(Workspace, user.workspace_id)
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="account.signed_in",
                 object_type="user", object_id=user.id)
    return AccountOut(user=UserOut.model_validate(user), token=token, company=ws.name if ws else "",
                      join_code=ws.join_code if ws and user.role is Role.brand_admin else None)


@router.post("/accounts/signout")
async def signout(session: Session, user: CurrentUser) -> dict:
    """Revoke the caller's token. Only a password account is revoked, because it can sign in again; a token an
    admin issued (or the demo picker's, shared by everyone who picks that person) would be lost for good."""
    if not user.password_hash:
        return {"revoked": False}
    # The stored hash is replaced by one nobody holds the token for; the next sign-in issues a new one.
    _, user.token_hash = new_token()
    user.token_issued_at = None
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="account.signed_out",
                 object_type="user", object_id=user.id)
    return {"revoked": True}


@router.get("/accounts/join-code")
async def join_code(session: Session, user: CurrentUser) -> dict:
    """The code creators join this company with, for its brand admin. Seeded workspaces have none."""
    ws = await session.get(Workspace, user.workspace_id)
    if user.role is not Role.brand_admin or ws is None or not ws.join_code:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no join code for this workspace")
    return {"join_code": ws.join_code, "company": ws.name}
