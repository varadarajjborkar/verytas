"""Prism Intake API: hand over material, see what was understood, answer what was asked, approve drafts.

Brand admins only. Uploads go through the same quotas as content uploads; a batch is read in the
background (intake/pipeline.py); approving a draft creates it through the library's own endpoint, so an
intake rule, fact, codename or asset passes exactly the checks, limits and audit entry of one added by
hand. Nothing reaches the library any other way.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import uuid
from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import func, select, update

from verytas.api.accounts import SelfServeBudget
from verytas.api.deps import PrismDep, Session, can_read, require
from verytas.api.knowledge import create_asset, create_fact, create_rule, create_term
from verytas.intake import fetch as live
from verytas.intake import pipeline, readers
from verytas.media.files import UNSUPPORTED_IMAGES, limit_for, sniff
from verytas.media.storage import over_quota, reclaim_orphans, usage, workspace_lock
from verytas.models import IntakeBatch, IntakeDraft, IntakeItem, MediaBlob, Role, Rule, RuleStatus, Tier, User, utcnow
from verytas.schemas import BrandAssetIn, FactIn, RuleIn, TermIn
from verytas.security.audit import append

router = APIRouter(tags=["intake"])
Admin = Annotated[User, Depends(require(Role.brand_admin))]
MAX_ITEMS = 25
_UPLOAD_CAP = 150 * 1024 * 1024
_DATA_CAP = 20 * 1024 * 1024  # sheets, CSV, JSON and text
_OFFICE = (readers.XLSX, readers.PPTX, readers.DOCX)


class IntakeFileOut(BaseModel):
    id: str
    name: str | None
    media_type: str
    bytes: int


@router.post("/intake/files", response_model=IntakeFileOut, status_code=status.HTTP_201_CREATED)
async def upload(request: Request, session: Session, admin: Admin,
                 file: Annotated[UploadFile, File()]) -> IntakeFileOut:
    """Any file a company keeps its brand in: documents, slides, sheets, CSV, JSON, text, images, video, audio."""
    raw = await file.read(_UPLOAD_CAP + 1)
    if len(raw) > _UPLOAD_CAP:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file is over 150 MB")
    kind = readers.office_kind(raw) or sniff(raw)
    if kind == "unknown":
        kind = readers.sniff_text(raw) or "unknown"
    if kind in UNSUPPORTED_IMAGES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"{kind.split('/')[1].upper()} images can't be read yet; export as JPEG or PNG")
    if kind == "unknown":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "unsupported file; use PDF, Word, PowerPoint, Excel, CSV, JSON, text, an image, a video "
                            "or audio (for a database or SAP, export a table or give a read-only link)")
    cap = _DATA_CAP if kind.startswith(("text/", "application/json")) or kind in (readers.XLSX, readers.PPTX) \
        else limit_for(kind)
    if len(raw) > cap:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"{kind} files are limited to {cap // 1024 // 1024} MB")
    settings = request.app.state.settings
    limits = {"user_mb": settings.upload_quota_user_mb, "workspace_mb": settings.upload_quota_workspace_mb}
    async with workspace_lock(admin.workspace_id):
        if over_quota(await usage(session, admin.workspace_id, admin.id), len(raw), **limits):
            await reclaim_orphans(session, older_than=timedelta(hours=settings.orphan_upload_ttl_h),
                                  workspace_id=admin.workspace_id)
            if reason := over_quota(await usage(session, admin.workspace_id, admin.id), len(raw), **limits):
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, reason)
        blob = MediaBlob(id=uuid.uuid4().hex, workspace_id=admin.workspace_id, media_type=kind,
                         name=(file.filename or "")[:200] or None, size=len(raw),
                         sha256=hashlib.sha256(raw).hexdigest(), data=raw, created_by=admin.id)
        session.add(blob)
        await session.commit()
    return IntakeFileOut(id=blob.id, name=blob.name, media_type=kind, bytes=len(raw))


class ItemIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    blob_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    url: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=200_000)
    context: str | None = Field(default=None, max_length=4000, description="What this item is, in the admin's words")

    @model_validator(mode="after")
    def one_source(self) -> ItemIn:
        if sum(x is not None for x in (self.blob_id, self.url, self.text)) != 1:
            raise ValueError("give exactly one of blob_id, url or text")
        if self.url is not None:
            try:
                live.check_url(self.url)
            except live.FetchRefused as exc:
                raise ValueError(str(exc)) from None
        return self


class BatchIn(BaseModel):
    note: str | None = Field(default=None, max_length=4000, description="What the material is, for every item")
    tier: Tier = Tier.internal
    items: list[ItemIn] = Field(min_length=1, max_length=MAX_ITEMS)


@router.post("/intake", status_code=status.HTTP_201_CREATED, dependencies=[SelfServeBudget])
async def start(body: BatchIn, session: Session, admin: Admin, prism: PrismDep) -> dict:
    if not can_read(admin, body.tier):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "material above your clearance can't be filed by you")
    blob_ids = [i.blob_id for i in body.items if i.blob_id]
    if blob_ids:
        found = {b.id: b for b in (await session.scalars(select(MediaBlob).where(MediaBlob.id.in_(blob_ids)))).all()}
        if any(found.get(b) is None or found[b].workspace_id != admin.workspace_id for b in blob_ids):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "upload not found")
    else:
        found = {}
    batch = IntakeBatch(workspace_id=admin.workspace_id, created_by=admin.id, note=body.note, tier=body.tier)
    session.add(batch)
    await session.flush()
    for i, it in enumerate(body.items):
        name = it.name or (found[it.blob_id].name if it.blob_id and found[it.blob_id].name else None) \
            or (_link_name(it.url) if it.url else None) or f"Pasted text {i + 1}"
        if it.url and name == it.name:
            name = name.split("?", 1)[0].split("#", 1)[0] or _link_name(it.url)
        session.add(IntakeItem(batch_id=batch.id, workspace_id=admin.workspace_id, name=name[:200],
                               blob_id=it.blob_id, source_url=it.url, text=it.text, context=it.context))
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="intake.started",
                 object_type="intake_batch", object_id=batch.id,
                 detail={"items": len(body.items), "tier": body.tier.value,
                         "links": sum(bool(i.url) for i in body.items)})
    await session.commit()
    prism.schedule_job(lambda: pipeline.run_batch(prism, batch.id))
    return {"id": batch.id, "status": batch.status}


def _link_name(url: str) -> str:
    """A link's last path segment, never its query: read-only links are often signed with a key there."""
    return pipeline.public_source(url).rstrip("/").rsplit("/", 1)[-1][:200] or "Linked source"


