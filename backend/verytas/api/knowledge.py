"""Brand knowledge base: rules, approved facts and confidential terms."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from verytas.api.accounts import SelfServeBudget
from verytas.api.deps import CurrentUser, PrismDep, Session, can_read, require
from verytas.checks.base import FactView
from verytas.checks.claims import relevance
from verytas.checks.patterns import validate_pattern
from verytas.media import assets as asset_match
from verytas.media import documents
from verytas.media.files import MAX_IMAGE_BYTES, MediaError, decode_b64, open_image, sniff
from verytas.models import BrandAsset, ConfidentialTerm, Fact, MediaBlob, Role, Rule, RuleStatus, User
from verytas.prism import clarify, rulebook
from verytas.prism.disputes import workspace_redactor
from verytas.schemas import (
    BrandAssetIn,
    BrandAssetOut,
    BrandAssetPatch,
    FactIn,
    FactOut,
    RuleIn,
    RuleOut,
    RulePatch,
    TermIn,
    TermOut,
    TermPatch,
)
from verytas.security.audit import append

router = APIRouter(tags=["knowledge"])
Admin = Annotated[User, Depends(require(Role.brand_admin))]


# --- rules ---------------------------------------------------------------------

@router.get("/rules", response_model=list[RuleOut])
async def list_rules(session: Session, user: CurrentUser, state: RuleStatus | None = None) -> list[Rule]:
    q = select(Rule).where(Rule.workspace_id == user.workspace_id)
    if state:
        q = q.where(Rule.status == state)
    rules = (await session.scalars(q.order_by(Rule.code, Rule.version))).all()
    return [r for r in rules if can_read(user, r.tier)]


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(body: RuleIn, session: Session, admin: Admin) -> Rule:
    latest = await session.scalar(
        select(func.max(Rule.version)).where(Rule.workspace_id == admin.workspace_id, Rule.code == body.code))
    if latest:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.code} exists; PATCH it to create a new version")
    rule = Rule(workspace_id=admin.workspace_id, **body.model_dump())
    session.add(rule)
    await session.flush()
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="rule.created",
                 object_type="rule", object_id=rule.id, detail={"code": rule.code, "status": rule.status})
    await session.commit()
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleOut)
async def update_rule(rule_id: int, body: RulePatch, session: Session, admin: Admin) -> Rule:
    """Content edits create a new version (old findings keep citing the text they
    were judged against); a status-only change updates in place."""
    rule = await session.get(Rule, rule_id)
    if rule is None or rule.workspace_id != admin.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    latest = await session.scalar(
        select(func.max(Rule.version)).where(Rule.workspace_id == admin.workspace_id, Rule.code == rule.code))
    if rule.version != latest:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{rule.code} v{rule.version} is not the latest; edit v{latest}")
    # An explicit null means "leave it", not "erase a required field".
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "nothing to change")
    if "pattern" in changes:
        try:
            changes["pattern"] = validate_pattern(rule.kind.value, changes["pattern"])
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    content_fields = {k: v for k, v in changes.items() if k != "status"}

    target = rule
    if content_fields:
        copied = {c.name: getattr(rule, c.name) for c in Rule.__table__.columns if c.name not in ("id", "created_at")}
        target = Rule(**copied)
        target.version = rule.version + 1
        for k, v in content_fields.items():
            setattr(target, k, v)
        target.status = changes.get("status", rule.status)
        rule.status = RuleStatus.retired
        session.add(target)
    elif "status" in changes:
        rule.status = changes["status"]
    await session.flush()
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="rule.updated",
                 object_type="rule", object_id=target.id,
                 detail={"code": rule.code, "from_version": rule.version, "to_version": target.version,
                         "fields": sorted(changes)})
    await session.commit()
    return target


class ClarifyOut(BaseModel):
    rule_id: int
    code: str
    version: int
    current: dict
    proposed: dict  # the RulePatch body that applies it: text, good_examples, bad_examples
    changes: str
    cases: dict  # how many decided cases it was drafted from, per side
    model: str


@router.post("/rules/{rule_id}/clarify", response_model=ClarifyOut, dependencies=[SelfServeBudget])
async def clarify_rule(rule_id: int, session: Session, admin: Admin, prism: PrismDep) -> ClarifyOut:
    """A sharper wording for a rule reviewers disagree about, with examples from its own decided cases
    (prism/clarify.py). Nothing is saved: the admin applies it with PATCH /rules/{id}, edits it, or drops it."""
    rule = await session.get(Rule, rule_id)
    if rule is None or rule.workspace_id != admin.workspace_id or not can_read(admin, rule.tier):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    # Health reports may name an older version; the draft is always of the wording in force, so it applies.
    rule = await session.scalar(select(Rule).where(Rule.workspace_id == rule.workspace_id, Rule.code == rule.code)
                                .order_by(Rule.version.desc()).limit(1))
    if rule.kind.value != "semantic":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "only model-judged rules read their wording; edit a word list directly")
    found = await clarify.cases(session, rule)
    if found.decided < 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "too few decided findings on this rule to learn from yet")
    _, llm, _, _ = prism.guarded_providers(await workspace_redactor(session, admin.workspace_id))
    task = clarify.ClarifyTask(rule, found)
    model = llm.name
    try:
        draft = await llm.run(task)
    except Exception:  # noqa: BLE001, a model failure falls back to the plain draft, named as such
        draft, model = task.heuristic(), "offline-heuristic"
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}",
                 action="rule.clarification_drafted", object_type="rule", object_id=rule.id,
                 detail={"code": rule.code, "version": rule.version, "model": model, "cases": found.decided})
    await session.commit()
    return ClarifyOut(
        rule_id=rule.id, code=rule.code, version=rule.version,
        current={"text": rule.text, "good_examples": rule.good_examples or [], "bad_examples": rule.bad_examples or []},
        proposed=clarify.proposal(rule, found, draft), changes=draft.changes.strip()[:500],
        cases={"upheld": len(found.upheld), "cleared": len(found.cleared), "unclear": len(found.unclear)},
        model=model)


class ExtractIn(BaseModel):
    text: str | None = Field(default=None, max_length=200_000)
    blob_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    source_ref: str | None = Field(default=None, max_length=300)


class ExtractOut(BaseModel):
    rules: list[RuleIn]
    notes: list[str]
    model: str


MAX_BOOK_CHARS = 60_000


@router.post("/rules/extract", response_model=ExtractOut, dependencies=[SelfServeBudget])
async def extract_rules(body: ExtractIn, session: Session, admin: Admin, prism: PrismDep) -> ExtractOut:
    """Proposed draft rules from brand-book prose or an uploaded PDF or Word file. Nothing is saved:
    the admin keeps what reads right and creates those as drafts."""
    notes: list[str] = []
    text = body.text or ""
    if body.blob_id:
        blob = await session.get(MediaBlob, body.blob_id)
        if blob is None or blob.workspace_id != admin.workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "upload not found")
        reader = {"application/pdf": documents.extract_pdf}.get(blob.media_type)
        if reader is None and blob.media_type.startswith("application/vnd.openxmlformats"):
            reader = documents.extract_docx
        if reader is None:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "import reads PDF and Word files")
        try:
            book = await asyncio.to_thread(reader, blob.data)
        except MediaError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"couldn't read that file: {exc}") from None
        text = "\n\n".join(p.text for p in book.pages if p.text.strip())
        if any(p.scanned for p in book.pages):
            notes.append("Some pages are scans; only pages with a text layer were read.")
    if not text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "nothing to read: paste text or upload a file")
    if len(text) > MAX_BOOK_CHARS:
        notes.append(f"Only the first {MAX_BOOK_CHARS // 1000}k characters were read; import the rest separately.")
        text = text[:MAX_BOOK_CHARS]

    # Brand books mention codenames; they are redacted on the way out like any other model call.
    _, llm, _, _ = prism.guarded_providers(await workspace_redactor(session, admin.workspace_id))
    model = llm.name
    try:
        found = await llm.run(rulebook.RuleExtractTask(text))
    except Exception:  # noqa: BLE001, any model failure falls back to the plain reading
        found = rulebook.RuleExtractTask(text).heuristic()
        notes.append("The model was unavailable, so a simpler offline reading was used.")
        # Name what actually read it, so nobody credits the model with the heuristic's work.
        model = "offline-heuristic"
    taken = set((await session.scalars(select(Rule.code).where(Rule.workspace_id == admin.workspace_id))).all())
    rules, skipped = rulebook.to_rules(found.rules, taken, body.source_ref)
    return ExtractOut(rules=rules, notes=notes + skipped, model=model)


# --- facts -----------------------------------------------------------------------

@router.get("/facts", response_model=list[FactOut])
async def list_facts(session: Session, user: CurrentUser, valid_on: date | None = None,
                     q: str | None = None) -> list[Fact]:
    facts = [f for f in (await session.scalars(
        select(Fact).where(Fact.workspace_id == user.workspace_id).order_by(Fact.id))).all()
        if can_read(user, f.tier)]
    if valid_on:
        facts = [f for f in facts if f.valid_on(valid_on)]
    if q:
        scored = [(relevance(q, FactView(f.id, f.statement, f.value, f.unit, f.subject, f.source_ref,
                                         f.valid_from, f.valid_to)), f) for f in facts]
        facts = [f for s, f in sorted(scored, key=lambda t: -t[0]) if s > 0]
    return facts


@router.post("/facts", response_model=FactOut, status_code=status.HTTP_201_CREATED)
async def create_fact(body: FactIn, session: Session, admin: Admin) -> Fact:
    old = None
    if body.supersedes_id:
        old = await session.get(Fact, body.supersedes_id)
        if old is None or old.workspace_id != admin.workspace_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "superseded fact not found")
        if body.valid_from <= old.valid_from:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "a replacement fact must start after the fact it supersedes")
    fact = Fact(workspace_id=admin.workspace_id, approved=True, **body.model_dump())
    session.add(fact)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid fact") from None
    if old is not None and (old.valid_to is None or old.valid_to > body.valid_from):
        # Close the old fact's window where the new one opens, so exactly
        # one version of the figure is valid on any given day.
        old.valid_to = body.valid_from
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="fact.created",
                 object_type="fact", object_id=fact.id, detail={"supersedes": body.supersedes_id})
    await session.commit()
    return fact


@router.post("/facts/{fact_id}/retire", response_model=FactOut)
async def retire_fact(fact_id: int, session: Session, admin: Admin) -> Fact:
    """Stops a fact backing claims from today. Kept, not deleted: past findings cite it."""
    fact = await session.get(Fact, fact_id)
    if fact is None or fact.workspace_id != admin.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "fact not found")
    today = datetime.now(UTC).date()
    if fact.valid_from >= today:
        # Not open yet: its window can't close before it starts, so it is withdrawn instead.
        fact.approved = False
        # Withdrawing a scheduled replacement hands the figure back to the fact it would have
        # replaced, which was closed on the day this one was to open.
        old = await session.get(Fact, fact.supersedes_id) if fact.supersedes_id else None
        if old is not None and old.workspace_id == admin.workspace_id and old.valid_to == fact.valid_from:
            old.valid_to = None
    elif fact.valid_to is None or fact.valid_to > today:
        fact.valid_to = today
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="fact.retired",
                 object_type="fact", object_id=fact.id, detail={"valid_to": fact.valid_to})
    await session.commit()
    return fact


# --- confidential terms ------------------------------------------------------------

@router.get("/confidential-terms", response_model=list[TermOut])
async def list_terms(session: Session, admin: Admin) -> list[ConfidentialTerm]:
    return list((await session.scalars(
        select(ConfidentialTerm).where(ConfidentialTerm.workspace_id == admin.workspace_id))).all())


@router.post("/confidential-terms", response_model=TermOut, status_code=status.HTTP_201_CREATED)
async def create_term(body: TermIn, session: Session, admin: Admin) -> ConfidentialTerm:
    term = ConfidentialTerm(workspace_id=admin.workspace_id, **body.model_dump())
    session.add(term)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "term already listed") from None
    # The audit trail records that a term was added, never the term itself.
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="term.created",
                 object_type="confidential_term", object_id=term.id, detail={"embargo_until": body.embargo_until})
    await session.commit()
    return term


async def _term(session, admin: User, term_id: int) -> ConfidentialTerm:
    term = await session.get(ConfidentialTerm, term_id)
    if term is None or term.workspace_id != admin.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "term not found")
    return term


@router.patch("/confidential-terms/{term_id}", response_model=TermOut)
async def update_term(term_id: int, body: TermPatch, session: Session, admin: Admin) -> ConfidentialTerm:
    """Note and embargo date only; to change the spelling, add the new term and remove the old one."""
    term = await _term(session, admin, term_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(term, k, v)
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="term.updated",
                 object_type="confidential_term", object_id=term.id,
                 detail={"fields": sorted(changes), "embargo_until": term.embargo_until})
    await session.commit()
    return term


@router.delete("/confidential-terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_term(term_id: int, session: Session, admin: Admin) -> None:
    """The term stops being guarded. The audit entry records the removal, never the term."""
    term = await _term(session, admin, term_id)
    await session.delete(term)
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="term.deleted",
                 object_type="confidential_term", object_id=term_id, detail={})
    await session.commit()


# --- brand assets ------------------------------------------------------------------

MAX_ACTIVE_ASSETS = 50

@router.get("/brand-assets", response_model=list[BrandAssetOut])
async def list_assets(session: Session, user: CurrentUser) -> list[BrandAsset]:
    rows = (await session.scalars(
        select(BrandAsset).where(BrandAsset.workspace_id == user.workspace_id).order_by(BrandAsset.id))).all()
    return [a for a in rows if can_read(user, a.tier)]


@router.post("/brand-assets", response_model=BrandAssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(body: BrandAssetIn, session: Session, admin: Admin) -> BrandAsset:
    """Register official artwork. It becomes ground truth for every review:
    content is compared against it, and parts it does not show are unapproved."""
    try:
        raw = decode_b64(body.data_base64, MAX_IMAGE_BYTES)
        if not sniff(raw).startswith("image/"):
            raise MediaError("not an image")
        img = open_image(raw)
        why = asset_match.check_registrable(img)
        if why:
            raise MediaError(why)
    except MediaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"asset image: {exc}") from None
    # Every active asset is matched against every image of every review.
    active = await session.scalar(select(func.count()).select_from(BrandAsset).where(
        BrandAsset.workspace_id == admin.workspace_id, BrandAsset.active))
    if active >= MAX_ACTIVE_ASSETS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{MAX_ACTIVE_ASSETS} active assets is the limit; retire one first")
    prepared = await asyncio.to_thread(asset_match.prepare, 0, img)
    asset = BrandAsset(workspace_id=admin.workspace_id, created_by=admin.id, **body.model_dump())
    session.add(asset)
    await session.flush()
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="asset.created",
                 object_type="brand_asset", object_id=asset.id,
                 detail={"name": body.name, "kind": body.kind, "part": body.part, "tier": body.tier,
                         "retired": body.retired})
    await session.commit()
    if asset_match.flat(prepared):
        asset.warning = ("flat artwork with little texture: it will be found in content only at its own "
                         "orientation (not rotated or in perspective)")
    return asset


@router.get("/brand-assets/{asset_id}/image")
async def asset_image(asset_id: int, session: Session, user: CurrentUser) -> Response:
    asset = await session.get(BrandAsset, asset_id)
    if asset is None or asset.workspace_id != user.workspace_id or not can_read(user, asset.tier):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset not found")
    return Response(base64.b64decode(asset.data_base64), media_type=asset.media_type,
                    # Revalidated every time: one browser can switch between accounts with different clearances.
                    headers={"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"})


@router.patch("/brand-assets/{asset_id}", response_model=BrandAssetOut)
async def update_asset(asset_id: int, body: BrandAssetPatch, session: Session, admin: Admin) -> BrandAsset:
    asset = await session.get(BrandAsset, asset_id)
    if asset is None or asset.workspace_id != admin.workspace_id or not asset.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset not found")
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(asset, key, value)
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}",
                 action="asset.version_retired" if changes.get("retired") else "asset.updated",
                 object_type="brand_asset", object_id=asset.id, detail=changes)
    await session.commit()
    return asset


@router.delete("/brand-assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retire_asset(asset_id: int, session: Session, admin: Admin) -> None:
    asset = await session.get(BrandAsset, asset_id)
    if asset is None or asset.workspace_id != admin.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset not found")
    # Taken out of the library (no longer matched), not deleted: past reviews cite it. The audit action
    # keeps its old name; a version that should still be caught in posts is PATCHed retired instead.
    asset.active = False
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="asset.retired",
                 object_type="brand_asset", object_id=asset.id, detail={})
    await session.commit()
