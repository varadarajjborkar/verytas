"""Conversations: a creator and the brand team talk a piece through, with Inki on call.

One conversation per creator and brand-team member. Calls are not built here: either side shares a link
from a meeting service the company already uses (Google Meet, Teams, Zoom...), which arrives as a call
card, so nobody has to hand over a phone number. Typed text passes the same guard as escalations, which
refuses personal numbers and "WhatsApp me", so the conversation stays where the brand can stand behind it.

Live updates are a server-sent event stream per person (GET /conversations/stream). A screen that
reconnects asks for messages after the last id it holds, so the stream may drop events without losing any.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from verytas.api.accounts import self_serve_budget
from verytas.api.assistant import _detail
from verytas.api.content import visible
from verytas.api.deps import CurrentUser, Session, bearer, current_user
from verytas.models import Content, Conversation, Message, Role, User, utcnow
from verytas.prism.disputes import workspace_redactor
from verytas.schemas import UTCModel
from verytas.security.audit import append
from verytas.services.contacts import screened
from verytas.services.inki import InkiTask
from verytas.services.messages import MessageHub, MessageSeal

log = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])

BRAND_TEAM = {Role.reviewer, Role.approver, Role.brand_admin}
MAX_TEXT = 4_000
PAGE = 30
MAX_PAGE = 100
# Messages Inki reads before the one that asked it, and pieces it may look at.
INKI_TRANSCRIPT = 12
INKI_PIECES = 2
# A stream is closed and reopened by the browser now and then, so no proxy idles it out.
STREAM_S = 50.0
HEARTBEAT_S = 15.0
_INKI = re.compile(r"(?<![\w@])@inki\b", re.IGNORECASE)
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


class MessageOut(UTCModel):
    id: int
    conversation_id: int
    kind: Literal["text", "call", "inki"]
    text: str
    call: CallOut | None = None
    piece: PieceOut | None = None
    sender: PersonOut | None  # None: Inki
    asked_by: PersonOut | None = None
    created_at: datetime


class ConversationOut(UTCModel):
    id: int
    other: PersonOut
    last: MessageOut | None = None
    unread: int = 0
    last_message_at: datetime


class StartIn(BaseModel):
    user_id: int


class MessageIn(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT)
    call_url: str | None = Field(default=None, max_length=500)
    content_id: int | None = None
    # Chosen by the browser per message, so a retry after a dropped connection is stored once.
    client_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,40}$")

    @field_validator("text")
    @classmethod
    def _trim(cls, text: str) -> str:
        return text.strip()


class ReadIn(BaseModel):
    last_id: int = Field(ge=0)


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


def _when(value: datetime | str) -> datetime:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _row(m: Message) -> dict[str, Any]:
    """A message as stored, for the cache: still sealed."""
    return {"id": m.id, "conversation_id": m.conversation_id, "sender_id": m.sender_id, "asked_by": m.asked_by,
            "kind": m.kind, "sealed": m.sealed, "content_id": m.content_id, "created_at": m.created_at.isoformat()}


async def _render(session: Session, seal: MessageSeal | None, rows: list[dict[str, Any]]) -> list[MessageOut]:
    """Messages as people see them. Without a seal the text and call stay out (they travel sealed, see
    _publish). A piece's title shows only while both people in the conversation may still open it, so a
    tier or clearance change after the message was sent hides it again."""
    convs = {c.id: c for c in (await session.scalars(select(Conversation).where(
        Conversation.id.in_({r["conversation_id"] for r in rows})))).all()}
    ids = {r["sender_id"] for r in rows} | {r["asked_by"] for r in rows} \
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

    out = []
    for r in rows:
        payload = seal.open(r["conversation_id"], r["sealed"]) if seal else {}
        sender, asker = users.get(r["sender_id"]), users.get(r["asked_by"])
        if r["sender_id"] is not None and sender is None:
            continue  # the account is gone; nothing to attribute the message to
        call = (payload or {}).get("call")
        piece = readable(r["conversation_id"], r["content_id"])
        out.append(MessageOut(
            id=r["id"], conversation_id=r["conversation_id"], kind=r["kind"],
            text=(payload or {}).get("text", "") if payload is not None else "This message can't be opened.",
            call=CallOut(**call) if isinstance(call, dict) else None,
            piece=PieceOut(id=piece.id, title=piece.title) if piece else None,
            sender=_person(sender) if sender else None, asked_by=_person(asker) if asker else None,
            created_at=_when(r["created_at"])))
    return out


async def _publish(hub: MessageHub, session: Session, conv: Conversation, message: Message) -> None:
    """The event carries the body still sealed; the stream opens it for the screen it is going to, so the
    text never crosses Redis readable."""
    [out] = await _render(session, None, [_row(message)])
    await hub.publish([conv.creator_id, conv.manager_id],
                      {"type": "message", "message": out.model_dump(mode="json"), "sealed": message.sealed})


def _opened(seal: MessageSeal, event: dict[str, Any]) -> dict[str, Any]:
    sealed = event.pop("sealed", None)
    if event.get("type") == "message" and sealed:
        message = event["message"]
        payload = seal.open(message["conversation_id"], sealed)
        message["text"] = (payload or {}).get("text", "") if payload is not None else "This message can't be opened."
        message["call"] = (payload or {}).get("call")
    return event


async def _store(session: Session, request: Request, conv: Conversation, *, kind: str, payload: dict[str, Any],
                 sender_id: int | None, asked_by: int | None = None, content_id: int | None = None,
                 client_id: str | None = None) -> Message:
    message = Message(conversation_id=conv.id, sender_id=sender_id, asked_by=asked_by, kind=kind,
                      sealed=_seal(request).seal(conv.id, payload), content_id=content_id, client_id=client_id)
    session.add(message)
    # The sender's read position is left alone: a message they write is never unread for them, and what
    # arrived just before it may be something they haven't seen yet.
    conv.last_message_at = utcnow()
    await session.commit()
    await _hub(request).forget_page(conv.id)
    return message


# --- routes -------------------------------------------------------------------------------------------

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
    others = {u.id: u for u in (await session.scalars(select(User).where(User.id.in_(
        {c.manager_id if c.creator_id == user.id else c.creator_id for c in convs})))).all()}
    last_ids = select(func.max(Message.id)).where(Message.conversation_id.in_([c.id for c in convs])) \
        .group_by(Message.conversation_id)
    lasts = {m.conversation_id: m
             for m in (await session.scalars(select(Message).where(Message.id.in_(last_ids)))).all()}
    rendered = {m.conversation_id: m for m in await _render(session, _seal(request), [_row(m) for m in lasts.values()])}
    unread = await _unread_by_conversation(session, user, convs)
    out = []
    for c in convs:
        other = others.get(c.manager_id if c.creator_id == user.id else c.creator_id)
        if other is None:
            continue
        out.append(ConversationOut(id=c.id, other=_person(other), last=rendered.get(c.id),
                                   unread=unread.get(c.id, 0), last_message_at=c.last_message_at))
    return out


async def _unread_by_conversation(session: Session, user: User, convs: list[Conversation]) -> dict[int, int]:
    """Messages after this person's read position that they did not write themselves."""
    counts: dict[int, int] = {}
    for c in convs:
        read = c.creator_read_id if c.creator_id == user.id else c.manager_read_id
        counts[c.id] = int(await session.scalar(select(func.count(Message.id)).where(
            Message.conversation_id == c.id, Message.id > read,
            or_(Message.sender_id.is_(None), Message.sender_id != user.id))) or 0)
    return counts


