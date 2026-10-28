from __future__ import annotations

import hashlib
import secrets
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.models import Role, Tier, User, utcnow
from verytas.prism.orchestrator import Prism

_bearer = HTTPBearer(auto_error=False)
# For a route that authenticates by hand rather than through CurrentUser (api/messages.py stream).
bearer = _bearer


# Personal tokens for the /mcp endpoint (api/tokens.py). A different audience from the web session token:
# the REST routes never accept one, and /mcp never accepts a session token.
PAT_PREFIX = "vt_pat_"


def new_token() -> tuple[str, str]:
    """Returns (token shown once to the user, hash we store)."""
    token = "vt_" + secrets.token_urlsafe(32)
    # token_urlsafe can, rarely, start with "pat_"; keep the two prefixes disjoint so a session token is
    # never mistaken for a personal one.
    while token.startswith(PAT_PREFIX):
        token = "vt_" + secrets.token_urlsafe(32)
    return token, hash_token(token)


def new_personal_token() -> tuple[str, str, str]:
    """Returns (token shown once, hash we store, display prefix: the first 8 characters after the scheme)."""
    body = secrets.token_urlsafe(32)
    return PAT_PREFIX + body, hash_token(PAT_PREFIX + body), body[:8]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.sessionmaker() as session:
        yield session


def get_prism(request: Request) -> Prism:
    return request.app.state.prism


Session = Annotated[AsyncSession, Depends(get_session)]
PrismDep = Annotated[Prism, Depends(get_prism)]


async def current_user(
    request: Request, session: Session, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})
    if creds.credentials.startswith(PAT_PREFIX):
        # Its hash is not in `users` and would fail below anyway; refusing it by name says why, and keeps the
        # separation from depending on that.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "personal tokens are only accepted at /mcp",
                            headers={"WWW-Authenticate": "Bearer"})
    user = await session.scalar(select(User).where(User.token_hash == hash_token(creds.credentials)))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token", headers={"WWW-Authenticate": "Bearer"})
    if user.password_hash and user.token_issued_at is not None:
        issued = user.token_issued_at if user.token_issued_at.tzinfo else user.token_issued_at.replace(tzinfo=UTC)
        if utcnow() - issued > timedelta(days=request.app.state.settings.account_token_days):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired; sign in again",
                                headers={"WWW-Authenticate": "Bearer"})
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require(*roles: Role) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory: brand admins can do anything a listed role can."""
    allowed = set(roles) | {Role.brand_admin}

    async def check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"needs role: {', '.join(sorted(r.value for r in roles))}")
        return user

    return check


def can_read(user: User, tier: Tier) -> bool:
    return tier.rank <= user.clearance.rank
