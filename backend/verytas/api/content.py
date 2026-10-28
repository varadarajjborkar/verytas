"""Content lifecycle: submit, review, decide, apply fixes, approve."""

from __future__ import annotations

import asyncio
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer, selectinload

from verytas.api.accounts import SelfServeBudget
from verytas.api.deps import CurrentUser, PrismDep, Session, can_read, require
from verytas.api.media import build_profile, load_blobs
from verytas.media import preview, serve
from verytas.media.files import DOCX, MAX_HTML_BYTES, MediaError, sniff
from verytas.models import (
    BrandEvent,
    Change,
    Comment,
    Content,
    ContentStatus,
    ContentVersion,
    Decision,
    DecisionAction,
    Dispute,
    Escalation,
    EventImpact,
    Finding,
    Level,
    MediaBlob,
    Review,
    ReviewStatus,
    Role,
    User,
    WorkflowEvent,
)
from verytas.prism import disputes as dispute_engine
from verytas.prism.orchestrator import finding_payload
from verytas.schemas import (
    AiEditIn,
    AiEditOut,
    CitationOut,
    CommentIn,
    CommentOut,
    ContentDetail,
    ContentIn,
    ContentListItem,
    ContentOut,
    DecisionIn,
    DecisionOut,
    DisputeIn,
    DisputeOut,
    FindingOut,
    LatestReview,
    ResubmitIn,
    ResubmitOut,
    ReviewOut,
    SubmitOut,
    TransitionIn,
    VersionIn,
    VersionOut,
)
from verytas.security.audit import append
from verytas.services.contacts import screened

log = logging.getLogger("verytas.api.content")
router = APIRouter(tags=["content"])
OVERRIDE_NOTE_MIN = 10
Writer = Annotated[User, Depends(require(Role.creator, Role.reviewer, Role.approver))]
Reviewer = Annotated[User, Depends(require(Role.creator, Role.reviewer, Role.approver))]

S = ContentStatus
# (from, to) -> roles allowed. Brand admins are always allowed (see `require`).
_TRANSITIONS: dict[tuple[ContentStatus, ContentStatus], set[Role]] = {
    (S.draft, S.in_review): {Role.creator, Role.reviewer, Role.approver},
    (S.changes_requested, S.in_review): {Role.creator, Role.reviewer, Role.approver},
    (S.in_review, S.changes_requested): {Role.reviewer, Role.approver},
    (S.in_review, S.approved): {Role.approver},
    (S.approved, S.changes_requested): {Role.approver},
    (S.approved, S.published): {Role.approver},
}


async def _content(session, user: User, content_id: int, *, with_versions: bool = False) -> Content:
    q = select(Content).where(Content.id == content_id)
    if with_versions:
        q = q.options(selectinload(Content.versions))
    content = await session.scalar(q)
    # Same 404 for "missing", "above your clearance" and "another creator's", so nothing leaks.
    if content is None or not visible(user, content):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    return content


def visible(user: User, content: Content) -> bool:
    """Creators see their own pieces only: one brand team, many creators, and a creator's drafts are
    nobody else's business but the team's. The brand team sees everything its clearance allows."""
    if content.workspace_id != user.workspace_id or not can_read(user, content.tier):
        return False
    return user.role is not Role.creator or content.created_by == user.id


async def _readable_finding(session, user: User, finding_id: int, *options) -> tuple[Finding, Content]:
    """A finding and its content, with one 404 for missing, another workspace's and above clearance,
    so finding ids can't be probed across tenants or tiers."""
    finding = await session.scalar(select(Finding).options(*options).where(Finding.id == finding_id))
    if finding is not None:
        review = await session.get(Review, finding.review_id)
        version = await session.get(ContentVersion, review.version_id)
        content = await session.get(Content, version.content_id)
        if visible(user, content):
            return finding, content
    raise HTTPException(status.HTTP_404_NOT_FOUND, "finding not found")


async def _latest_review(session, content_id: int) -> Review | None:
    return await session.scalar(
        select(Review).join(ContentVersion, Review.version_id == ContentVersion.id)
        .where(ContentVersion.content_id == content_id).order_by(Review.id.desc()).limit(1)
    )


async def _start_review(session, prism, version: ContentVersion, wait: bool) -> int:
    review = Review(version_id=version.id)
    session.add(review)
    await session.commit()
    if wait:
        await prism.run(review.id)
    else:
        prism.schedule(review.id)
    return review.id


IRREGULARITY_NOTE_MIN = 15
BRIEF_MIN = 20


async def _intake(session, user: User, channel: str, body: str, attachments: dict,
                  notes: dict, *, brief_required: bool = True) -> dict:
    """Profile the upload; an irregular one needs the creator's reason before it is accepted.

    Not a block: with a reason it goes ahead and is scanned in full, and the
    irregularity is scored as a finding (orchestrator). Without one, the
    creator gets the list of what looks off and what was expected.
    """
    # A video is checked frame by frame; the creator's own account of what is in it tells the review what
    # to look for and gives it claims to verify, so a video doesn't go in without one.
    if brief_required and attachments.get("videos") and len((notes.get("brief") or "").strip()) < BRIEF_MIN \
            and not notes.get("brief_audio_blob_id"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={
            "code": "brief_required",
            "message": "A video needs a short brief: in your own words (or a voice note), what is in it: the "
                       "characters, people and products, and roughly when they appear (creator_notes.brief, at "
                       f"least {BRIEF_MIN} characters).",
        })
    if notes.get("brief_audio_blob_id"):
        await load_blobs(session, user.workspace_id, {notes["brief_audio_blob_id"]})
    p = await build_profile(session, user, channel, body, attachments)
    reason = (notes.get("irregularity") or "").strip()
    if p.irregularities and len(reason) < IRREGULARITY_NOTE_MIN:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={
            "message": f"This upload is unusual for {channel}. Say briefly why it is this way "
                       f"(creator_notes.irregularity, at least {IRREGULARITY_NOTE_MIN} characters) and it will be "
                       "checked in full; the irregularity still counts against its score.",
            "irregularities": p.as_dict()["irregularities"],
        })
    return p.as_dict()


