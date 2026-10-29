"""Conversations between creators and the brand team: sealing, live delivery and the recent-message cache.

The database is the record. Redis, when configured, does the two jobs it is good at: fanning an event out
to every API process that has a screen open (pub/sub), and serving the newest page of a conversation from
memory. Both are best effort and both fall back. A publish that can't reach Redis is delivered by this
process, and a cache miss or error reads the database. Screens catch up on reconnect by asking for
everything after the last id they hold, so a lost event costs a moment, never a message. A clone with no
Redis runs the same code as one process.

Message bodies are sealed with AES-GCM under a key kept beside the agent keys (0600), with the
conversation id as associated data, so a sealed body copied into another conversation fails to open.
Redis only ever holds sealed bodies. TLS covers the trip to the browser. It is not end-to-end on purpose:
the brand's record and Inki both have to read a conversation, which end-to-end encryption would rule out.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)
_VERSION = "v1."
# Events a slow screen may fall behind by before the oldest are dropped; it re-reads on reconnect.
_QUEUE_MAX = 200
_CACHE_TTL_S = 24 * 3600


class MessageSeal:
    """AES-256-GCM over a message's JSON payload, bound to its conversation."""

    def __init__(self, keys_dir: Path) -> None:
        self._path = keys_dir / "messages.key"
        self._aead: AESGCM | None = None

    def _cipher(self) -> AESGCM:
        if self._aead is None:
            self._aead = AESGCM(self._load_or_create())
        return self._aead

    def ensure_key(self) -> None:
        """Made at startup, not on the first message, so a fresh install fails early if it can't write it."""
        self._cipher()

    def _load_or_create(self) -> bytes:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Written whole under a private name, then linked into place: another process sees either no
            # key or the complete one, never a half-written file, and only one key ever wins.
            tmp = self._path.with_name(f".{self._path.name}.{os.getpid()}.{os.urandom(4).hex()}")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(AESGCM.generate_key(bit_length=256))
                    fh.flush()
                    os.fsync(fh.fileno())
                with contextlib.suppress(FileExistsError):
                    os.link(tmp, self._path)
            finally:
                tmp.unlink(missing_ok=True)
        key = self._path.read_bytes()
        if len(key) != 32:
            raise ValueError(f"{self._path} is not a 256-bit key")
        return key

    def fingerprint(self) -> str:
        """A short, one-way name for the key, so caches of what it sealed can be told apart from another key's."""
        return hashlib.sha256(b"verytas-message-key:" + self._load_or_create()).hexdigest()[:12]

    def seal(self, conversation_id: int, payload: dict[str, Any]) -> str:
        nonce = os.urandom(12)
        body = self._cipher().encrypt(nonce, json.dumps(payload, separators=(",", ":")).encode(),
                                      _aad(conversation_id))
        return _VERSION + base64.urlsafe_b64encode(nonce + body).decode()

    def open(self, conversation_id: int, sealed: str) -> dict[str, Any] | None:
        """The payload, or None when it does not open here (wrong conversation, other key, tampered)."""
        if not sealed.startswith(_VERSION):
            return None
        try:
            raw = base64.urlsafe_b64decode(sealed[len(_VERSION):])
            data = json.loads(self._cipher().decrypt(raw[:12], raw[12:], _aad(conversation_id)))
        except (InvalidTag, ValueError):
            return None
        return data if isinstance(data, dict) else None


def _aad(conversation_id: int) -> bytes:
    return f"conversation:{conversation_id}".encode()


