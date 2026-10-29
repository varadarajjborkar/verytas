"""Conversations: a creator and the brand team talk a piece through, with Inki on call.

One conversation per creator and brand-team member. Calls are not built here: either side shares a link
from a meeting service the company already uses (Google Meet, Teams, Zoom...), which arrives as a call
card. What people type is not screened or refused: a ten-digit number is as likely an order or a price as
a phone number, and a conversation that second-guesses its users gets abandoned. The limits are on Inki.

A message can answer an earlier one, carry files (images, documents, videos up to ten minutes), be edited
by its writer and be deleted for everyone. Deleting replaces the sealed body with an empty one and releases
the files at once; the record keeps that a message was deleted, not what it said.

Live updates are a server-sent event stream per person (GET /conversations/stream). A screen that
reconnects asks for messages after the last id it holds, so the stream may drop events without losing any.
Edits and deletions arrive as the same "message" event, which screens apply by id.

Inki answers "@Inki" only for someone who has agreed to it reading the conversation (inki-consent), and
only within the limits in services/inki_guard.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from verytas.api.accounts import self_serve_budget
from verytas.api.assistant import _detail
from verytas.api.content import visible
from verytas.api.deps import CurrentUser, Session, bearer, current_user
from verytas.media import serve, storage
from verytas.media.files import MediaError
from verytas.memory.thread import Turn, VectorCache, earlier_turns, expand, ranks
from verytas.models import (
    Content,
    Conversation,
    MediaBlob,
    MediaDigest,
    Message,
    MessageAttachment,
    MessageVector,
    Role,
    User,
    utcnow,
)
from verytas.prism.disputes import workspace_redactor
from verytas.schemas import UTCModel
from verytas.security.audit import append
from verytas.services.contacts import contacts_for
from verytas.services.inki import SYSTEM as INKI_SYSTEM
from verytas.services.inki import InkiTask, read_upload
from verytas.services.inki_guard import LIMITED, REFUSAL, RateLimit, asks_for_instructions, checked
from verytas.services.messages import MessageHub, MessageSeal

log = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])

BRAND_TEAM = {Role.reviewer, Role.approver, Role.brand_admin}
MAX_TEXT = 4_000
PAGE = 30
MAX_PAGE = 100
MAX_FILES = 6
MAX_VIDEO_S = 10 * 60
REPLY_EXCERPT = 140
# Messages Inki reads before the one that asked it, pieces and files it may look at.
INKI_TRANSCRIPT = 12
INKI_PIECES = 2
INKI_FILES = 3
INKI_READ_S = 120.0
# A stream is closed and reopened by the browser now and then, so no proxy idles it out.
STREAM_S = 50.0
HEARTBEAT_S = 15.0
_INKI = re.compile(r"(?<![\w@])@inki\b", re.IGNORECASE)
_LIMITS = RateLimit(per_hour=20)
# Ids in paths and bodies stay inside a database integer; a bigger one is a 422, not an overflow.
MAX_ID = 2**62
Id = Annotated[int, Path(ge=1, le=MAX_ID)]
# Reading files for Inki has its own small pool: a read that outlives its deadline can't be cancelled, and it
# must not hold up the threads every other request uses.
_READER = ThreadPoolExecutor(max_workers=2, thread_name_prefix="inki-read")
# A preview is rendered no larger than this on its long side, whatever size the page claims to be.
POSTER_SIDE = 720
# Meeting services a call link may point at. Anything else is refused: a call card is a button people
# trust, so it must not lead to an arbitrary site.
CALL_HOSTS = {
    "meet.google.com": "Google Meet",
    "teams.microsoft.com": "Microsoft Teams",
    "teams.live.com": "Microsoft Teams",
    "zoom.us": "Zoom",
    "join.skype.com": "Skype",
    "meet.jit.si": "Jitsi Meet",
    "whereby.com": "Whereby",
}
_OFFICE = ("wordprocessingml", "presentationml", "spreadsheetml")


def call_provider(url: str) -> str | None:
    # A backslash or a space reads differently in a browser than in urlsplit ("https://evil.io\\.zoom.us"
    # is evil.io to Chrome), so anything urlsplit and a browser could disagree on is refused outright.
    if not url.isprintable() or any(c in url for c in "\\ \"'<>"):
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password or port is not None:
        return None
    host = (parts.hostname or "").lower()
    if parts.netloc.lower() != host:
        return None
    for known, name in CALL_HOSTS.items():
        if host == known or host.endswith("." + known):
            return name
    return None


def file_kind(media_type: str) -> Literal["image", "video", "document"] | None:
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("video/"):
        return "video"
    if media_type == "application/pdf" or any(k in media_type for k in _OFFICE):
        return "document"
    return None


# --- shapes -------------------------------------------------------------------------------------------

class PersonOut(BaseModel):
    id: int
    name: str
    role: Role


class ContactOut(PersonOut):
    conversation_id: int | None = None


class CallOut(BaseModel):
    url: str
    provider: str


class PieceOut(BaseModel):
    id: int
    title: str


class TopicOut(PieceOut):
    status: str


class FileOut(BaseModel):
    id: str
    kind: Literal["image", "video", "document"]
    name: str
    media_type: str
    bytes: int
    duration: float | None = None


class ReplyOut(BaseModel):
    id: int
    sender: str  # a name, or "Inki"
    excerpt: str
    deleted: bool = False


class MessageOut(UTCModel):
    id: int
    conversation_id: int
    kind: Literal["text", "call", "inki"]
    text: str
    call: CallOut | None = None
    files: list[FileOut] = Field(default_factory=list)
    piece: PieceOut | None = None
    reply_to: ReplyOut | None = None
    sender: PersonOut | None  # None: Inki
    asked_by: PersonOut | None = None
    created_at: datetime
    edited: bool = False
    deleted: bool = False


class ConversationOut(UTCModel):
    id: int
    other: PersonOut
    last: MessageOut | None = None
    unread: int = 0
    # The other person spoke last (or Inki answered them): the ball is in this person's court.
    needs_reply: bool = False
    # The piece this conversation most recently pointed at, and where it stands now.
    topic: TopicOut | None = None
    last_message_at: datetime


class StartIn(BaseModel):
    user_id: int


class MessageIn(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT)
    call_url: str | None = Field(default=None, max_length=500)
    content_id: int | None = Field(default=None, ge=1, le=MAX_ID)
    files: list[Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]] = Field(default_factory=list, max_length=MAX_FILES)
    reply_to: int | None = Field(default=None, ge=1, le=MAX_ID)
    # Chosen by the browser per message, so a retry after a dropped connection is stored once.
    client_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,40}$")

    @field_validator("text")
    @classmethod
    def _trim(cls, text: str) -> str:
        return text.strip()


class EditIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)

    @field_validator("text")
    @classmethod
    def _trim(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("a message can't be edited to nothing; delete it instead")
        return text.strip()


class ReadIn(BaseModel):
    last_id: int = Field(ge=0, le=MAX_ID)


class ConsentIn(BaseModel):
    accept: Literal[True]


# --- helpers ------------------------------------------------------------------------------------------

def _hub(request: Request) -> MessageHub:
    return request.app.state.messages


def _seal(request: Request) -> MessageSeal:
    return request.app.state.message_seal


def _side(user: User) -> Literal["creator", "manager"] | None:
    if user.role == Role.creator:
        return "creator"
    return "manager" if user.role in BRAND_TEAM else None


def _person(u: User) -> PersonOut:
    return PersonOut(id=u.id, name=u.name, role=u.role)


async def _mine(session: Session, user: User, conversation_id: int) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or user.id not in (conv.creator_id, conv.manager_id) or conv.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    return conv


async def _message(session: Session, conv: Conversation, message_id: int) -> Message:
    m = await session.get(Message, message_id)
    if m is None or m.conversation_id != conv.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    return m


def _when(value: datetime | str | None) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _row(m: Message) -> dict[str, Any]:
    """A message as stored, for the cache: still sealed."""
    def iso(t: datetime | None) -> str | None:
        return t.isoformat() if t else None

    return {"id": m.id, "conversation_id": m.conversation_id, "sender_id": m.sender_id, "asked_by": m.asked_by,
            "kind": m.kind, "sealed": m.sealed, "content_id": m.content_id, "reply_to_id": m.reply_to_id,
            "created_at": iso(m.created_at), "edited_at": iso(m.edited_at), "deleted_at": iso(m.deleted_at)}


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= REPLY_EXCERPT else text[:REPLY_EXCERPT - 3].rstrip() + "..."


async def _render(session: Session, seal: MessageSeal | None, rows: list[dict[str, Any]]) -> list[MessageOut]:
    """Messages as people see them. Without a seal the text, files and call stay out (they travel sealed,
    see _publish). A piece's title shows only while both people in the conversation may still open it, so
    a tier or clearance change after the message was sent hides it again."""
    if not rows:
        return []
    convs = {c.id: c for c in (await session.scalars(select(Conversation).where(
        Conversation.id.in_({r["conversation_id"] for r in rows})))).all()}
    quoted = {m.id: m for m in (await session.scalars(select(Message).where(
        Message.id.in_({r.get("reply_to_id") for r in rows if r.get("reply_to_id")})))).all()}
    ids = {r["sender_id"] for r in rows} | {r["asked_by"] for r in rows} | {m.sender_id for m in quoted.values()} \
        | {c.creator_id for c in convs.values()} | {c.manager_id for c in convs.values()}
    users = {u.id: u for u in (await session.scalars(select(User).where(User.id.in_(ids - {None})))).all()}
    piece_ids = {r["content_id"] for r in rows if r["content_id"]}
    pieces = {c.id: c for c in (await session.scalars(select(Content).where(Content.id.in_(piece_ids)))).all()} \
        if piece_ids else {}

    def readable(conversation_id: int, content_id: int | None) -> Content | None:
        conv, piece = convs.get(conversation_id), pieces.get(content_id)
        members = [users.get(conv.creator_id), users.get(conv.manager_id)] if conv else []
        ok = piece is not None and members and all(m is not None and visible(m, piece) for m in members)
        return piece if ok else None

    def reply(r: dict[str, Any]) -> ReplyOut | None:
        q = quoted.get(r.get("reply_to_id"))
        if q is None or q.conversation_id != r["conversation_id"]:
            return None
        who = "Inki" if q.sender_id is None else (users[q.sender_id].name if q.sender_id in users else "Someone")
        if q.deleted_at is not None:
            return ReplyOut(id=q.id, sender=who, excerpt="", deleted=True)
        body = seal.open(q.conversation_id, q.sealed) if seal else None
        text = (body or {}).get("text") or ("A file" if (body or {}).get("files") else "")
        return ReplyOut(id=q.id, sender=who, excerpt=_excerpt(text))

    out = []
    for r in rows:
        sender, asker = users.get(r["sender_id"]), users.get(r["asked_by"])
        if r["sender_id"] is not None and sender is None:
            continue  # the account is gone; nothing to attribute the message to
        deleted = r.get("deleted_at") is not None
        payload = (seal.open(r["conversation_id"], r["sealed"]) if seal else {}) if not deleted else {}
        unreadable = payload is None
        payload = payload or {}
        call = payload.get("call")
        piece = None if deleted else readable(r["conversation_id"], r["content_id"])
        out.append(MessageOut(
            id=r["id"], conversation_id=r["conversation_id"], kind=r["kind"],
            text="This message can't be opened." if unreadable else payload.get("text", ""),
            call=CallOut(**call) if isinstance(call, dict) else None,
            files=[FileOut(**f) for f in payload.get("files", []) if isinstance(f, dict)],
            piece=PieceOut(id=piece.id, title=piece.title) if piece else None,
            reply_to=None if deleted else reply(r),
            sender=_person(sender) if sender else None, asked_by=_person(asker) if asker else None,
            created_at=_when(r["created_at"]), edited=r.get("edited_at") is not None, deleted=deleted))
    return out


async def _publish(hub: MessageHub, session: Session, conv: Conversation, message: Message) -> None:
    """The event carries the body still sealed; the stream opens it for the screen it is going to, so the
    text never crosses Redis readable. New, edited and deleted messages all go out this way."""
    [out] = await _render(session, None, [_row(message)])
    quoted = await session.get(Message, message.reply_to_id) if message.reply_to_id and not message.deleted_at else None
    await hub.publish([conv.creator_id, conv.manager_id], {
        "type": "message", "message": out.model_dump(mode="json"),
        "sealed": None if message.deleted_at else message.sealed,
        "reply_sealed": quoted.sealed if quoted is not None and quoted.deleted_at is None else None})


def _opened(seal: MessageSeal, event: dict[str, Any]) -> dict[str, Any]:
    sealed = event.pop("sealed", None)
    reply_sealed = event.pop("reply_sealed", None)
    if event.get("type") == "message" and reply_sealed and event["message"].get("reply_to"):
        message = event["message"]
        body = seal.open(message["conversation_id"], reply_sealed) or {}
        message["reply_to"]["excerpt"] = _excerpt(body.get("text") or ("A file" if body.get("files") else ""))
    if event.get("type") == "message" and sealed:
        message = event["message"]
        payload = seal.open(message["conversation_id"], sealed)
        message["text"] = (payload or {}).get("text", "") if payload is not None else "This message can't be opened."
        message["call"] = (payload or {}).get("call")
        message["files"] = (payload or {}).get("files", [])
    return event


async def _files(session: Session, user: User, ids: list[str]) -> list[dict[str, Any]]:
    """The uploads a message may carry: this person's own, in this workspace, of a kind a conversation shows,
    and videos no longer than ten minutes."""
    if not ids:
        return []
    blobs = {b.id: b for b in (await session.scalars(select(MediaBlob).where(
        MediaBlob.id.in_(ids), MediaBlob.workspace_id == user.workspace_id, MediaBlob.created_by == user.id))).all()}
    out = []
    for blob_id in dict.fromkeys(ids):
        blob = blobs.get(blob_id)
        kind = file_kind(blob.media_type) if blob else None
        if blob is None or kind is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "attach images, documents (PDF, Word, PowerPoint, Excel) or videos you uploaded")
        meta: dict[str, Any] = {"id": blob.id, "kind": kind, "name": blob.name or kind.title(),
                                "media_type": blob.media_type, "bytes": blob.size}
        if kind == "video":
            from verytas.media.video import probe

            try:
                info = await asyncio.to_thread(probe, blob.data)
            except MediaError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"that video can't be read ({exc})") from exc
            if info["duration"] > MAX_VIDEO_S:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    "videos in a conversation can be up to 10 minutes long")
            meta["duration"] = info["duration"]
        out.append(meta)
    return out


# --- routes: conversations ----------------------------------------------------------------------------

@router.get("/conversations/people", response_model=list[ContactOut])
async def people(session: Session, user: CurrentUser) -> list[ContactOut]:
    """Who this person may start a conversation with: a creator, anyone on the brand team; the brand team,
    any creator. Auditors read the record, so they have no conversations of their own."""
    side = _side(user)
    if side is None:
        return []
    roles = BRAND_TEAM if side == "creator" else {Role.creator}
    others = (await session.scalars(select(User).where(User.workspace_id == user.workspace_id,
                                                       User.role.in_(roles), User.id != user.id)
                                    .order_by(User.name))).all()
    mine = select(Conversation).where(or_(Conversation.creator_id == user.id, Conversation.manager_id == user.id))
    existing = {(c.manager_id if side == "creator" else c.creator_id): c.id
                for c in (await session.scalars(mine)).all()}
    return [ContactOut(id=u.id, name=u.name, role=u.role, conversation_id=existing.get(u.id)) for u in others]


@router.post("/conversations", response_model=ConversationOut)
async def start(body: StartIn, request: Request, session: Session, user: CurrentUser) -> ConversationOut:
    """Opens the conversation with this person, creating it the first time; asking twice opens the same one."""
    side = _side(user)
    other = await session.get(User, body.user_id)
    if side is None or other is None or other.workspace_id != user.workspace_id or other.id == user.id \
            or _side(other) in (None, side):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no one to talk to there")
    # Plain values, because a rollback below expires every loaded object in the session.
    other_out, workspace_id, user_id = _person(other), user.workspace_id, user.id
    creator_id, manager_id = (user.id, other.id) if side == "creator" else (other.id, user.id)
    where = and_(Conversation.creator_id == creator_id, Conversation.manager_id == manager_id)
    conv = await session.scalar(select(Conversation).where(where))
    if conv is None:
        session.add(Conversation(workspace_id=workspace_id, creator_id=creator_id, manager_id=manager_id))
        try:
            await session.commit()
            created = True
        except IntegrityError:  # both started it at the same moment: the other one is the conversation
            await session.rollback()
            created = False
        conv = await session.scalar(select(Conversation).where(where))
        if conv is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "couldn't open the conversation; try again")
        conv_id, last_at = conv.id, conv.last_message_at
        if created:
            await append(session, workspace_id=workspace_id, actor=f"user:{user_id}",
                         action="conversation.started", object_type="conversation", object_id=conv_id,
                         detail={"with": other_out.id})
        return ConversationOut(id=conv_id, other=other_out, last_message_at=last_at)
    return ConversationOut(id=conv.id, other=other_out, last_message_at=conv.last_message_at)


@router.get("/conversations", response_model=list[ConversationOut])
async def conversations(request: Request, session: Session, user: CurrentUser) -> list[ConversationOut]:
    convs = (await session.scalars(select(Conversation).where(
        or_(Conversation.creator_id == user.id, Conversation.manager_id == user.id))
        .order_by(Conversation.last_message_at.desc()))).all()
    if not convs:
        return []
    ids = [c.id for c in convs]
    others = {u.id: u for u in (await session.scalars(select(User).where(User.id.in_(
        {c.manager_id if c.creator_id == user.id else c.creator_id for c in convs})))).all()}
    last_ids = select(func.max(Message.id)).where(Message.conversation_id.in_(ids)).group_by(Message.conversation_id)
    lasts = {m.conversation_id: m
             for m in (await session.scalars(select(Message).where(Message.id.in_(last_ids)))).all()}
    rendered = {m.conversation_id: m
                for m in await _render(session, _seal(request), [_row(m) for m in lasts.values()])}
    topics = await _topics(session, convs)
    unread = await _unread_by_conversation(session, user, convs)
    out = []
    for c in convs:
        other = others.get(c.manager_id if c.creator_id == user.id else c.creator_id)
        if other is None:
            continue
        last = lasts.get(c.id)
        waiting = last is not None and last.deleted_at is None and (
            last.sender_id == other.id or (last.sender_id is None and last.asked_by == other.id))
        out.append(ConversationOut(id=c.id, other=_person(other), last=rendered.get(c.id),
                                   unread=unread.get(c.id, 0), needs_reply=waiting, topic=topics.get(c.id),
                                   last_message_at=c.last_message_at))
    return out


async def _topics(session: Session, convs: list[Conversation]) -> dict[int, TopicOut]:
    """Each conversation's latest linked piece both people may still open, with its current status."""
    latest = select(Message.conversation_id, func.max(Message.id).label("mid")).where(
        Message.conversation_id.in_([c.id for c in convs]), Message.content_id.is_not(None),
        Message.deleted_at.is_(None)).group_by(Message.conversation_id).subquery()
    rows = (await session.execute(select(Message.conversation_id, Message.content_id)
                                  .join(latest, Message.id == latest.c.mid))).all()
    if not rows:
        return {}
    pieces = {p.id: p for p in (await session.scalars(select(Content).where(
        Content.id.in_({cid for _, cid in rows})))).all()}
    members = {u.id: u for u in (await session.scalars(select(User).where(User.id.in_(
        {c.creator_id for c in convs} | {c.manager_id for c in convs})))).all()}
    by_conv = {c.id: c for c in convs}
    out = {}
    for conv_id, content_id in rows:
        piece, conv = pieces.get(content_id), by_conv[conv_id]
        both = [members.get(conv.creator_id), members.get(conv.manager_id)]
        if piece and all(m is not None and visible(m, piece) for m in both):
            out[conv_id] = TopicOut(id=piece.id, title=piece.title, status=piece.status.value)
    return out