@router.post("/contents", response_model=SubmitOut, status_code=status.HTTP_201_CREATED, dependencies=[SelfServeBudget])
async def create_content(body: ContentIn, session: Session, user: Writer, prism: PrismDep,
                         wait: bool = False) -> SubmitOut:
    """Create a draft and start the automated pre-check. `wait=true` returns after the review finishes."""
    if not can_read(user, body.tier):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you cannot create content above your clearance")
    if body.event_id is not None:
        event = await session.get(BrandEvent, body.event_id)
        if event is None or event.workspace_id != user.workspace_id or event.status != "active" \
                or not can_read(user, event.tier):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "that event doesn't exist or was cancelled")
    attachments = body.attachments.model_dump(exclude_none=True)
    notes = body.creator_notes.model_dump(exclude_none=True)
    attachments["profile"] = await _intake(session, user, body.channel, body.body, attachments, notes)
    content = Content(workspace_id=user.workspace_id, title=body.title, channel=body.channel, tier=body.tier,
                      created_by=user.id, event_id=body.event_id)
    session.add(content)
    await session.flush()
    version = ContentVersion(content_id=content.id, version_no=1, body=body.body,
                             attachments=attachments, creator_notes=notes, created_by=user.id)
    session.add(version)
    await session.flush()
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="content.created",
                 object_type="content", object_id=content.id, detail={"tier": body.tier, "channel": body.channel})
    review_id = await _start_review(session, prism, version, wait)
    return SubmitOut(content=ContentOut.model_validate(content), version=VersionOut.model_validate(version),
                     review_id=review_id)



def _splice(text: str, edits: list[tuple[int, int, str, int]]) -> tuple[str, list[tuple[int, int, str, int]]]:
    """Apply sorted, non-overlapping edits (start, end, replacement, finding id); return the text and the
    edits as applied.

    A deletion takes one neighbouring space with it, so the sentences around it don't end up two spaces
    apart (or the text with a trailing space), unless another edit starts right there."""
    starts = {e[0] for e in edits}
    done = []
    for start, end, replacement, fid in reversed(edits):  # right to left keeps earlier offsets valid
        if not replacement:
            if text[end:end + 1] == " " and end not in starts:
                end += 1
            elif end >= len(text) and text[start - 1:start] == " " and start > 0:
                start -= 1
        text = text[:start] + replacement + text[end:]
        done.append((start, end, replacement, fid))
    return text, list(reversed(done))

async def _new_version(session, user: User, content: Content, body: str, attachments: dict | None,
                       notes: dict | None = None) -> ContentVersion:
    if content.status in (S.published, S.withdrawn):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"content is {content.status.value}; create a new piece of content instead")
    latest = await session.scalar(
        select(ContentVersion).where(ContentVersion.content_id == content.id)
        .order_by(ContentVersion.version_no.desc()).limit(1))
    attachments = dict(latest.attachments or {}) if attachments is None else dict(attachments)
    notes = dict(latest.creator_notes or {}) if notes is None else dict(notes)
    # A revision keeps the brief it was given unless it says otherwise, and a video already in the
    # previous version (made before briefs were asked for) isn't held back for lacking one.
    for key in ("brief", "brief_audio_blob_id"):
        if not notes.get(key) and (latest.creator_notes or {}).get(key):
            notes[key] = latest.creator_notes[key]
    same_videos = {v.get("blob_id") for v in attachments.get("videos", [])} \
        <= {v.get("blob_id") for v in (latest.attachments or {}).get("videos", [])}
    attachments["profile"] = await _intake(session, user, content.channel, body, attachments, notes,
                                           brief_required=not same_videos)
    version = ContentVersion(content_id=content.id, version_no=latest.version_no + 1, parent_id=latest.id,
                             body=body, attachments=attachments, creator_notes=notes, created_by=user.id)
    session.add(version)
    try:
        await session.flush()
    except IntegrityError:
        # Two saves raced for the same version number (double click on apply-fixes).
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "another version was created at the same moment; reload and try again") from None
    if content.status is S.approved:
        # The approval covered the previous text. New text needs a new human decision.
        session.add(WorkflowEvent(content_id=content.id, from_status=S.approved, to_status=S.in_review,
                                  actor_id=user.id, note=f"version {version.version_no} saved after approval"))
        content.status = S.in_review
    return version


@router.post("/contents/{content_id}/versions", response_model=SubmitOut, status_code=status.HTTP_201_CREATED,
             dependencies=[SelfServeBudget])
async def add_version(content_id: int, body: VersionIn, session: Session, user: Writer, prism: PrismDep,
                      wait: bool = False) -> SubmitOut:
    content = await _content(session, user, content_id)
    attachments = body.attachments.model_dump(exclude_none=True) if body.attachments else None
    notes = body.creator_notes.model_dump(exclude_none=True) if body.creator_notes else None
    version = await _new_version(session, user, content, body.body, attachments, notes)
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="version.created",
                 object_type="content", object_id=content.id, detail={"version_no": version.version_no})
    review_id = await _start_review(session, prism, version, wait)
    return SubmitOut(content=ContentOut.model_validate(content), version=VersionOut.model_validate(version),
                     review_id=review_id)


@router.post("/contents/{content_id}/apply-fixes", response_model=SubmitOut, status_code=status.HTTP_201_CREATED,
             dependencies=[SelfServeBudget])