def _batch_out(b: IntakeBatch) -> dict:
    return {"id": b.id, "note": b.note, "tier": b.tier.value, "status": b.status, "summary": b.summary,
            "created_at": b.created_at, "finished_at": b.finished_at}


def _item_out(i: IntakeItem) -> dict:
    return {"id": i.id, "name": i.name, "media_type": i.media_type, "source_url": i.source_url, "context": i.context,
            "status": i.status, "kind": i.kind, "purpose": i.purpose, "confidence": i.confidence,
            "questions": i.questions, "reading": i.reading, "issues": i.issues, "model": i.model, "error": i.error,
            "refreshed_at": i.refreshed_at}


def _draft_out(d: IntakeDraft) -> dict:
    return {"id": d.id, "item_id": d.item_id, "target": d.target, "payload": d.payload, "provenance": d.provenance,
            "confidence": d.confidence, "issues": d.issues, "status": d.status, "created_object": d.created_object}


async def _batch(session, admin: User, batch_id: int) -> IntakeBatch:
    b = await session.get(IntakeBatch, batch_id)
    if b is None or b.workspace_id != admin.workspace_id or not can_read(admin, b.tier):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "intake not found")
    return b


@router.get("/intake")
async def batches(session: Session, admin: Admin) -> list[dict]:
    rows = (await session.scalars(select(IntakeBatch).where(IntakeBatch.workspace_id == admin.workspace_id)
                                  .order_by(IntakeBatch.id.desc()).limit(50))).all()
    return [_batch_out(b) for b in rows if can_read(admin, b.tier)]