async def _unread_by_conversation(session: Session, user: User, convs: list[Conversation]) -> dict[int, int]:
    """Live messages after this person's read position that they did not write themselves."""
    counts: dict[int, int] = {}
    for c in convs:
        read = c.creator_read_id if c.creator_id == user.id else c.manager_read_id
        counts[c.id] = int(await session.scalar(select(func.count(Message.id)).where(
            Message.conversation_id == c.id, Message.id > read, Message.deleted_at.is_(None),
            or_(Message.sender_id.is_(None), Message.sender_id != user.id))) or 0)
    return counts


@router.get("/conversations/unread")
async def unread(session: Session, user: CurrentUser) -> dict[str, int]:
    convs = (await session.scalars(select(Conversation).where(
        or_(Conversation.creator_id == user.id, Conversation.manager_id == user.id)))).all()
    return {"unread": sum((await _unread_by_conversation(session, user, list(convs))).values())}


# --- routes: Inki consent -----------------------------------------------------------------------------

@router.get("/conversations/inki-consent")
async def inki_consent(user: CurrentUser) -> dict[str, Any]:
    return {"accepted_at": user.inki_consent_at.isoformat() if user.inki_consent_at else None}


@router.post("/conversations/inki-consent")
async def accept_inki(body: ConsentIn, session: Session, user: CurrentUser) -> dict[str, Any]:
    if user.inki_consent_at is None:
        user.inki_consent_at = utcnow()
        await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="inki.consented",
                     object_type="user", object_id=user.id, detail={})
    return {"accepted_at": user.inki_consent_at.isoformat()}