async def apply_fixes(content_id: int, session: Session, user: Writer, prism: PrismDep,
                      wait: bool = False) -> SubmitOut:
    """Build the next version from accepted and edited decisions on the latest
    review. This is the board's raw -> first cite -> corrected step."""
    content = await _content(session, user, content_id)
    review = await _latest_review(session, content.id)
    if review is None or review.status is not ReviewStatus.done:
        raise HTTPException(status.HTTP_409_CONFLICT, "no finished review to apply")
    version = await session.get(ContentVersion, review.version_id)
    findings = (await session.scalars(
        select(Finding).options(selectinload(Finding.decisions), selectinload(Finding.suggestions))
        .where(Finding.review_id == review.id))).all()

    edits: list[tuple[int, int, str, int]] = []  # (start, end, replacement, finding_id)
    for f in findings:
        # Only typed text can be patched; a finding inside an image or PDF page
        # points into that source's text, and its fix is guidance for the creator.
        if not f.decisions or f.span_start is None or f.span_end is None or f.source != "body":
            continue
        d = f.decisions[-1]
        if d.action is DecisionAction.edited and d.edited_text:
            edits.append((f.span_start, f.span_end, d.edited_text, f.id))
        elif d.action is DecisionAction.accepted:
            s = next((s for s in f.suggestions if s.id == d.suggestion_id), f.suggestions[0] if f.suggestions else None)
            if s is None:
                continue
            at = version.body.find(s.original, f.span_start, f.span_end)
            if at >= 0:
                edits.append((at, at + len(s.original), s.proposed, f.id))
    if not edits:
        raise HTTPException(status.HTTP_409_CONFLICT, "no accepted or edited fixes to apply")

    ordered = sorted(edits, key=lambda e: (e[0], e[1]))
    conflicts = [(a[3], b[3]) for a, b in zip(ordered, ordered[1:], strict=False) if b[0] < a[1]]
    if conflicts:
        # Silently picking one would drop a human decision, so make the person choose.
        pairs = ", ".join(f"#{a} and #{b}" for a, b in conflicts)
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"fixes overlap for findings {pairs}; dismiss one of each pair or edit the text directly")
    body, spliced = _splice(version.body, ordered)
    applied = [{"finding_id": fid, "start": start, "end": end, "before": version.body[start:end], "after": rep}
               for start, end, rep, fid in reversed(spliced)]

    new = await _new_version(session, user, content, body, None)
    session.add(Change(from_version_id=version.id, to_version_id=new.id, diff=list(reversed(applied))))
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="fixes.applied",
                 object_type="content", object_id=content.id,
                 detail={"from_version": version.version_no, "to_version": new.version_no, "edits": len(applied)})
    review_id = await _start_review(session, prism, new, wait)
    return SubmitOut(content=ContentOut.model_validate(content), version=VersionOut.model_validate(new),
                     review_id=review_id)


@router.get("/contents", response_model=list[ContentListItem])
async def list_contents(session: Session, user: CurrentUser, state: ContentStatus | None = None,
                        mine: bool = False, limit: int = Query(200, ge=1, le=500)) -> list[ContentListItem]:
    """Newest activity first, each with its latest review's outcome, so a history list needs one call."""
    q = select(Content).where(Content.workspace_id == user.workspace_id)
    if state:
        q = q.where(Content.status == state)
    if mine or user.role is Role.creator:
        q = q.where(Content.created_by == user.id)
    rows = [c for c in (await session.scalars(q.order_by(Content.id.desc()))).all() if can_read(user, c.tier)]
    if not rows:
        return []
    ids = [c.id for c in rows]
    versions = (await session.execute(
        select(ContentVersion.id, ContentVersion.content_id, ContentVersion.created_at)
        .where(ContentVersion.content_id.in_(ids)))).all()
    content_of = {v.id: v.content_id for v in versions}
    count: dict[int, int] = {}
    last_edit: dict[int, datetime] = {}
    for v in versions:
        count[v.content_id] = count.get(v.content_id, 0) + 1
        last_edit[v.content_id] = max(last_edit.get(v.content_id, v.created_at), v.created_at)
    latest: dict[int, Review] = {}
    for r in (await session.scalars(
            select(Review).where(Review.version_id.in_(list(content_of))).order_by(Review.id.desc()))).all():
        latest.setdefault(content_of[r.version_id], r)

    # When each piece entered its current status: a queue is ordered by how long it has waited
    # there, not by when its text or check last changed.
    since: dict[int, datetime] = {}
    status_of = {c.id: c.status for c in rows}
    for cid, to, at in (await session.execute(
            select(WorkflowEvent.content_id, WorkflowEvent.to_status, WorkflowEvent.created_at)
            .where(WorkflowEvent.content_id.in_(ids)).order_by(WorkflowEvent.id))).all():
        if to == status_of[cid]:
            since[cid] = at
    open_esc: dict[int, int] = dict((await session.execute(
        select(Escalation.content_id, func.count()).where(Escalation.content_id.in_(ids), Escalation.status == "open")
        .group_by(Escalation.content_id))).all())
    rechecked: dict[int, int] = {}
    for cid, eid in (await session.execute(select(EventImpact.content_id, EventImpact.event_id)
                                           .where(EventImpact.content_id.in_(ids)).order_by(EventImpact.id))).all():
        rechecked[cid] = eid

    out = []
    for c in rows:
        item = ContentListItem.model_validate(c)
        item.status_since = since.get(c.id, c.created_at)
        item.open_escalations = open_esc.get(c.id, 0)
        item.rechecked_for_event = rechecked.get(c.id)
        item.version_count = count.get(c.id, 0)
        r = latest.get(c.id)
        item.updated_at = max(filter(None, [last_edit.get(c.id), r.finished_at if r else None]), default=c.created_at)
        if r is not None:
            s = r.summary or {}
            item.latest_review = LatestReview(id=r.id, status=r.status, overall=s.get("overall"),
                                              blockers=s.get("blockers", 0), warnings=s.get("warnings", 0),
                                              advisories=s.get("advisories", 0), finished_at=r.finished_at)
        out.append(item)
    out.sort(key=lambda i: _aware(i.updated_at), reverse=True)
    return out[:limit]


