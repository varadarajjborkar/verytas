"""Uploads and the intake precheck.

POST /media stores a file (any supported type, sniffed from its bytes) and
returns an id that versions reference. POST /contents/precheck profiles a
draft before it is submitted, so the creator sees irregularities (a 300-page
PDF, a 40 MP image, invisible characters in the caption) while uploading,
not after a long scan. Submission enforces the same profile server-side.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select

from verytas.api.deps import CurrentUser, Session, require
from verytas.media import profile as prof
from verytas.media.files import UNSUPPORTED_IMAGES, MediaError, decode_b64, limit_for, pdf_active_content, sniff
from verytas.models import MediaBlob, Role, User
from verytas.schemas import MediaOut, PrecheckIn

router = APIRouter(tags=["media"])
Writer = Annotated[User, Depends(require(Role.creator, Role.reviewer, Role.approver, Role.brand_admin))]
_ACCEPTED = ("image/", "video/", "application/pdf", "application/vnd.openxmlformats-officedocument")
# Uploads are read whole into memory once, so cap the request before reading.
_UPLOAD_CAP = 150 * 1024 * 1024


@router.post("/media", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def upload(session: Session, user: Writer, file: Annotated[UploadFile, File()]) -> MediaOut:
    raw = await file.read(_UPLOAD_CAP + 1)
    if len(raw) > _UPLOAD_CAP:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file is over 150 MB")
    kind = sniff(raw)
    if kind in UNSUPPORTED_IMAGES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"{kind.split('/')[1].upper()} images can't be read yet; export as JPEG or PNG")
    if not kind.startswith(_ACCEPTED):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"unsupported file type ({kind}); use an image, video, PDF or Word file")
    if len(raw) > limit_for(kind):
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"{kind} files are limited to {limit_for(kind) // 1024 // 1024} MB")
    digest = hashlib.sha256(raw).hexdigest()
    blob = MediaBlob(id=uuid.uuid4().hex, workspace_id=user.workspace_id, media_type=kind,
                     name=(file.filename or "")[:200] or None, size=len(raw), sha256=digest, data=raw,
                     created_by=user.id)
    session.add(blob)
    await session.commit()
    metrics = await asyncio.to_thread(_metrics, kind, raw)
    return MediaOut(id=blob.id, media_type=kind, name=blob.name, bytes=len(raw), sha256=digest, metrics=metrics)


def _metrics(kind: str, raw: bytes) -> dict[str, Any]:
    try:
        if kind.startswith("video/"):
            from verytas.media.video import probe

            return probe(raw)
        if kind == "application/pdf":
            return {"pages": _pdf_pages(raw), "active_content": pdf_active_content(raw)}
    except MediaError as exc:
        return {"error": str(exc)}
    return {}


def _pdf_pages(raw: bytes) -> int | None:
    import pypdfium2 as pdfium

    from verytas.media.documents import _PDFIUM

    with _PDFIUM:
        try:
            pdf = pdfium.PdfDocument(raw)
        except pdfium.PdfiumError:
            return None
        try:
            return len(pdf)
        finally:
            pdf.close()


async def load_blobs(session, workspace_id: int, ids: set[str]) -> dict[str, MediaBlob]:
    if not ids:
        return {}
    rows = (await session.scalars(
        select(MediaBlob).where(MediaBlob.id.in_(ids), MediaBlob.workspace_id == workspace_id))).all()
    found = {b.id: b for b in rows}
    missing = ids - set(found)
    if missing:
        # Another workspace's id reads as missing too: no cross-tenant probing.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown media id(s): {sorted(missing)}")
    return found


def blob_ids(attachments: dict[str, Any]) -> set[str]:
    ids = set()
    for key in ("images", "documents", "videos"):
        ids |= {a["blob_id"] for a in attachments.get(key, []) if a.get("blob_id")}
    return ids


async def build_profile(session, user: User, channel: str, body: str, attachments: dict[str, Any]) -> prof.Profile:
    blobs = await load_blobs(session, user.workspace_id, blob_ids(attachments))
    return await asyncio.to_thread(_profile, channel, body, attachments, {k: v.data for k, v in blobs.items()})


def _profile(channel: str, body: str, attachments: dict[str, Any], blobs: dict[str, bytes]) -> prof.Profile:
    p = prof.Profile(channel)
    prof.profile_text(p, body)

    def payload(item: dict[str, Any], limit: int) -> bytes | None:
        if item.get("blob_id"):
            return blobs.get(item["blob_id"])
        if item.get("data_base64"):
            try:
                return decode_b64(item["data_base64"], limit)
            except MediaError:
                return None
        return None

    for img in attachments.get("images", []):
        raw = payload(img, 8 * 1024 * 1024)
        if raw:
            prof.profile_image(p, str(img.get("id")), raw)
    for doc in attachments.get("documents", []):
        raw = payload(doc, 20 * 1024 * 1024)
        if not raw:
            continue
        kind = sniff(raw)
        pages = _pdf_pages(raw) if kind == "application/pdf" else None
        flags = pdf_active_content(raw) if kind == "application/pdf" else []
        prof.profile_document(p, str(doc.get("name") or doc.get("id")), raw, pages, flags)
    for vid in attachments.get("videos", []):
        raw = payload(vid, 150 * 1024 * 1024)
        if not raw:
            continue
        try:
            from verytas.media.video import probe

            prof.profile_video(p, str(vid.get("name") or vid.get("id")), probe(raw))
        except MediaError as exc:
            p.irregularities.append(prof.Irregularity("video_unreadable", f"video {vid.get('id')}", str(exc),
                                                      "a playable video", "it cannot be checked"))
    prof.profile_counts(p)
    return p


@router.post("/contents/precheck")
async def precheck(body: PrecheckIn, session: Session, user: CurrentUser) -> dict[str, Any]:
    attachments = body.attachments.model_dump(exclude_none=True)
    p = await build_profile(session, user, body.channel, body.body, attachments)
    out = p.as_dict()
    out["needs_reason"] = bool(p.irregularities)
    return out