class MessageHub:
    """Delivers events to the screens each person has open, and caches each conversation's newest page."""

    def __init__(self, redis_url: str | None, cache_size: int, namespace: str = "verytas") -> None:
        self._url = redis_url
        self.cache_size = cache_size
        # Every key and channel carries the deployment's name, so two deployments sharing a Redis never
        # see each other's events or pages.
        self._ns = namespace
        self._channel = f"{namespace}:user:"
        self._pages = f"{namespace}:conv"
        self._local: dict[int, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._redis: Any = None
        self._listener: asyncio.Task[None] | None = None
        # True while this process is subscribed, so a publish through Redis comes back to its own screens.
        self._subscribed = False

    def scope_pages(self, key_name: str) -> None:
        """Keep cached pages under the message key's name. A demo reset or a restore brings a new database and
        a new key while Redis keeps the old pages; those were sealed under the old key and would show as
        unreadable, so they must never be found again."""
        self._pages = f"{self._ns}:{key_name}:conv"

    @property
    def mode(self) -> str:
        return "redis" if self._subscribed else "local"

    async def start(self) -> None:
        if not self._url:
            return
        import redis.asyncio as redis  # only needed when Redis is configured

        self._redis = redis.from_url(self._url, socket_connect_timeout=1.5, socket_timeout=2.0,
                                     health_check_interval=30)
        self._listener = asyncio.create_task(self._listen())

    async def close(self) -> None:
        if self._listener:
            self._listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.aclose()

    async def _listen(self) -> None:
        """One pattern subscription per process; events are handed to the screens open here."""
        delay = 1.0
        while True:
            pubsub = self._redis.pubsub()
            try:
                await pubsub.psubscribe(self._channel + "*")
                self._subscribed, delay = True, 1.0
                async for msg in pubsub.listen():
                    if msg.get("type") != "pmessage":
                        continue
                    channel = msg["channel"].decode() if isinstance(msg["channel"], bytes) else msg["channel"]
                    with contextlib.suppress(ValueError, TypeError):
                        self._deliver(int(channel[len(self._channel):]), json.loads(msg["data"]))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any Redis failure: deliver locally until it is back
                if self._subscribed:
                    log.warning("redis pub/sub lost (%s); delivering in-process", type(exc).__name__)
                self._subscribed = False
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)

    async def publish(self, user_ids: list[int], event: dict[str, Any]) -> None:
        if self._subscribed:
            try:
                data = json.dumps(event, default=str)
                for uid in set(user_ids):
                    await self._redis.publish(f"{self._channel}{uid}", data)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("redis publish failed (%s); delivering in-process", type(exc).__name__)
        for uid in set(user_ids):
            self._deliver(uid, event)

    def _deliver(self, user_id: int, event: dict[str, Any]) -> None:
        for queue in self._local.get(user_id, ()):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self, user_id: int) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(_QUEUE_MAX)
        self._local.setdefault(user_id, set()).add(queue)
        try:
            yield queue
        finally:
            queues = self._local.get(user_id)
            if queues is not None:
                queues.discard(queue)
                if not queues:
                    self._local.pop(user_id, None)

    # The newest page of a conversation, as stored (sealed). Every write bumps the conversation's version
    # and pages are kept under the version they were read at, so a reader that loaded the database just
    # before a write can only fill a key nobody asks for again: a cached page never misses a message.

    async def cached_page(self, conversation_id: int) -> tuple[int | None, list[dict[str, Any]] | None]:
        """(version, page): the page is None on a miss; the version is None when there is no cache."""
        if self._redis is None or not self.cache_size:
            return None, None
        try:
            version = int(await self._redis.get(f"{self._pages}:{conversation_id}:v") or 0)
            raw = await self._redis.get(f"{self._pages}:{conversation_id}:recent:{version}")
        except Exception:  # noqa: BLE001
            return None, None
        return version, (json.loads(raw) if raw else None)

    async def cache_page(self, conversation_id: int, version: int | None, rows: list[dict[str, Any]]) -> None:
        if self._redis is None or version is None:
            return
        with contextlib.suppress(Exception):
            await self._redis.set(f"{self._pages}:{conversation_id}:recent:{version}", json.dumps(rows, default=str),
                                  ex=_CACHE_TTL_S)

    async def forget_page(self, conversation_id: int) -> None:
        if self._redis is None:
            return
        with contextlib.suppress(Exception):
            await self._redis.incr(f"{self._pages}:{conversation_id}:v")