def _aware(t: datetime | None) -> datetime:
    """SQLite hands back naive datetimes; compare everything as UTC."""
    if t is None:
        return datetime.min.replace(tzinfo=UTC)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


@router.get("/contents/{content_id}", response_model=ContentDetail)
async def get_content(content_id: int, session: Session, user: CurrentUser) -> ContentDetail:
    content = await _content(session, user, content_id, with_versions=True)
    latest = await _latest_review(session, content.id)
    detail = ContentDetail.model_validate(content)
    detail.latest_review_id = latest.id if latest else None
    return detail


async def _document(session, user: User, content_id: int, version_id: int, doc_id: str) -> tuple[Content, bytes]:
    """One attached document's bytes, readable exactly when the piece is; one 404 for anything missing."""
    content = await _content(session, user, content_id, with_versions=True)
    version = next((v for v in content.versions if v.id == version_id), None)
    doc = next((d for d in ((version.attachments or {}).get("documents", []) if version else [])
                if isinstance(d, dict) and d.get("id") == doc_id), None)
    raw: bytes | None = None
    if doc is not None and doc.get("data_base64"):
        raw = base64.b64decode(doc["data_base64"])
    elif doc is not None and doc.get("blob_id"):
        blob = await session.get(MediaBlob, doc["blob_id"])
        raw = blob.data if blob is not None and blob.workspace_id == content.workspace_id else None
    if raw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return content, raw


_PREVIEW_DEADLINE = 180  # seconds; past the queue wait plus a conversion, the request is answered anyway
# Previews get their own threads, apart from the pool every other blocking call shares: conversions (slow,
# one at a time in LibreOffice; one that outlives its request keeps its thread) and drawing pages of a PDF
# already in hand, so a page of a converted deck never waits behind someone else's conversion.
_CONVERT_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preview-convert")
_DRAW_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preview-draw")


async def _blocking(fn, *args, pool: ThreadPoolExecutor = _DRAW_POOL):
    try:
        return await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(pool, fn, *args),
                                      _PREVIEW_DEADLINE)
    except TimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "the preview took too long; try again") from None
    except MediaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


async def _pdf_of(raw: bytes, kind: str) -> bytes:
    return await _blocking(preview.ready, raw, kind) or await _blocking(preview.as_pdf, raw, kind, pool=_CONVERT_POOL)


@router.get("/contents/{content_id}/versions/{version_id}/documents/{doc_id}/preview")
async def document_preview(content_id: int, version_id: int, doc_id: str, session: Session,
                           user: CurrentUser) -> dict:
    """How to show one attached document as it looks. A PDF, Word file or deck: its page sizes and where each
    finding of the version's latest review sits on them (pictures from the route below). A web page: its HTML
    as text, for the browser's locked frame; it is never served as a page from here."""
    _, raw = await _document(session, user, content_id, version_id, doc_id)
    kind = sniff(raw)
    if kind == "text/html":
        return {"kind": "html", "html": raw[:MAX_HTML_BYTES].decode("utf-8", "replace")}
    pdf = await _pdf_of(raw, kind)
    sizes, total = await _blocking(preview.page_sizes, pdf)
    review = await session.scalar(select(Review).where(Review.version_id == version_id).order_by(Review.id.desc())
                                  .limit(1))
    wanted: list[tuple[int, str, int | None]] = []
    if review is not None:
        rows = (await session.scalars(select(Finding).where(
            Finding.review_id == review.id, Finding.source.startswith(f"doc:{doc_id}:", autoescape=True)))).all()
        # A slide and a PDF page are the same page in the picture; Word has no pages of its own, so anywhere.
        paged = kind != DOCX
        wanted = [(f.id, f.quote, (f.locator or {}).get("page") if paged else None) for f in rows if f.quote]
    marks = await _blocking(preview.locate, pdf, wanted) if wanted else []
    return {"kind": "pages", "pages": [{"width": w, "height": h} for w, h in sizes], "total_pages": total,
            "marks": [{"finding_id": m.finding_id, "page": m.page, "box": list(m.box)} for m in marks]}


@router.get("/contents/{content_id}/versions/{version_id}/documents/{doc_id}/pages/{number}")
async def document_page(content_id: int, version_id: int, doc_id: str, number: int, session: Session,
                        user: CurrentUser) -> Response:
    """One page of an attached document as a picture."""
    _, raw = await _document(session, user, content_id, version_id, doc_id)
    pdf = await _pdf_of(raw, sniff(raw))
    png = await _blocking(preview.render, pdf, number)
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"})


@router.get("/contents/{content_id}/versions/{version_id}/images/{image_id}")
async def version_image(content_id: int, version_id: int, image_id: str, session: Session,
                        user: CurrentUser) -> Response:
    """One attached image, so a reviewer sees what was checked, with each finding's box drawn over it.
    Readable exactly when the content is: one 404 for a missing piece, version or image."""
    content = await _content(session, user, content_id, with_versions=True)
    version = next((v for v in content.versions if v.id == version_id), None)
    image = next((i for i in ((version.attachments or {}).get("images", []) if version else [])
                  if isinstance(i, dict) and i.get("id") == image_id), None)
    raw: bytes | None = None
    if image is not None and image.get("data_base64"):
        raw = base64.b64decode(image["data_base64"])
    elif image is not None and image.get("blob_id"):
        blob = await session.get(MediaBlob, image["blob_id"])
        raw = blob.data if blob is not None and blob.workspace_id == content.workspace_id else None
    if raw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image not found")
    # The type is sniffed from the bytes, not trusted from the upload, and the browser may not guess.
    kind = sniff(raw)
    if not kind.startswith("image/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image not found")
    return Response(raw, media_type=kind,
                    # Revalidated every time: one browser can switch between accounts with different clearances.
                    headers={"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"})


