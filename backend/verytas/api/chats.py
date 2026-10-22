"""Ask Verytas conversation history, private to each person.

The answers themselves come from the web app's model route; this only keeps
the threads so a person can return to them from any browser. Threads are
never shared: another user, even an admin, gets a 404.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from verytas.api.deps import CurrentUser, Session
from verytas.models import ChatThread, utcnow
from verytas.schemas import UTCModel

router = APIRouter(tags=["chats"])

MAX_THREADS_LISTED = 100
MAX_MESSAGES = 200
MAX_CHARS = 20_000
MAX_IMAGES = 4
# A downscaled image as a data URL; the browser resizes before attaching.
MAX_IMAGE_CHARS = 600_000
_IMAGE_PREFIXES = ("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_CHARS)
    images: list[str] = Field(default_factory=list, max_length=MAX_IMAGES)

    @field_validator("images")
    @classmethod
    def _images(cls, images: list[str]) -> list[str]:
        for img in images:
            if not img.startswith(_IMAGE_PREFIXES) or len(img) > MAX_IMAGE_CHARS:
                raise ValueError("images must be PNG, JPEG or WebP data URLs under 600 KB")
        return images


class ThreadIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(max_length=MAX_MESSAGES)


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
    thread = ChatThread(workspace_id=user.workspace_id, user_id=user.id, title=body.title.strip(),
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
    thread.title = body.title.strip()
    thread.messages = [m.model_dump() for m in body.messages]
    thread.updated_at = utcnow()
    await session.commit()
    return thread


@router.delete("/chats/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: int, session: Session, user: CurrentUser) -> None:
    await session.delete(await _own(session, user, thread_id))
    await session.commit()