@router.get("/intake/{batch_id}")
async def batch(batch_id: int, session: Session, admin: Admin) -> dict:
    b = await _batch(session, admin, batch_id)
    items = (await session.scalars(select(IntakeItem).where(IntakeItem.batch_id == b.id).order_by(IntakeItem.id))).all()
    drafts = (await session.scalars(select(IntakeDraft).where(IntakeDraft.item_id.in_([i.id for i in items]))
                                    .order_by(IntakeDraft.id))).all() if items else []
    return _batch_out(b) | {"items": [_item_out(i) for i in items], "drafts": [_draft_out(d) for d in drafts]}


async def _item(session, admin: User, item_id: int) -> IntakeItem:
    i = await session.get(IntakeItem, item_id)
    if i is None or i.workspace_id != admin.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "intake item not found")
    await _batch(session, admin, i.batch_id)
    return i


class AnswerIn(BaseModel):
    context: str = Field(min_length=2, max_length=4000)


@router.post("/intake/items/{item_id}/answer", dependencies=[SelfServeBudget])
async def answer(item_id: int, body: AnswerIn, session: Session, admin: Admin, prism: PrismDep) -> dict:
    """The admin's answer to an item's questions, or more context on it: the item is understood again."""
    item = await _item(session, admin, item_id)
    _idle(item)
    # The newest answer matters most, so a long history is cut from the front.
    item.context = "\n".join(x for x in (item.context, body.context.strip()) if x)[-8000:]
    item.status, item.questions = "queued", []
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="intake.answered",
                 object_type="intake_item", object_id=item.id, detail={"chars": len(body.context)})
    await session.commit()
    batch_id = item.batch_id
    prism.schedule_job(lambda: pipeline.rerun_item(prism, item_id, batch_id))
    return _item_out(item)


def _idle(item: IntakeItem) -> None:
    # Two runs of one item would each clear the other's drafts and add their own: one at a time.
    if item.status in ("queued", "reading"):
        raise HTTPException(status.HTTP_409_CONFLICT, "this item is still being read; wait for it to finish")


@router.post("/intake/items/{item_id}/refresh", dependencies=[SelfServeBudget])
async def refresh(item_id: int, session: Session, admin: Admin, prism: PrismDep) -> dict:
    """A live source read again. What changed comes back as new pending drafts; a value that moved from an
    approved fact is flagged as replacing it, never changed in place."""
    item = await _item(session, admin, item_id)
    if not item.source_url:
        raise HTTPException(status.HTTP_409_CONFLICT, "only a linked source can be refreshed")
    _idle(item)
    item.status = "queued"
    await session.commit()
    batch_id = item.batch_id
    prism.schedule_job(lambda: pipeline.rerun_item(prism, item_id, batch_id))
    return _item_out(item)


class DecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    payload: dict[str, Any] | None = Field(default=None, description="The draft as edited by the admin")


async def _apply(session, admin: User, d: IntakeDraft, payload: dict[str, Any]) -> str:
    """Creates the draft through the library's own endpoint. Returns "fact:12" and the like."""
    if d.target == "rule":
        body = RuleIn.model_validate(payload)
        # Codes are given when the draft is made; another approval since may have taken this one.
        taken = set((await session.scalars(select(Rule.code).where(Rule.workspace_id == admin.workspace_id))).all())
        if body.code in taken:
            stem, n = body.code.rsplit("-", 1)[0], 1
            while f"{stem}-{n}" in taken:
                n += 1
            body.code = payload["code"] = f"{stem}-{n}"
        rule = await create_rule(body, session, admin)
        rule.status = RuleStatus.active
        await session.commit()
        return f"rule:{rule.id}"
    if d.target == "fact":
        body = FactIn.model_validate(payload)
        supersedes = next((i.get("supersedes") for i in d.issues if i.get("supersedes")), None)
        if supersedes and body.supersedes_id is None:
            body.supersedes_id = supersedes
        fact = await create_fact(body, session, admin)
        return f"fact:{fact.id}"
    if d.target == "term":
        term = await create_term(TermIn.model_validate(payload), session, admin)
        return f"term:{term.id}"
    if d.target == "asset":
        item = await session.get(IntakeItem, d.item_id)
        index = payload.get("image", d.payload.get("image", 0))
        if not isinstance(index, int) or isinstance(index, bool):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "image must be the picture's number")
        png = await _picture(session, item, index)
        body = BrandAssetIn.model_validate({k: v for k, v in payload.items() if k != "image"}
                                           | {"media_type": "image/png", "data_base64": base64.b64encode(png).decode()})
        asset = await create_asset(body, session, admin)
        return f"asset:{asset.id}"
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown draft type {d.target}")