@router.get("/contents/{content_id}/versions/{version_id}/videos/{video_id}")
async def version_video(content_id: int, version_id: int, video_id: str, session: Session, user: CurrentUser,
                        range_: Annotated[str | None, Header(alias="range")] = None) -> Response:
    """One attached video, streamed in ranges so the review's player can seek to a finding's moment.
    Shown in place, never offered as a download; readable exactly when the content is."""
    content = await _content(session, user, content_id, with_versions=True)
    version = next((v for v in content.versions if v.id == version_id), None)
    video = next((v for v in ((version.attachments or {}).get("videos", []) if version else [])
                  if isinstance(v, dict) and v.get("id") == video_id), None)
    blob = await session.get(MediaBlob, video["blob_id"], options=[defer(MediaBlob.data)]) \
        if video and video.get("blob_id") else None
    if blob is None or blob.workspace_id != content.workspace_id or not blob.media_type.startswith("video/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "video not found")
    return await serve.inline(session, blob.id, blob.media_type, blob.size, range_)


@router.get("/reviews/{review_id}", response_model=ReviewOut)
async def get_review(review_id: int, request: Request, session: Session, user: CurrentUser) -> ReviewOut:
    review = await session.scalar(
        select(Review).where(Review.id == review_id).options(
            selectinload(Review.findings).selectinload(Finding.suggestions),
            selectinload(Review.findings).selectinload(Finding.decisions),
            selectinload(Review.findings).selectinload(Finding.rule),
            selectinload(Review.findings).selectinload(Finding.fact),
        ))
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "review not found")
    version = await session.get(ContentVersion, review.version_id)
    await _content(session, user, version.content_id)  # workspace + clearance check

    keyring = request.app.state.prism.keyring
    out = ReviewOut.model_validate(review, from_attributes=True)
    if user.role is Role.creator and out.coverage:
        # Decision counts and per-rule fix tallies describe other people's pieces.
        out.coverage = {k: v for k, v in out.coverage.items() if k not in ("calibration", "fix_style", "precedents")}
    out.findings = []
    for f in review.findings:
        fo = FindingOut.model_validate(f)
        if user.role is Role.creator:
            # Precedents quote other pieces and name their reviewers; a creator sees only their own work.
            # The agreement rate stays, but not how many decisions on others' pieces it rests on.
            fo.precedents = None
            if fo.calibration:
                fo.calibration = {k: v for k, v in fo.calibration.items() if k != "n"}
        cites = []
        if f.rule:
            label = f"{f.rule.code} v{f.rule.version}: {f.rule.title}"
            cites.append(CitationOut(kind="rule", id=f.rule.id, label=label, source=f.rule.source_ref))
        if f.fact:
            cites.append(CitationOut(kind="fact", id=f.fact.id, label=f.fact.statement, source=f.fact.source_ref))
        fo.citations = cites
        fix = (f.suggestions[0].original, f.suggestions[0].proposed) if f.suggestions else None
        fo.signature_valid = keyring.verify(f.signature, finding_payload(review.id, f, f.rule_id, f.level.value, fix))
        out.findings.append(fo)
    return out


@router.post("/findings/{finding_id}/decision", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
async def decide(finding_id: int, body: DecisionIn, session: Session, user: Reviewer) -> Decision:
    finding, content = await _readable_finding(session, user, finding_id, selectinload(Finding.suggestions))
    if body.suggestion_id is not None and body.suggestion_id not in {s.id for s in finding.suggestions}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "suggestion does not belong to this finding")
    if (finding.level is Level.blocker and body.action is DecisionAction.rejected
            and user.role not in (Role.approver, Role.brand_admin)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only approvers can dismiss a blocker")

    decision = Decision(finding_id=finding.id, actor_id=user.id, **body.model_dump())
    session.add(decision)
    await session.flush()
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="finding.decided",
                 object_type="finding", object_id=finding.id,
                 detail={"content_id": content.id, "action": body.action, "reason_code": body.reason_code,
                         "rule_id": finding.rule_id, "level": finding.level})
    await session.commit()
    return decision


async def _approval_state(session, content_id: int) -> tuple[str | None, int, list[str]]:
    """(why approval can't even be considered, open blockers, check families that did not run)."""
    review = await _latest_review(session, content_id)
    if review is None:
        return "no automated review has run yet", 0, []
    if review.status is ReviewStatus.failed:
        return "the latest automated review failed; save a new version to re-run it", 0, []
    if review.status is not ReviewStatus.done:
        return "the latest automated review has not finished", 0, []
    # A new version is committed (with its audit entry) a moment before its review row, so for that
    # moment the newest review is still the previous version's. Approving then would approve text
    # nothing has checked.
    newest = await session.scalar(select(func.max(ContentVersion.id)).where(ContentVersion.content_id == content_id))
    if review.version_id != newest:
        return "the latest version has not been reviewed yet", 0, []
    blockers = (await session.scalars(
        select(Finding).options(selectinload(Finding.decisions))
        .where(Finding.review_id == review.id, Finding.level == Level.blocker))).all()
    # A blocker is resolved only by an explicit human dismissal; accepting a
    # fix means a new version (and review) is still to come.
    open_ = [f for f in blockers if not (f.decisions and f.decisions[-1].action is DecisionAction.rejected)]
    return None, len(open_), list((review.coverage or {}).get("not_checked") or [])