@router.delete("/conversations/inki-consent", status_code=204)
async def withdraw_inki(session: Session, user: CurrentUser) -> None:
    if user.inki_consent_at is not None:
        user.inki_consent_at = None
        await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="inki.withdrawn",
                     object_type="user", object_id=user.id, detail={})


# --- routes: messages ---------------------------------------------------------------------------------

@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def messages(conversation_id: Id, request: Request, session: Session, user: CurrentUser,
                   before: Annotated[int | None, Query(ge=1, le=MAX_ID)] = None,
                   after: Annotated[int | None, Query(ge=0, le=MAX_ID)] = None,
                   limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = PAGE) -> list[MessageOut]:
    """Oldest first. No cursor: the newest page. `before`: the page above it. `after`: everything newer than
    what a screen holds (capped), which is how a reconnecting screen catches up."""
    conv = await _mine(session, user, conversation_id)
    hub = _hub(request)
    newest = before is None and after is None and limit <= hub.cache_size
    version = None
    if newest:
        version, cached = await hub.cached_page(conv.id)
        # Served only while it still ends at the conversation's newest message: one indexed lookup, and a page
        # left over from another database (a reset, a restore) or a write that missed the version bump is
        # read again instead of shown.
        if cached is not None and cached and cached[-1]["id"] == await session.scalar(
                select(func.max(Message.id)).where(Message.conversation_id == conv.id)):
            return await _render(session, _seal(request), cached[-limit:])
    q = select(Message).where(Message.conversation_id == conv.id)
    if after is not None:
        rows = (await session.scalars(q.where(Message.id > after).order_by(Message.id).limit(limit))).all()
        return await _render(session, _seal(request), [_row(m) for m in rows])
    if before is not None:
        q = q.where(Message.id < before)
    take = max(limit, hub.cache_size) if newest else limit
    rows = list(reversed((await session.scalars(q.order_by(Message.id.desc()).limit(take))).all()))
    stored = [_row(m) for m in rows]
    if newest:
        await hub.cache_page(conv.id, version, stored)
    return await _render(session, _seal(request), stored[-limit:])


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send(conversation_id: Id, body: MessageIn, request: Request, session: Session,
               user: CurrentUser) -> MessageOut:
    conv = await _mine(session, user, conversation_id)
    conv_id, user_id, workspace_id = conv.id, user.id, user.workspace_id
    members = [conv.creator_id, conv.manager_id]
    if body.client_id:
        again = await session.scalar(select(Message).where(Message.conversation_id == conv_id,
                                                           Message.client_id == body.client_id))
        if again is not None:  # the same send twice: answer with what was stored the first time
            return (await _render(session, _seal(request), [_row(again)]))[0]
    if not body.text and not body.call_url and not body.files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "write a message, attach a file or share a call link")
    call = None
    if body.call_url:
        provider = call_provider(body.call_url.strip())
        if provider is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {
                "message": "Share a meeting link from Google Meet, Microsoft Teams, Zoom, Skype, Jitsi or Whereby "
                           "(it starts with https://)."})
        call = {"url": body.call_url.strip(), "provider": provider}
    if body.reply_to is not None:
        target = await session.get(Message, body.reply_to)
        if target is None or target.conversation_id != conv_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "the message being answered isn't in this conversation")
    if body.content_id is not None:
        piece = await session.get(Content, body.content_id)
        creator, manager = await session.get(User, conv.creator_id), await session.get(User, conv.manager_id)
        # Only the creator's own pieces, and only ones both of them may open, so a link never shows either
        # side a title they couldn't already see.
        if piece is None or piece.created_by != conv.creator_id or creator is None or manager is None \
                or not visible(creator, piece) or not visible(manager, piece):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    files = await _files(session, user, body.files)
    asks_inki = bool(body.text and _INKI.search(body.text))
    if asks_inki:
        if user.inki_consent_at is None:
            raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, {
                "code": "inki_consent_required",
                "message": "Inki reads this conversation to answer. Agree to that first, or remove @Inki."})
        await self_serve_budget(request, session, user)
    payload: dict[str, Any] = {"text": body.text}
    if call:
        payload["call"] = call
    if files:
        payload["files"] = files
    message = Message(conversation_id=conv_id, sender_id=user_id, kind="call" if call else "text",
                      sealed=_seal(request).seal(conv_id, payload), content_id=body.content_id,
                      reply_to_id=body.reply_to, client_id=body.client_id)
    session.add(message)
    try:
        await session.flush()
        for f in files:
            session.add(MessageAttachment(message_id=message.id, blob_id=f["id"]))
        conv.last_message_at = utcnow()
        await session.commit()
    except IntegrityError:  # the same client_id raced itself: the one that landed is the answer
        await session.rollback()
        again = await session.scalar(select(Message).where(Message.conversation_id == conv_id,
                                                           Message.client_id == body.client_id)) \
            if body.client_id else None
        if again is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "the message wasn't stored; send it again") from None
        return (await _render(session, _seal(request), [_row(again)]))[0]
    await _hub(request).forget_page(conv_id)
    message_id = message.id
    if call:
        # The record keeps that a call was offered and where, not the link itself.
        await append(session, workspace_id=workspace_id, actor=f"user:{user_id}",
                     action="conversation.call_shared", object_type="conversation", object_id=conv_id,
                     detail={"provider": call["provider"]})
    await _publish(_hub(request), session, conv, message)
    if asks_inki:
        await _hub(request).publish(members, {"type": "inki", "conversation_id": conv_id, "state": "thinking"})
        app = request.app
        app.state.prism.schedule_job(lambda: _inki_reply(app, conv_id, user_id, message_id))
    return (await _render(session, _seal(request), [_row(message)]))[0]


