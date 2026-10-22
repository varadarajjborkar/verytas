"""Content lifecycle: submit, review, decide, apply fixes, approve."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from verytas.api.deps import CurrentUser, PrismDep, Session, can_read, require
from verytas.models import (
    Change,
    Comment,
    Content,
    ContentStatus,
    ContentVersion,
    Decision,
    DecisionAction,
    Finding,
    Level,
    Review,
    ReviewStatus,
    Role,
    User,
    WorkflowEvent,
)
from verytas.prism.orchestrator import finding_payload
from verytas.schemas import (
    CitationOut,
    CommentIn,
    CommentOut,
    ContentDetail,
    ContentIn,
    ContentOut,
    DecisionIn,
    DecisionOut,
    FindingOut,
    ReviewOut,
    SubmitOut,
    TransitionIn,
    VersionIn,
    VersionOut,
)
from verytas.security.audit import append

router = APIRouter(tags=["content"])
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
    # Same 404 for "missing" and "above your clearance" so tiers don't leak.
    if content is None or content.workspace_id != user.workspace_id or not can_read(user, content.tier):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    return content


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


@router.post("/contents", response_model=SubmitOut, status_code=status.HTTP_201_CREATED)
async def create_content(body: ContentIn, session: Session, user: Writer, prism: PrismDep,
                         wait: bool = False) -> SubmitOut:
    """Create a draft and start the automated pre-check. `wait=true` returns after the review finishes."""
    if not can_read(user, body.tier):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you cannot create content above your clearance")
    content = Content(workspace_id=user.workspace_id, title=body.title, channel=body.channel, tier=body.tier,
                      created_by=user.id)
    session.add(content)
    await session.flush()
    version = ContentVersion(content_id=content.id, version_no=1, body=body.body,
                             attachments=body.attachments.model_dump(exclude_none=True), created_by=user.id)
    session.add(version)
    await session.flush()
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="content.created",
                 object_type="content", object_id=content.id, detail={"tier": body.tier, "channel": body.channel})
    review_id = await _start_review(session, prism, version, wait)
    return SubmitOut(content=ContentOut.model_validate(content), version=VersionOut.model_validate(version),
                     review_id=review_id)


async def _new_version(session, user: User, content: Content, body: str, attachments: dict | None) -> ContentVersion:
    latest = await session.scalar(
        select(ContentVersion).where(ContentVersion.content_id == content.id)
        .order_by(ContentVersion.version_no.desc()).limit(1))
    version = ContentVersion(content_id=content.id, version_no=latest.version_no + 1, parent_id=latest.id,
                             body=body, attachments=latest.attachments if attachments is None else attachments,
                             created_by=user.id)
    session.add(version)
    await session.flush()
    return version


@router.post("/contents/{content_id}/versions", response_model=SubmitOut, status_code=status.HTTP_201_CREATED)
async def add_version(content_id: int, body: VersionIn, session: Session, user: Writer, prism: PrismDep,
                      wait: bool = False) -> SubmitOut:
    content = await _content(session, user, content_id)
    if content.status in (S.published, S.withdrawn):
        raise HTTPException(status.HTTP_409_CONFLICT, f"content is {content.status.value}")
    attachments = body.attachments.model_dump(exclude_none=True) if body.attachments else None
    version = await _new_version(session, user, content, body.body, attachments)
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="version.created",
                 object_type="content", object_id=content.id, detail={"version_no": version.version_no})
    review_id = await _start_review(session, prism, version, wait)
    return SubmitOut(content=ContentOut.model_validate(content), version=VersionOut.model_validate(version),
                     review_id=review_id)


@router.post("/contents/{content_id}/apply-fixes", response_model=SubmitOut, status_code=status.HTTP_201_CREATED)
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
        if not f.decisions or f.span_start is None or f.span_end is None:
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

    body, applied, cursor_end = version.body, [], len(version.body) + 1
    for start, end, replacement, fid in sorted(edits, key=lambda e: e[0], reverse=True):
        if end > cursor_end:
            continue  # overlaps an edit already applied further right; keep the first
        applied.append({"finding_id": fid, "start": start, "end": end, "before": body[start:end],
                        "after": replacement})
        body = body[:start] + replacement + body[end:]
        cursor_end = start

    new = await _new_version(session, user, content, body, None)
    session.add(Change(from_version_id=version.id, to_version_id=new.id, diff=list(reversed(applied))))
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="fixes.applied",
                 object_type="content", object_id=content.id,
                 detail={"from_version": version.version_no, "to_version": new.version_no, "edits": len(applied)})
    review_id = await _start_review(session, prism, new, wait)
    return SubmitOut(content=ContentOut.model_validate(content), version=VersionOut.model_validate(new),
                     review_id=review_id)


@router.get("/contents", response_model=list[ContentOut])
async def list_contents(session: Session, user: CurrentUser, state: ContentStatus | None = None) -> list[Content]:
    q = select(Content).where(Content.workspace_id == user.workspace_id)
    if state:
        q = q.where(Content.status == state)
    rows = (await session.scalars(q.order_by(Content.id.desc()))).all()
    return [c for c in rows if can_read(user, c.tier)]


@router.get("/contents/{content_id}", response_model=ContentDetail)
async def get_content(content_id: int, session: Session, user: CurrentUser) -> ContentDetail:
    content = await _content(session, user, content_id, with_versions=True)
    latest = await _latest_review(session, content.id)
    detail = ContentDetail.model_validate(content)
    detail.latest_review_id = latest.id if latest else None
    return detail


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
    out.findings = []
    for f in review.findings:
        fo = FindingOut.model_validate(f)
        cites = []
        if f.rule:
            label = f"{f.rule.code} v{f.rule.version}: {f.rule.title}"
            cites.append(CitationOut(kind="rule", id=f.rule.id, label=label, source=f.rule.source_ref))
        if f.fact:
            cites.append(CitationOut(kind="fact", id=f.fact.id, label=f.fact.statement, source=f.fact.source_ref))
        fo.citations = cites
        fo.signature_valid = keyring.verify(f.signature, finding_payload(review.id, f, f.rule_id))
        out.findings.append(fo)
    return out


@router.post("/findings/{finding_id}/decision", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
async def decide(finding_id: int, body: DecisionIn, session: Session, user: Reviewer) -> Decision:
    finding = await session.scalar(
        select(Finding).options(selectinload(Finding.suggestions)).where(Finding.id == finding_id))
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "finding not found")
    review = await session.get(Review, finding.review_id)
    version = await session.get(ContentVersion, review.version_id)
    content = await _content(session, user, version.content_id)
    if body.suggestion_id is not None and body.suggestion_id not in {s.id for s in finding.suggestions}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "suggestion does not belong to this finding")
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


async def _unresolved_blockers(session, content_id: int) -> tuple[Review | None, int]:
    review = await _latest_review(session, content_id)
    if review is None or review.status is not ReviewStatus.done:
        return review, -1
    blockers = (await session.scalars(
        select(Finding).options(selectinload(Finding.decisions))
        .where(Finding.review_id == review.id, Finding.level == Level.blocker))).all()
    # A blocker is resolved only by an explicit human dismissal; accepting a
    # fix means a new version (and review) is still to come.
    open_ = [f for f in blockers if not (f.decisions and f.decisions[-1].action is DecisionAction.rejected)]
    return review, len(open_)


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

    overridden = 0
    if target in (S.approved, S.published):
        review, open_blockers = await _unresolved_blockers(session, content.id)
        if open_blockers < 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "the latest automated review has not finished")
        if open_blockers:
            if not (body.override_blockers and body.note):
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    f"{open_blockers} unresolved blocker(s); dismiss them or override with a note")
            overridden = open_blockers

    session.add(WorkflowEvent(content_id=content.id, from_status=current, to_status=target, actor_id=user.id,
                              note=body.note))
    content.status = target
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="content.transition",
                 object_type="content", object_id=content.id,
                 detail={"from": current, "to": target, "blockers_overridden": overridden, "note": body.note})
    await session.commit()
    return content


@router.get("/contents/{content_id}/comments", response_model=list[CommentOut])
async def list_comments(content_id: int, session: Session, user: CurrentUser) -> list[Comment]:
    await _content(session, user, content_id)
    return list((await session.scalars(
        select(Comment).where(Comment.content_id == content_id).order_by(Comment.id))).all())


@router.post("/contents/{content_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(content_id: int, body: CommentIn, session: Session, user: CurrentUser) -> Comment:
    await _content(session, user, content_id)
    if body.parent_id is not None:
        parent = await session.get(Comment, body.parent_id)
        if parent is None or parent.content_id != content_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "parent comment is on different content")
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