@router.post("/contents/{content_id}/transition", response_model=ContentOut)
async def transition(content_id: int, body: TransitionIn, session: Session, user: CurrentUser) -> Content:
    content = await _content(session, user, content_id)
    current, target = content.status, body.to

    if target is S.withdrawn:
        if user.id != content.created_by and user.role not in (Role.approver, Role.brand_admin):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only the author or an approver can withdraw")
        if current is S.published:
            raise HTTPException(status.HTTP_409_CONFLICT, "published content cannot be withdrawn here")
    else:
        allowed = _TRANSITIONS.get((current, target))
        if allowed is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"cannot move from {current.value} to {target.value}")
        if user.role not in allowed | {Role.brand_admin}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"{user.role.value} cannot move content to {target.value}")

    overridden, unchecked = 0, []
    if target in (S.approved, S.published):
        pending, open_blockers, unchecked = await _approval_state(session, content.id)
        if pending:
            raise HTTPException(status.HTTP_409_CONFLICT, pending)
        problems = []
        if open_blockers:
            problems.append(f"{open_blockers} unresolved blocker(s)")
        if unchecked:
            # A check that did not run is not a pass.
            problems.append(f"checks that did not run: {', '.join(unchecked)}")
        if problems:
            note = (body.note or "").strip()
            if not (body.override_blockers and len(note) >= OVERRIDE_NOTE_MIN):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"{'; '.join(problems)}. Resolve them, or override with a note of at least "
                    f"{OVERRIDE_NOTE_MIN} characters explaining why.")
            overridden = open_blockers

    session.add(WorkflowEvent(content_id=content.id, from_status=current, to_status=target, actor_id=user.id,
                              note=body.note))
    content.status = target
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="content.transition",
                 object_type="content", object_id=content.id,
                 detail={"from": current, "to": target, "blockers_overridden": overridden,
                         "unchecked_overridden": unchecked, "note": body.note})
    await session.commit()
    return content


@router.get("/contents/{content_id}/comments", response_model=list[CommentOut])
async def list_comments(content_id: int, session: Session, user: CurrentUser) -> list[Comment]:
    await _content(session, user, content_id)
    return list((await session.scalars(
        select(Comment).where(Comment.content_id == content_id).order_by(Comment.id))).all())


@router.post("/contents/{content_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(content_id: int, body: CommentIn, session: Session, user: Writer) -> Comment:
    await _content(session, user, content_id)
    # Comments reach Inki's context, so a bribe or an instruction aimed at the model is still refused. Contact
    # details only flag: "the 9876543210 order code is wrong" is feedback, not an attempt to go off the record.
    await screened(session, workspace_id=user.workspace_id, actor_id=user.id, text=body.body, where="comment")
    if body.parent_id is not None:
        parent = await session.get(Comment, body.parent_id)
        if parent is None or parent.content_id != content_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "parent comment is on different content")
    if body.version_id is not None:
        version = await session.get(ContentVersion, body.version_id)
        if version is None or version.content_id != content_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "version does not belong to this content")
        if body.media_id is not None:
            media = {str(a.get("id")): key for key in ("images", "videos", "documents")
                     for a in (version.attachments or {}).get(key, [])}
            if body.media_id not in media:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "that version has no such image or video")
            if body.time_start is not None and media[body.media_id] != "videos":
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "only a video has moments to pin to")
    comment = Comment(content_id=content_id, actor_id=user.id, **body.model_dump())
    session.add(comment)
    await session.commit()
    return comment


@router.get("/contents/{content_id}/changes")
async def list_changes(content_id: int, session: Session, user: CurrentUser) -> list[dict]:
    await _content(session, user, content_id)
    versions = select(ContentVersion.id).where(ContentVersion.content_id == content_id)
    rows = (await session.scalars(select(Change).where(Change.to_version_id.in_(versions)).order_by(Change.id))).all()
    return [{"id": c.id, "from_version_id": c.from_version_id, "to_version_id": c.to_version_id, "diff": c.diff,
             "created_at": c.created_at} for c in rows]


@router.get("/contents/{content_id}/events")
async def list_events(content_id: int, session: Session, user: CurrentUser) -> list[dict]:
    await _content(session, user, content_id)
    rows = (await session.scalars(
        select(WorkflowEvent).where(WorkflowEvent.content_id == content_id).order_by(WorkflowEvent.id))).all()
    return [{"from": e.from_status, "to": e.to_status, "actor_id": e.actor_id, "note": e.note,
             "at": e.created_at} for e in rows]