@router.patch("/conversations/{conversation_id}/messages/{message_id}", response_model=MessageOut)
async def edit(conversation_id: Id, message_id: Id, body: EditIn, request: Request, session: Session,
               user: CurrentUser) -> MessageOut:
    """The writer changes their words. Files, call links and the piece stay as sent; Inki is not asked again."""
    conv = await _mine(session, user, conversation_id)
    m = await _message(session, conv, message_id)
    if m.sender_id != user.id or m.deleted_at is not None or m.kind == "inki":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the writer can edit their own message")
    payload = _seal(request).open(conv.id, m.sealed) or {}
    if payload.get("text") != body.text:
        m.sealed = _seal(request).seal(conv.id, {**payload, "text": body.text})
        m.edited_at = utcnow()
        # The old words' vector goes too; recall embeds the new ones when it next needs them.
        await session.execute(delete(MessageVector).where(MessageVector.message_id == m.id))
        await session.commit()
        await _hub(request).forget_page(conv.id)
        await _publish(_hub(request), session, conv, m)
    return (await _render(session, _seal(request), [_row(m)]))[0]


@router.delete("/conversations/{conversation_id}/messages/{message_id}", response_model=MessageOut)
async def delete_message(conversation_id: Id, message_id: Id, request: Request, session: Session,
                         user: CurrentUser) -> MessageOut:
    """Deleted for everyone, by its writer (or, for an Inki answer, by whoever asked). The words and files
    go now; what stays is that a message was deleted, so a reply to it still makes sense."""
    conv = await _mine(session, user, conversation_id)
    m = await _message(session, conv, message_id)
    owner = m.asked_by if m.sender_id is None else m.sender_id
    if owner != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the writer can delete a message")
    if m.deleted_at is None:
        held = set((await session.scalars(select(MessageAttachment.blob_id).where(
            MessageAttachment.message_id == m.id))).all())
        m.sealed = _seal(request).seal(conv.id, {"text": ""})
        m.deleted_at = utcnow()
        m.content_id = None
        # What the words meant goes with them (memory/thread.py keeps a sealed vector per turn).
        await session.execute(delete(MessageVector).where(MessageVector.message_id == m.id))
        await session.flush()
        await storage.release(session, conv.workspace_id, held)
        await session.commit()
        await append(session, workspace_id=conv.workspace_id, actor=f"user:{user.id}",
                     action="conversation.message_deleted", object_type="conversation", object_id=conv.id,
                     detail={"message": m.id, "files": len(held)})
        await _hub(request).forget_page(conv.id)
        await _publish(_hub(request), session, conv, m)
    return (await _render(session, _seal(request), [_row(m)]))[0]