@router.get("/conversations/unread")
async def unread(session: Session, user: CurrentUser) -> dict[str, int]:
    convs = (await session.scalars(select(Conversation).where(
        or_(Conversation.creator_id == user.id, Conversation.manager_id == user.id)))).all()
    return {"unread": sum((await _unread_by_conversation(session, user, list(convs))).values())}


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def messages(conversation_id: int, request: Request, session: Session, user: CurrentUser,
                   before: Annotated[int | None, Query(ge=1)] = None,
                   after: Annotated[int | None, Query(ge=0)] = None,
                   limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = PAGE) -> list[MessageOut]:
    """Oldest first. No cursor: the newest page. `before`: the page above it. `after`: everything newer than
    what a screen holds (capped), which is how a reconnecting screen catches up."""
    conv = await _mine(session, user, conversation_id)
    hub = _hub(request)
    newest = before is None and after is None and limit <= hub.cache_size
    version = None
    if newest:
        version, cached = await hub.cached_page(conv.id)
        if cached is not None:
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
async def send(conversation_id: int, body: MessageIn, request: Request, session: Session,
               user: CurrentUser) -> MessageOut:
    conv = await _mine(session, user, conversation_id)
    conv_id, user_id, workspace_id = conv.id, user.id, user.workspace_id
    members = [conv.creator_id, conv.manager_id]
    if body.client_id:
        again = await session.scalar(select(Message).where(Message.conversation_id == conv_id,
                                                           Message.client_id == body.client_id))
        if again is not None:  # the same send twice: answer with what was stored the first time
            return (await _render(session, _seal(request), [_row(again)]))[0]
    if not body.text and not body.call_url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "write a message or share a call link")
    call = None
    if body.call_url:
        provider = call_provider(body.call_url.strip())
        if provider is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {
                "message": "Share a meeting link from Google Meet, Microsoft Teams, Zoom, Skype, Jitsi or Whereby "
                           "(it starts with https://)."})
        call = {"url": body.call_url.strip(), "provider": provider}
    if body.text:
        await screened(session, workspace_id=user.workspace_id, actor_id=user.id, text=body.text,
                       where="conversation")
    if body.content_id is not None:
        piece = await session.get(Content, body.content_id)
        creator, manager = await session.get(User, conv.creator_id), await session.get(User, conv.manager_id)
        # Only the creator's own pieces, and only ones both of them may open, so a link never shows either
        # side a title they couldn't already see.
        if piece is None or piece.created_by != conv.creator_id or creator is None or manager is None \
                or not visible(creator, piece) or not visible(manager, piece):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    asks_inki = bool(body.text and _INKI.search(body.text))
    if asks_inki:
        await self_serve_budget(request, session, user)
    try:
        message = await _store(session, request, conv, kind="call" if call else "text",
                               payload={"text": body.text, **({"call": call} if call else {})},
                               sender_id=user.id, content_id=body.content_id, client_id=body.client_id)
    except IntegrityError:  # the same client_id raced itself: the one that landed is the answer
        await session.rollback()
        again = await session.scalar(select(Message).where(Message.conversation_id == conv_id,
                                                           Message.client_id == body.client_id)) \
            if body.client_id else None
        if again is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "the message wasn't stored; send it again") from None
        return (await _render(session, _seal(request), [_row(again)]))[0]
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