@router.get("/contents/{content_id}/timeline")
async def timeline(content_id: int, session: Session, user: CurrentUser) -> dict:
    """The piece's whole story in time order, like a pull request's history: each version saved, what
    its check found, every status move, comment and human decision on a finding. The review map and
    the activity feed both read this, so the two parties always see the same record."""
    content = await _content(session, user, content_id)
    versions = (await session.scalars(select(ContentVersion).where(ContentVersion.content_id == content_id)
                                      .order_by(ContentVersion.version_no))).all()
    version_no = {v.id: v.version_no for v in versions}
    saved_at = {v.id: v.created_at for v in versions}
    reviews = (await session.scalars(select(Review).where(Review.version_id.in_(list(version_no)))
                                     .order_by(Review.id))).all()
    events = (await session.scalars(select(WorkflowEvent).where(WorkflowEvent.content_id == content_id)
                                    .order_by(WorkflowEvent.id))).all()
    comments = (await session.scalars(select(Comment).where(Comment.content_id == content_id)
                                      .order_by(Comment.id))).all()
    decisions = (await session.execute(
        select(Decision, Finding.title, Finding.level, Review.version_id)
        .join(Finding, Decision.finding_id == Finding.id).join(Review, Finding.review_id == Review.id)
        .where(Review.version_id.in_(list(version_no))).order_by(Decision.id))).all()
    actor_ids = ({v.created_by for v in versions} | {e.actor_id for e in events} | {c.actor_id for c in comments}
                 | {d.actor_id for d, *_ in decisions} | {content.created_by})
    people = {u.id: {"id": u.id, "name": u.name, "role": u.role} for u in (await session.scalars(
        select(User).where(User.id.in_(actor_ids), User.workspace_id == user.workspace_id))).all()}

    items: list[dict] = [{"type": "version", "at": v.created_at, "actor": people.get(v.created_by),
                          "version": v.version_no} for v in versions]
    for r in reviews:
        s = r.summary or {}
        # A review not yet started belongs where its version was saved, not at the top of the story.
        items.append({"type": "review", "at": r.finished_at or r.started_at or saved_at[r.version_id],
                      "actor": None, "version": version_no[r.version_id], "review_id": r.id, "status": r.status,
                      "score": s.get("overall"), "blockers": s.get("blockers", 0), "warnings": s.get("warnings", 0),
                      "advisories": s.get("advisories", 0)})
    items += [{"type": "status", "at": e.created_at, "actor": people.get(e.actor_id), "from": e.from_status,
               "to": e.to_status, "note": e.note} for e in events]
    items += [{"type": "comment", "at": c.created_at, "actor": people.get(c.actor_id), "id": c.id,
               "parent_id": c.parent_id, "version": version_no.get(c.version_id), "body": c.body,
               "span": [c.span_start, c.span_end] if c.span_start is not None else None} for c in comments]
    items += [{"type": "decision", "at": d.created_at, "actor": people.get(d.actor_id), "finding": title,
               "level": level, "version": version_no[vid], "action": d.action, "reason_code": d.reason_code,
               "reason": d.reason_text} for d, title, level, vid in decisions]
    # Stable order for equal timestamps: a version comes before its review, a move after both.
    escalations = (await session.execute(
        select(Escalation, Finding.title, Finding.level).join(Finding, Escalation.finding_id == Finding.id)
        .where(Escalation.content_id == content_id).order_by(Escalation.id))).all()
    impacts = (await session.execute(
        select(EventImpact, BrandEvent.name).join(BrandEvent, EventImpact.event_id == BrandEvent.id)
        .where(EventImpact.content_id == content_id).order_by(EventImpact.id))).all()
    involved = {e.raised_by for e, *_ in escalations} | {e.resolved_by for e, *_ in escalations if e.resolved_by}
    extra = involved - set(people)
    if extra:
        people |= {u.id: {"id": u.id, "name": u.name, "role": u.role} for u in (await session.scalars(
            select(User).where(User.id.in_(extra), User.workspace_id == user.workspace_id))).all()}
    for e, title, level in escalations:
        items.append({"type": "escalation", "at": e.created_at, "actor": people.get(e.raised_by), "id": e.id,
                      "finding": title, "level": level, "message": e.message, "state": "raised"})
        if e.resolved_at:
            items.append({"type": "escalation", "at": e.resolved_at, "actor": people.get(e.resolved_by), "id": e.id,
                          "finding": title, "level": level, "message": e.resolution, "state": e.status})
    items += [{"type": "event", "at": i.created_at, "actor": None, "event": name, "change": i.change,
               "revision": i.revision, "review_id": i.review_id} for i, name in impacts]
    rank = {"version": 0, "review": 1, "decision": 2, "status": 3, "comment": 4, "escalation": 5, "event": 6}
    items.sort(key=lambda i: (_aware(i["at"]), rank[i["type"]]))
    for i in items:
        i["at"] = _aware(i["at"]).isoformat()
    return {"status": content.status, "author": people.get(content.created_by), "items": items}


# --- disputes, resubmission and AI edits ---------------------------------------------------------

DISPUTE_LIMIT = 50


async def _finding_in_latest(session, content: Content, finding_id: int) -> Finding:
    review = await _latest_review(session, content.id)
    finding = await session.get(Finding, finding_id)
    if finding is None or review is None or finding.review_id != review.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"finding {finding_id} is not on this content's latest review")
    return finding


async def _file_dispute(session, user: User, content: Content, finding_id: int, claim: str,
                        language: str | None) -> Dispute:
    finding = await _finding_in_latest(session, content, finding_id)
    open_count = await session.scalar(select(func.count()).select_from(Dispute).where(
        Dispute.content_id == content.id, Dispute.status.in_(("queued", "running"))))
    if open_count >= DISPUTE_LIMIT:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many disputes waiting on this content")
    dispute = Dispute(finding_id=finding.id, content_id=content.id, rule_id=finding.rule_id, user_id=user.id,
                      claim=claim.strip(), language=language)
    session.add(dispute)
    await session.flush()
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="dispute.filed",
                 object_type="dispute", object_id=dispute.id, detail={"finding_id": finding.id})
    return dispute


