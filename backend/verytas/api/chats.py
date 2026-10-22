"""Ask Verytas conversation history, private to each person.

The answers themselves come from the web app's model route; this only keeps
the threads so a person can return to them from any browser. Threads are
never shared: another user, even an admin, gets a 404.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select

from verytas.api.deps import CurrentUser, Session
from verytas.models import ChatThread, utcnow
from verytas.schemas import UTCModel

router = APIRouter(tags=["chats"])

MAX_THREADS_LISTED = 100
MAX_THREADS = 500
MAX_MESSAGES = 200
MAX_CHARS = 20_000
MAX_IMAGES = 4
# A downscaled image as a data URL; the browser resizes before attaching.
MAX_IMAGE_CHARS = 600_000
# Per thread, so a long conversation can't grow into hundreds of megabytes of images.
MAX_THREAD_CHARS = 8_000_000
_MAGIC = {"data:image/png;base64,": (b"\x89PNG\r\n\x1a\n",), "data:image/jpeg;base64,": (b"\xff\xd8\xff",),
          "data:image/webp;base64,": (b"RIFF",)}


def _valid_image(url: str) -> bool:
    prefix = next((p for p in _MAGIC if url.startswith(p)), None)
    if prefix is None or len(url) > MAX_IMAGE_CHARS:
        return False
    try:
        raw = base64.b64decode(url[len(prefix):], validate=True)
    except (binascii.Error, ValueError):
        return False
    if prefix.startswith("data:image/webp") and raw[8:12] != b"WEBP":
        return False
    return raw.startswith(_MAGIC[prefix])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_CHARS)
    images: list[str] = Field(default_factory=list, max_length=MAX_IMAGES)

    @field_validator("images")
    @classmethod
    def _images(cls, images: list[str]) -> list[str]:
        for img in images:
            if not _valid_image(img):
                raise ValueError("images must be PNG, JPEG or WebP data URLs under 600 KB")
        return images


class ThreadIn(BaseModel):
    title: str = Field(max_length=200)
    messages: list[ChatMessage] = Field(max_length=MAX_MESSAGES)

    @field_validator("title")
    @classmethod
    def _title(cls, title: str) -> str:
        title = title.strip()
        if not title:
            raise ValueError("title must not be blank")
        return title

    @model_validator(mode="after")
    def _size(self) -> ThreadIn:
        if sum(len(m.content) + sum(map(len, m.images)) for m in self.messages) > MAX_THREAD_CHARS:
            raise ValueError("this conversation is too large to save; start a new one")
        return self


class ThreadSummary(UTCModel):
    id: int
    title: str
    updated_at: datetime


class ThreadOut(ThreadSummary):
    messages: list[dict[str, Any]]


async def _own(session: Session, user: CurrentUser, thread_id: int) -> ChatThread:
    thread = await session.get(ChatThread, thread_id)
    if thread is None or thread.user_id != user.id or thread.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    return thread


@router.get("/chats", response_model=list[ThreadSummary])
async def list_threads(session: Session, user: CurrentUser) -> list[ChatThread]:
    rows = await session.scalars(
        select(ChatThread).where(ChatThread.user_id == user.id, ChatThread.workspace_id == user.workspace_id)
        .order_by(ChatThread.updated_at.desc()).limit(MAX_THREADS_LISTED))
    return list(rows)


@router.post("/chats", response_model=ThreadOut, status_code=status.HTTP_201_CREATED)
async def create_thread(body: ThreadIn, session: Session, user: CurrentUser) -> ChatThread:
    held = await session.scalar(select(func.count()).select_from(ChatThread).where(
        ChatThread.user_id == user.id, ChatThread.workspace_id == user.workspace_id))
    if (held or 0) >= MAX_THREADS:
        raise HTTPException(status.HTTP_409_CONFLICT, "too many saved conversations; delete some old ones first")
    thread = ChatThread(workspace_id=user.workspace_id, user_id=user.id, title=body.title,
                        messages=[m.model_dump() for m in body.messages])
    session.add(thread)
    await session.commit()
    return thread


@router.get("/chats/{thread_id}", response_model=ThreadOut)
async def get_thread(thread_id: int, session: Session, user: CurrentUser) -> ChatThread:
    return await _own(session, user, thread_id)


@router.put("/chats/{thread_id}", response_model=ThreadOut)
async def replace_thread(thread_id: int, body: ThreadIn, session: Session, user: CurrentUser) -> ChatThread:
    thread = await _own(session, user, thread_id)
    thread.title = body.title
    thread.messages = [m.model_dump() for m in body.messages]
    thread.updated_at = utcnow()
    await session.commit()
    return thread


@router.delete("/chats/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: int, session: Session, user: CurrentUser) -> None:
    await session.delete(await _own(session, user, thread_id))
    await session.commit()