async def _picture(session, item: IntakeItem, index: int) -> bytes:
    """The item's picture, read again from its file: drafts keep an index, not a copy of the image."""
    blob = await session.get(MediaBlob, item.blob_id) if item.blob_id else None
    if blob is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the file this picture came from is gone; upload it again")
    reading = await asyncio.to_thread(readers.read, bytes(blob.data), blob.media_type, item.name)
    if not 0 <= index < len(reading.images):
        raise HTTPException(status.HTTP_409_CONFLICT, "that picture is no longer in the file")
    return reading.images[index]


async def _decide(session, admin: User, d: IntakeDraft, body: DecisionIn) -> dict:
    draft_id = d.id
    # Claimed before anything is created, in its own commit: a double click or a retry finds it taken
    # and creates nothing a second time.
    claimed = await session.execute(update(IntakeDraft).where(IntakeDraft.id == draft_id,
                                                              IntakeDraft.status == "pending")
                                    .values(status="applying"))
    await session.commit()
    if claimed.rowcount != 1:
        await session.refresh(d)
        raise HTTPException(status.HTTP_409_CONFLICT, f"this draft is already {d.status}")
    if body.action == "approve":
        payload = d.payload if body.payload is None else {**d.payload, **body.payload}
        try:
            try:
                d.created_object = await _apply(session, admin, d, payload)
            except ValidationError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors()[0]["msg"]) from None
        except HTTPException:
            # Refused by the library: nothing was created, so the draft goes back to waiting for a person.
            await session.rollback()
            await session.execute(update(IntakeDraft).where(IntakeDraft.id == draft_id).values(status="pending"))
            await session.commit()
            raise
        d.payload = payload
    d.status = "approved" if body.action == "approve" else "rejected"
    d.decided_by, d.decided_at = admin.id, utcnow()
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action=f"intake.{d.status}",
                 object_type="intake_draft", object_id=d.id, detail={"target": d.target, "created": d.created_object})
    await session.commit()
    return _draft_out(d)


@router.post("/intake/drafts/{draft_id}")
async def decide(draft_id: int, body: DecisionIn, session: Session, admin: Admin) -> dict:
    d = await session.get(IntakeDraft, draft_id)
    if d is None or d.workspace_id != admin.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    await _item(session, admin, d.item_id)
    return await _decide(session, admin, d, body)


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: Literal["approve", "reject"] = "approve"


@router.post("/intake/{batch_id}/decide")
async def decide_many(batch_id: int, body: BulkIn, session: Session, admin: Admin) -> dict:
    """Many drafts at once. Approving in bulk skips any draft with something to check (a conflict, an open
    question, no unit): those need a person to look, one at a time."""
    b = await _batch(session, admin, batch_id)
    items = set((await session.scalars(select(IntakeItem.id).where(IntakeItem.batch_id == b.id))).all())
    drafts = (await session.scalars(select(IntakeDraft).where(IntakeDraft.id.in_(body.ids)))).all()
    # Plain values up front: a refused draft rolls the session back, which expires every loaded object.
    todo = [(d.id, d.item_id in items and d.status == "pending" and not (body.action == "approve" and d.issues))
            for d in drafts]
    admin_id = admin.id
    done, skipped = [], []
    for draft_id, ok in todo:
        if not ok:
            skipped.append(draft_id)
            continue
        admin = await session.get(User, admin_id)
        d = await session.get(IntakeDraft, draft_id)
        try:
            done.append((await _decide(session, admin, d, DecisionIn(action=body.action)))["id"])
        except HTTPException as exc:
            skipped.append(draft_id)
            d = await session.get(IntakeDraft, draft_id)
            d.issues = [*d.issues, {"kind": "rejected_by_library", "detail": str(exc.detail)[:300]}]
            await session.commit()
    pending = await session.scalar(select(func.count()).select_from(IntakeDraft).where(
        IntakeDraft.item_id.in_(items), IntakeDraft.status == "pending"))
    return {"done": done, "skipped": skipped, "pending": pending}