def _can_dispute(user: User, content: Content) -> None:
    if user.id != content.created_by and user.role not in (Role.reviewer, Role.approver, Role.brand_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the author or a reviewer can dispute a finding")


@router.post("/findings/{finding_id}/disputes", response_model=DisputeOut, status_code=status.HTTP_201_CREATED,
             dependencies=[SelfServeBudget])
async def dispute_finding(finding_id: int, body: DisputeIn, session: Session, user: CurrentUser,
                          prism: PrismDep, wait: bool = False) -> Dispute:
    """'That is not what it means.' Queued and re-evaluated by Prism; the verdict can still be no."""
    _, content = await _readable_finding(session, user, finding_id)
    _can_dispute(user, content)
    await screened(session, workspace_id=user.workspace_id, actor_id=user.id, text=body.claim, where="dispute")
    dispute = await _file_dispute(session, user, content, finding_id, body.claim, body.language)
    await session.commit()
    if wait:
        await dispute_engine.evaluate(prism, dispute.id)
        await session.refresh(dispute)
    else:
        prism.schedule_job(lambda: dispute_engine.evaluate(prism, dispute.id))
    return dispute


@router.get("/contents/{content_id}/disputes", response_model=list[DisputeOut])
async def list_disputes(content_id: int, session: Session, user: CurrentUser) -> list[Dispute]:
    await _content(session, user, content_id)
    return list((await session.scalars(
        select(Dispute).where(Dispute.content_id == content_id).order_by(Dispute.id))).all())


@router.post("/contents/{content_id}/resubmit", response_model=ResubmitOut, status_code=status.HTTP_201_CREATED,
             dependencies=[SelfServeBudget])
async def resubmit(content_id: int, body: ResubmitIn, session: Session, user: Writer, prism: PrismDep,
                   wait: bool = False) -> ResubmitOut:
    """The checklist round trip: apply chosen fixes, note what was fixed by hand, dispute what was
    misread, and run everything again. Disputes are decided before the new review runs, so a reading
    overturned now is not raised at full weight again."""
    content = await _content(session, user, content_id)
    _can_dispute(user, content)
    # Screened before anything is saved, so a refusal leaves no half-made version behind.
    for d in body.disputes:
        await screened(session, workspace_id=user.workspace_id, actor_id=user.id, text=d.claim, where="dispute")
    review = await _latest_review(session, content.id)
    if review is None or review.status is not ReviewStatus.done:
        raise HTTPException(status.HTTP_409_CONFLICT, "no finished review to work from")
    version = await session.get(ContentVersion, review.version_id)
    findings = {f.id: f for f in (await session.scalars(
        select(Finding).options(selectinload(Finding.suggestions)).where(Finding.review_id == review.id))).all()}

    skipped: list[str] = []
    text = version.body
    edits: list[tuple[int, int, str, int]] = []
    if body.body is not None:
        text = body.body
        if body.apply:
            skipped.append("suggested fixes were not applied because the text was replaced")
    else:
        for fid in body.apply:
            f = findings.get(fid)
            if f is None or not f.suggestions or f.source != "body" or f.span_start is None:
                skipped.append(f"finding {fid}: no fix that can be applied to the typed text")
                continue
            s = f.suggestions[0]
            at = text.find(s.original, f.span_start, (f.span_end or f.span_start) + len(s.original))
            if at < 0:
                skipped.append(f"finding {fid}: the text it fixes has changed")
                continue
            edits.append((at, at + len(s.original), s.proposed, fid))
        edits.sort(key=lambda e: (e[0], e[1]))
        kept: list[tuple[int, int, str, int]] = []
        for e in edits:
            if kept and e[0] < kept[-1][1]:
                skipped.append(f"finding {e[3]}: overlaps the fix for finding {kept[-1][3]}")
                continue
            kept.append(e)
        text, edits = _splice(text, kept)

    notes = (body.creator_notes.model_dump(exclude_none=True) if body.creator_notes
             else dict(version.creator_notes or {}))
    notes["resolved"] = sorted({i for i in body.resolved if i in findings})
    attachments = body.attachments.model_dump(exclude_none=True) if body.attachments else None
    filed = [await _file_dispute(session, user, content, d.finding_id, d.claim, d.language) for d in body.disputes]
    new = await _new_version(session, user, content, text, attachments, notes)
    if edits:
        session.add(Change(from_version_id=version.id, to_version_id=new.id,
                           diff=[{"finding_id": fid, "start": a, "end": b, "after": r} for a, b, r, fid in edits]))
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="content.resubmitted",
                 object_type="content", object_id=content.id,
                 detail={"version_no": new.version_no, "applied": len(edits), "resolved": notes["resolved"],
                         "disputes": [d.id for d in filed]})
    next_review = Review(version_id=new.id)
    session.add(next_review)
    await session.commit()
    dispute_ids = [d.id for d in filed]

    async def chain() -> None:
        # The new review runs whatever happens to the disputes: a failed
        # evaluation must not leave the resubmission queued forever.
        try:
            for did in dispute_ids:
                try:
                    await dispute_engine.evaluate(prism, did)
                except Exception:  # noqa: BLE001, evaluate already escalates what it can
                    log.exception("dispute %s could not be evaluated before resubmit review", did)
        finally:
            await prism.run(next_review.id)

    if wait:
        await chain()
    else:
        prism.schedule_job(chain)
    submit = SubmitOut(content=ContentOut.model_validate(content), version=VersionOut.model_validate(new),
                       review_id=next_review.id)
    return ResubmitOut(submit=submit, disputes=dispute_ids, applied=len(edits), skipped=skipped)


@router.post("/contents/{content_id}/ai-edit", response_model=AiEditOut, dependencies=[SelfServeBudget])
async def ai_edit(content_id: int, body: AiEditIn, session: Session, user: Writer, prism: PrismDep) -> AiEditOut:
    """A proposed rewrite following the creator's instruction and the brand rules. Nothing is saved:
    the creator reviews it and resubmits, and the full review runs again."""
    content = await _content(session, user, content_id)
    review = await _latest_review(session, content.id)
    version = await session.scalar(select(ContentVersion).options(selectinload(ContentVersion.content))
                                   .where(ContentVersion.content_id == content.id)
                                   .order_by(ContentVersion.version_no.desc()).limit(1))
    titles = []
    if review is not None:
        titles = [f"{f.title}: {f.explanation}" for f in (await session.scalars(
            select(Finding).where(Finding.review_id == review.id, Finding.source == "body"))).all()]
    result, remaining, model = await dispute_engine.ai_edit(prism, session, content, version, titles,
                                                            body.instruction)
    return AiEditOut(body=result.body, changes=result.changes, remaining=remaining, model=model)