@router.post("/conversations/{conversation_id}/read", status_code=204)
async def mark_read(conversation_id: int, body: ReadIn, request: Request, session: Session, user: CurrentUser) -> None:
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


async def _answer(app: Any, conversation_id: int, asked_by: int, question_id: int) -> None:
    hub: MessageHub = app.state.messages
    seal: MessageSeal = app.state.message_seal
    async with app.state.db.sessionmaker() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            return
        rows = list(reversed((await session.scalars(select(Message).where(
            Message.conversation_id == conv.id, Message.id <= question_id)
            .order_by(Message.id.desc()).limit(INKI_TRANSCRIPT + 1))).all()))
        names = {conv.creator_id: "Creator", conv.manager_id: "Brand team"}
        transcript = []
        for m in rows:
            payload = seal.open(conv.id, m.sealed) or {}
            call = payload.get("call")
            text = payload.get("text") or (f"(shared a {call['provider']} link)" if call else "")
            if text:
                transcript.append(("Inki" if m.sender_id is None else names.get(m.sender_id, "Someone"), text))
        # The pieces this conversation has pointed at, newest first; the question's own piece leads.
        linked = [m.content_id for m in reversed(rows) if m.content_id]
        older = (await session.scalars(select(Message.content_id).where(
            Message.conversation_id == conv.id, Message.content_id.is_not(None))
            .order_by(Message.id.desc()).limit(20))).all()
        creator, manager = await session.get(User, conv.creator_id), await session.get(User, conv.manager_id)
        redactor = await workspace_redactor(session, conv.workspace_id)
        piece_ids, pieces = [], []
        for pid in dict.fromkeys(linked + list(older)):
            piece = await session.get(Content, pid)
            if piece and creator and manager and visible(creator, piece) and visible(manager, piece):
                piece_ids.append(pid)
                pieces.append({"title": piece.title, **await _detail(session, pid, redactor)})
            if len(piece_ids) == INKI_PIECES:
                break
        await session.commit()  # no transaction held across the model call
        task = InkiTask(transcript=transcript, pieces=pieces)
        _, llm, _, _ = app.state.prism.guarded_providers(redactor)
        try:
            reply = (await llm.run(task)).reply.strip()
        except Exception:  # noqa: BLE001 - a model failure answers from the record, and says so
            log.warning("inki reply fell back to the record", exc_info=True)
            reply = task.heuristic().reply
        message = Message(conversation_id=conv.id, sender_id=None, asked_by=asked_by, kind="inki",
                          sealed=seal.seal(conv.id, {"text": reply or task.heuristic().reply}),
                          content_id=piece_ids[0] if piece_ids else None)
        session.add(message)
        conv.last_message_at = utcnow()
        await session.commit()
        await hub.forget_page(conv.id)
        await _publish(hub, session, conv, message)