@router.post("/conversations/{conversation_id}/read", status_code=204)
async def mark_read(conversation_id: Id, body: ReadIn, request: Request, session: Session, user: CurrentUser) -> None:
    conv = await _mine(session, user, conversation_id)
    newest = int(await session.scalar(select(func.max(Message.id)).where(Message.conversation_id == conv.id)) or 0)
    last = min(body.last_id, newest)  # never past what exists, and never backwards
    if conv.creator_id == user.id and last > conv.creator_read_id:
        conv.creator_read_id = last
    elif conv.manager_id == user.id and last > conv.manager_read_id:
        conv.manager_read_id = last
    else:
        return
    await session.commit()
    await _hub(request).publish([user.id], {"type": "read", "conversation_id": conv.id, "last_id": last})


# --- routes: files ------------------------------------------------------------------------------------

async def _shared_file(session: Session, user: User, conversation_id: int, blob_id: str) -> MediaBlob:
    """An upload carried by a live message of a conversation this person is in; one 404 for anything else."""
    conv = await _mine(session, user, conversation_id)
    held = await session.scalar(select(MessageAttachment.id).join(Message, Message.id == MessageAttachment.message_id)
                                .where(Message.conversation_id == conv.id, Message.deleted_at.is_(None),
                                       MessageAttachment.blob_id == blob_id).limit(1))
    blob = await session.get(MediaBlob, blob_id, options=[defer(MediaBlob.data)]) if held else None
    if blob is None or blob.workspace_id != conv.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    return blob


