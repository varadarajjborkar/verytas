"""Who is calling /mcp, and may they: Origin check, personal-token check, per-token rate limit.

The gate sits in front of the SDK's session manager, so nothing from the SDK (or a tool) runs for a request
that has not passed it. Failures are uniform on purpose: a caller learns "unauthorised", never whether the
token was unknown, expired or revoked.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from verytas.api.deps import PAT_PREFIX, hash_token
from verytas.api.tokens import aware, is_active
from verytas.models import PersonalToken, User, utcnow

log = logging.getLogger("verytas.mcp")

SCOPE_KEY = "verytas.principal"
# last_used_at is a hint for the person reading their token list, not a log, so it is written at most
# this often per token.
LAST_USED_EVERY = timedelta(minutes=1)
_MAX_TOKEN_LEN = 128


@dataclass(frozen=True)
class Principal:
    token_id: int
    token_name: str
    user_id: int
    workspace_id: int
    scopes: frozenset[str]
    expires_at: datetime


async def authenticate(app, raw: str) -> Principal | None:
    # Only the personal-token scheme is looked up here. A web session token ("vt_...") is a different
    # audience and is refused before touching the database.
    if not raw.startswith(PAT_PREFIX) or len(raw) > _MAX_TOKEN_LEN:
        return None
    async with app.state.db.sessionmaker() as session:
        token = await session.scalar(select(PersonalToken).where(PersonalToken.token_hash == hash_token(raw)))
        if token is None or not is_active(token):
            return None
        user = await session.get(User, token.user_id)
        # A token is bound to the workspace it was made in; a person moved elsewhere takes nothing with them.
        if user is None or user.workspace_id != token.workspace_id:
            return None
        now = utcnow()
        if token.last_used_at is None or now - aware(token.last_used_at) >= LAST_USED_EVERY:
            token.last_used_at = now
            await session.commit()
        return Principal(token.id, token.name, user.id, token.workspace_id, frozenset(token.scopes or ["read"]),
                         aware(token.expires_at))


class CallLimiter:
    """Sliding window of tool calls per token, in process like the sign-in and search limits."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._calls: dict[int, deque[float]] = {}
        self._noted: dict[int, float] = {}

    def take(self, token_id: int) -> tuple[bool, bool]:
        """Returns (allowed, first refusal in this window). The caller audits only the first refusal, so
        a loop hammering a limited token can't fill the audit chain."""
        now = time.monotonic()
        recent = self._calls.setdefault(token_id, deque())
        while recent and now - recent[0] > 60:
            recent.popleft()
        if len(recent) >= self.per_minute:
            first = now - self._noted.get(token_id, -120.0) > 60
            if first:
                self._noted[token_id] = now
            return False, first
        recent.append(now)
        if len(self._calls) > 5_000:
            for tid in [t for t, d in self._calls.items() if not d or now - d[-1] > 60]:
                del self._calls[tid]
                self._noted.pop(tid, None)
        return True, False


def _unauthorised(*, had_credentials: bool) -> JSONResponse:
    challenge = 'Bearer realm="verytas-mcp"' + (', error="invalid_token"' if had_credentials else "")
    return JSONResponse({"error": "unauthorized", "error_description": "a valid personal token is required"},
                        status_code=401, headers={"WWW-Authenticate": challenge})


def origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    if origin is None:
        return True  # not a browser
    return origin.strip().lower().rstrip("/") in {a.strip().lower().rstrip("/") for a in allowed}


class McpGate:
    """The ASGI endpoint mounted at /mcp: checks, then hands the request to the SDK's session manager."""

    def __init__(self, session_manager) -> None:
        self._manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        app = scope["app"]
        headers = Headers(scope=scope)
        # Origin first, before any token is looked at: a page in someone's browser must not get even a
        # token oracle out of this endpoint.
        if not origin_allowed(headers.get("origin"), app.state.settings.mcp_allowed_origins):
            log.warning("mcp request refused: origin not allowed")
            await JSONResponse({"error": "forbidden", "error_description": "origin not allowed"},
                               status_code=403)(scope, receive, send)
            return
        scheme, _, credential = headers.get("authorization", "").partition(" ")
        credential = credential.strip()
        principal = None
        if scheme.lower() == "bearer" and credential:
            principal = await authenticate(app, credential)
        if principal is None:
            await _unauthorised(had_credentials=bool(credential))(scope, receive, send)
            return
        scope[SCOPE_KEY] = principal
        await self._manager.handle_request(scope, receive, send)