@router.get("/conversations/{conversation_id}/files/{blob_id}")
async def shared_file(conversation_id: Id, blob_id: str, session: Session, user: CurrentUser,
                      range_: Annotated[str | None, Header(alias="range")] = None) -> Response:
    """The file itself, shown in the page rather than saved: inline, never cached, and in ranges so a video
    can be played and sought without sending all of it."""
    blob = await _shared_file(session, user, conversation_id, blob_id)
    return await serve.inline(session, blob.id, blob.media_type, blob.size, range_)


@router.get("/conversations/{conversation_id}/files/{blob_id}/poster")
async def file_poster(conversation_id: Id, blob_id: str, session: Session, user: CurrentUser) -> Response:
    """A still for a video or the first page of a PDF, so a file shows as itself in the conversation."""
    blob = await _shared_file(session, user, conversation_id, blob_id)
    if not blob.media_type.startswith("video/") and blob.media_type != "application/pdf":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preview for this file")
    data = await session.scalar(select(MediaBlob.data).where(MediaBlob.id == blob.id))
    try:
        jpeg = await asyncio.wait_for(asyncio.to_thread(_poster, blob.media_type, bytes(data or b"")), 30)
    except Exception:  # noqa: BLE001 - a file that can't be previewed shows as a plain file card
        jpeg = None
    if jpeg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preview for this file")
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600",
                                                            "X-Content-Type-Options": "nosniff"})


def _poster(media_type: str, raw: bytes) -> bytes | None:
    from PIL import Image

    img: Image.Image | None = None
    if media_type.startswith("video/"):
        from verytas.media.video import frames

        got = frames(raw, max_seconds=2.0, every_s=1.0)
        img = got[-1][1] if got else None
    elif media_type == "application/pdf":
        import pypdfium2 as pdfium

        from verytas.media.documents import _PDFIUM

        with _PDFIUM:
            pdf = pdfium.PdfDocument(raw)
            try:
                page = pdf[0]
                width, height = page.get_size()
                # Sized from the page's own claim, so a page that says it is metres wide renders small.
                scale = min(1.0, POSTER_SIDE / max(width, height, 1.0))
                img = page.render(scale=scale).to_pil()
            finally:
                pdf.close()
    if img is None:
        return None
    img = img.convert("RGB")
    img.thumbnail((720, 720))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


# --- routes: live -------------------------------------------------------------------------------------

@router.get("/conversations/stream")
async def stream(request: Request,
                 creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> StreamingResponse:
    # Not CurrentUser: a dependency's session lives as long as the response, and this response stays
    # open for most of a minute. On SQLite that held a read open that made other requests wait.
    async with request.app.state.db.sessionmaker() as session:
        user_id = (await current_user(request, session, creds)).id
    hub, seal = _hub(request), _seal(request)

    async def events():
        loop = asyncio.get_running_loop()
        ends = loop.time() + STREAM_S
        async with hub.subscribe(user_id) as queue:
            yield f"retry: 1500\nevent: ready\ndata: {json.dumps({'mode': hub.mode})}\n\n"
            while (left := ends - loop.time()) > 0:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=min(HEARTBEAT_S, left))
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(_opened(seal, dict(event)), default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# --- Inki ---------------------------------------------------------------------------------------------

async def _inki_reply(app: Any, conversation_id: int, asked_by: int, question_id: int) -> None:
    """Answers one @Inki after the asker's request has returned. A model failure still answers, from the
    record; anything else tells the screens to stop waiting."""
    try:
        await _answer(app, conversation_id, asked_by, question_id)
    except Exception:  # noqa: BLE001 - a background job: log it, and never leave "Inki is reading" up
        log.exception("inki reply failed")
        async with app.state.db.sessionmaker() as session:
            conv = await session.get(Conversation, conversation_id)
            members = [conv.creator_id, conv.manager_id] if conv else []
        with contextlib.suppress(Exception):
            await app.state.messages.publish(members, {"type": "inki", "conversation_id": conversation_id,
                                                        "state": "failed"})


async def _digest(app: Any, session: Session, blob_id: str) -> tuple[str, str, str] | None:
    """(name, kind, text) for one shared file, read once and kept."""
    blob = await session.get(MediaBlob, blob_id)
    if blob is None:
        return None
    kind = file_kind(blob.media_type) or "file"
    kept = await session.get(MediaDigest, blob_id)
    if kept is None:
        settings = app.state.settings
        loop = asyncio.get_running_loop()
        try:
            text = await asyncio.wait_for(loop.run_in_executor(
                _READER, lambda: read_upload(blob.media_type, blob.data, asr_model=settings.asr_model)), INKI_READ_S)
        except TimeoutError:
            # Said, not kept: the next question tries again.
            return blob.name or kind.title(), kind, "The file took too long to read just now."
        except Exception as exc:  # noqa: BLE001 - an unreadable file is said to be so, not fatal
            return blob.name or kind.title(), kind, f"The file couldn't be read ({type(exc).__name__})."
        kept = MediaDigest(blob_id=blob_id, text=text)
        session.add(kept)
        try:
            await session.commit()
        except IntegrityError:  # read twice at once; either copy will do
            await session.rollback()
            return blob_id, kind, text
    return blob.name or kind.title(), kind, kept.text


async def _still_consents(app: Any, user_id: int) -> bool:
    """Read fresh from the database, not from an object loaded before a long wait."""
    async with app.state.db.sessionmaker() as session:
        return await session.scalar(select(User.inki_consent_at).where(User.id == user_id)) is not None


async def _answer(app: Any, conversation_id: int, asked_by: int, question_id: int) -> None:
    hub: MessageHub = app.state.messages
    seal: MessageSeal = app.state.message_seal
    async with app.state.db.sessionmaker() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            return
        conv_id, workspace_id = conv.id, conv.workspace_id
        creator_id, manager_id = conv.creator_id, conv.manager_id
        rows = list(reversed((await session.scalars(select(Message).where(
            Message.conversation_id == conv_id, Message.id <= question_id, Message.deleted_at.is_(None))
            .order_by(Message.id.desc()).limit(INKI_TRANSCRIPT + 1))).all()))
        question = next((m for m in rows if m.id == question_id), None)
        if question is None:
            return  # deleted before Inki got to it
        names = {creator_id: "Creator", manager_id: "Brand team"}

        def said(m: Message) -> tuple[str, str, list[dict]]:
            payload = seal.open(conv_id, m.sealed) or {}
            call = payload.get("call")
            shared = [f for f in payload.get("files", []) if isinstance(f, dict)]
            text = payload.get("text") or ""
            if call:
                text += f" (shared a {call['provider']} link)"
            if shared:
                text += f" (shared {', '.join(f['name'] for f in shared)})"
            return "Inki" if m.sender_id is None else names.get(m.sender_id, "Someone"), text.strip(), shared

        transcript, file_ids = [], []
        for m in rows:
            who, text, shared = said(m)
            file_ids += [f["id"] for f in shared]
            if text:
                transcript.append((who, text))
        question_text = (seal.open(conv_id, question.sealed) or {}).get("text", "")
        # Older turns, for recall below once the question is known to be answered (verytas/memory/thread.py).
        settings = app.state.settings
        turns: list[Turn] = []
        if settings.memory_enabled and settings.memory_recall_turns and rows:
            older = list(reversed((await session.scalars(select(Message).where(
                Message.conversation_id == conv_id, Message.id < rows[0].id, Message.deleted_at.is_(None))
                .order_by(Message.id.desc()).limit(settings.memory_recall_scan))).all()))
            turns = [Turn(m.id, who, text) for m in older for who, text, _ in [said(m)] if text]
        # The pieces this conversation has pointed at, newest first; the question's own piece leads.
        linked = [m.content_id for m in reversed(rows) if m.content_id]
        older = (await session.scalars(select(Message.content_id).where(
            Message.conversation_id == conv_id, Message.content_id.is_not(None), Message.deleted_at.is_(None))
            .order_by(Message.id.desc()).limit(20))).all()
        creator, manager = await session.get(User, creator_id), await session.get(User, manager_id)
        asker = await session.get(User, asked_by)
        consented = asker is not None and asker.inki_consent_at is not None
        public = await contacts_for(session, workspace_id)
        redactor = await workspace_redactor(session, workspace_id)
        piece_ids, pieces = [], []
        for pid in dict.fromkeys(linked + list(older)):
            piece = await session.get(Content, pid)
            if piece and creator and manager and visible(creator, piece) and visible(manager, piece):
                piece_ids.append(pid)
                pieces.append({"title": piece.title, **await _detail(session, pid, redactor)})
            if len(piece_ids) == INKI_PIECES:
                break
        if not consented:
            return  # consent withdrawn in the meantime: nothing is read, nothing is sent
        # Refusals and the hourly limit come before any file is read: neither should cost OCR or speech.
        fixed = REFUSAL if asks_for_instructions(question_text) else None if _LIMITS.take(asked_by) else LIMITED
        files = []
        if fixed is None:
            for blob_id in list(dict.fromkeys(reversed(file_ids)))[:INKI_FILES]:
                got = await _digest(app, session, blob_id)
                if got:
                    files.append({"name": got[0], "kind": got[1], "text": got[2]})
        await session.commit()  # no transaction held across the model calls below

        # Beyond the recent turns, the earlier ones that bear on the question, found by meaning, by shared
        # words and by the question reworded the way the answer was likely written. Only for a question Inki
        # will answer: a refusal or the hourly limit sends nothing anywhere, rewording included. The rewording
        # is the first time the question leaves, so consent is read fresh before it.
        earlier: list[tuple[str, str]] = []
        if fixed is None and turns:
            if not await _still_consents(app, asked_by):
                return
            try:
                phrasings = []
                if ranks(turns):  # a short history comes whole, unranked: nothing to reword for
                    _, quick, _, _ = app.state.prism.guarded_providers(redactor)
                    phrasings = await expand(quick, question_text, [text for _, text in transcript[-3:-1]])
                picked = await earlier_turns(VectorCache(app.state.db, seal), app.state.embedder, conv_id, turns,
                                             question_text, settings.memory_recall_turns, phrasings)
                earlier = [(t.who, t.text) for t in picked]
            except Exception:  # noqa: BLE001 - recall is extra context; without it Inki still has the recent turns
                log.warning("inki recall of earlier turns failed", exc_info=True)

        task = InkiTask(transcript=transcript, pieces=pieces, files=files, earlier=earlier)
        if fixed is not None:
            reply = fixed  # answered here; the model is never asked
        elif not await _still_consents(app, asked_by):
            return
        else:
            _, llm, _, _ = app.state.prism.guarded_providers(redactor)
            try:
                reply = (await llm.run(task)).reply.strip()
            except Exception:  # noqa: BLE001 - a model failure answers from the record, and says so
                log.warning("inki reply fell back to the record", exc_info=True)
                reply = task.heuristic().reply
            reply = checked(reply or task.heuristic().reply, INKI_SYSTEM, public)
        if not await _still_consents(app, asked_by):
            return  # withdrawn while Inki was reading or thinking: nothing is posted
        message = Message(conversation_id=conv_id, sender_id=None, asked_by=asked_by, kind="inki",
                          sealed=seal.seal(conv_id, {"text": reply}), reply_to_id=question_id,
                          content_id=piece_ids[0] if piece_ids else None)
        session.add(message)
        conv = await session.get(Conversation, conv_id)
        conv.last_message_at = utcnow()
        await session.commit()
        await hub.forget_page(conv_id)
        await _publish(hub, session, conv, message)
