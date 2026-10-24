"""First steps: what a newly signed-up company has set up so far, and a sample brand kit to try it with.

The checklist is computed from the workspace itself, never stored, so it can't drift from what is really
there: a step is done because the library holds a rule, a creator has joined, a piece was reviewed. Each
role gets the steps it can take; a brand admin cannot submit a piece, so their step is inviting a creator.

The sample kit is the Kitepath library from the showcase (a fictional edtech company): its rules, facts,
confidential terms, public contacts and artwork, created through the library's own endpoints so every
validation, audit entry and asset check applies exactly as if an admin had typed them in. It is offered
only to a workspace with nothing of its own yet, so it never mixes into a real brand's library.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from verytas.api.deps import CurrentUser, Session, require
from verytas.api.governance import add_contact
from verytas.api.knowledge import create_asset, create_fact, create_rule, create_term
from verytas.models import (
    BrandAsset,
    ChatThread,
    ConfidentialTerm,
    Content,
    ContentVersion,
    Decision,
    Fact,
    Review,
    Role,
    Rule,
    RuleStatus,
    User,
    Workspace,
    utcnow,
)
from verytas.schemas import BrandAssetIn, ContactIn, FactIn, RuleIn, TermIn
from verytas.security.audit import append

router = APIRouter(tags=["onboarding"])

Admin = Annotated[User, Depends(require(Role.brand_admin))]
SAMPLE_BRAND = "Kitepath"
# One load at a time per workspace: a double click must not race two kits into one library.
_LOADING: dict[int, asyncio.Lock] = {}


class Step(BaseModel):
    key: str
    title: str
    detail: str
    done: bool
    href: str | None = None


class OnboardingOut(BaseModel):
    role: Role
    company: str
    self_serve: bool
    steps: list[Step]
    # Offered to a brand admin whose library has nothing of its own yet.
    sample_kit: bool


class SampleKitOut(BaseModel):
    rules: int
    facts: int
    terms: int
    contacts: int
    assets: int


async def _count(session, model, *where) -> int:
    return await session.scalar(select(func.count()).select_from(model).where(*where)) or 0


async def _library(session, ws: int) -> dict[str, int]:
    return {"rules": await _count(session, Rule, Rule.workspace_id == ws, Rule.system.is_(False)),
            "facts": await _count(session, Fact, Fact.workspace_id == ws),
            "terms": await _count(session, ConfidentialTerm, ConfidentialTerm.workspace_id == ws),
            "assets": await _count(session, BrandAsset, BrandAsset.workspace_id == ws)}


async def _reviewed(session, ws: int, author: int | None = None) -> int:
    stmt = (select(func.count()).select_from(Review).join(ContentVersion, Review.version_id == ContentVersion.id)
            .join(Content, ContentVersion.content_id == Content.id).where(Content.workspace_id == ws))
    if author is not None:
        stmt = stmt.where(Content.created_by == author)
    return await session.scalar(stmt) or 0


async def _decided(session, user: User) -> int:
    return await _count(session, Decision, Decision.actor_id == user.id)


async def _admin_steps(session, user: User, lib: dict[str, int]) -> list[Step]:
    ws = user.workspace_id
    creators = await _count(session, User, User.workspace_id == ws, User.role == Role.creator)
    return [
        Step(key="material", title="Hand over your brand material",
             detail="Drop in a brand book, a price sheet or a logo. Verytas reads it and drafts rules, facts and "
                    "terms; nothing is added until you approve it.",
             done=lib["rules"] > 0, href="/library?tab=import"),
        Step(key="facts", title="Add the facts posts may quote",
             detail="Prices, counts and dates with their source, so a wrong number in a post is caught.",
             done=lib["facts"] > 0, href="/library?tab=facts"),
        Step(key="terms", title="List your confidential codenames",
             detail="Unreleased product names and deals. They are never sent to a hosted model, and a post that "
                    "mentions one is blocked.",
             done=lib["terms"] > 0, href="/library?tab=terms"),
        Step(key="assets", title="Register your logo and artwork",
             detail="Images in posts are compared with these: stretched, recoloured, mirrored or retired marks.",
             done=lib["assets"] > 0, href="/library?tab=assets"),
        Step(key="creator", title="Invite a creator",
             detail="Creators join with your company's join code (in Settings) and submit pieces for review.",
             done=creators > 0, href=None),
        Step(key="review", title="See a first piece reviewed",
             detail="Once a creator submits, the review appears in your queue with every finding explained.",
             done=await _reviewed(session, ws) > 0, href="/review?queue=all"),
    ]


def _ask(asked: bool, detail: str) -> Step:
    return Step(key="ask", title="Ask Verytas", detail=detail, done=asked, href="/ask")


async def _creator_steps(session, user: User, asked: bool) -> list[Step]:
    mine = await _reviewed(session, user.workspace_id, user.id)
    fixed = await _count(session, ContentVersion, ContentVersion.content_id.in_(
        select(Content.id).where(Content.workspace_id == user.workspace_id, Content.created_by == user.id)),
        ContentVersion.version_no > 1)
    return [
        Step(key="submit", title="Submit a first piece",
             detail="Paste a caption or a post and add images, a PDF or a video. The pre-check takes under a minute.",
             done=mine > 0, href="/review"),
        Step(key="fix", title="Fix what it found",
             detail="Each finding says which guideline it breaks and offers a fix you can accept or edit. "
                    "Resubmitting checks the new version.",
             done=fixed > 0, href="/review"),
        _ask(asked, "Before you write, ask what the guidelines say about a topic; answers quote their source."),
    ]


async def _team_steps(session, user: User, asked: bool) -> list[Step]:
    steps = [_ask(asked, "Ask what a guideline means or why a piece was flagged; answers quote their source.")]
    if user.role in (Role.reviewer, Role.approver):
        steps.insert(0, Step(
            key="decide", title="Decide on a finding",
            detail="Open the queue, then uphold a finding or dismiss it with a reason. Dismissals show which "
                   "guidelines read unclearly.", done=await _decided(session, user) > 0, href="/review"))
    return steps


@router.get("/onboarding", response_model=OnboardingOut)
async def onboarding(session: Session, user: CurrentUser) -> OnboardingOut:
    ws = await session.get(Workspace, user.workspace_id)
    lib = await _library(session, user.workspace_id)
    asked = await _count(session, ChatThread, ChatThread.user_id == user.id) > 0
    if user.role is Role.brand_admin:
        steps = await _admin_steps(session, user, lib)
    elif user.role is Role.creator:
        steps = await _creator_steps(session, user, asked)
    else:
        steps = await _team_steps(session, user, asked)
    return OnboardingOut(role=user.role, company=ws.name, self_serve=bool(ws.self_serve), steps=steps,
                         sample_kit=user.role is Role.brand_admin and not any(lib.values()))


@router.post("/onboarding/sample-kit", response_model=SampleKitOut, status_code=status.HTTP_201_CREATED)
async def sample_kit(session: Session, admin: Admin) -> SampleKitOut:
    async with _LOADING.setdefault(admin.workspace_id, asyncio.Lock()):
        if any((await _library(session, admin.workspace_id)).values()):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "the sample kit loads only into an empty library, so it never mixes with your own")
        return await _load_kit(session, admin)


async def _load_kit(session, admin: User) -> SampleKitOut:
    from verytas.showcase import art, kitepath

    today = utcnow().date()
    made = SampleKitOut(rules=0, facts=0, terms=0, contacts=0, assets=0)
    for spec in kitepath.RULES:
        rule = await create_rule(RuleIn.model_validate({"tier": "public", **spec}), session, admin)
        rule.status = RuleStatus.active
        await session.commit()
        made.rules += 1
    # The showcase dates facts in days from today. A fact that supersedes another names that one's key, and
    # the list is in time order, so the older fact already exists.
    fact_ids: dict[str, int] = {}
    for spec in kitepath.FACTS:
        body = {k: v for k, v in spec.items() if k not in ("key", "supersedes", "from", "to")}
        body |= {"tier": "public", "valid_from": today + timedelta(days=spec["from"])}
        if spec.get("to") is not None:
            body["valid_to"] = today + timedelta(days=spec["to"])
        if spec.get("supersedes"):
            body["supersedes_id"] = fact_ids[spec["supersedes"]]
        fact = await create_fact(FactIn.model_validate(body), session, admin)
        fact_ids[spec.get("key", spec["statement"])] = fact.id
        made.facts += 1
    for spec in kitepath.TERMS:
        body = {"term": spec["term"], "note": spec.get("note")}
        if spec.get("embargo") is not None:
            body["embargo_until"] = today + timedelta(days=spec["embargo"])
        await create_term(TermIn.model_validate(body), session, admin)
        made.terms += 1
    for spec in kitepath.CONTACTS:
        await add_contact(ContactIn.model_validate(spec), session, admin)
        made.contacts += 1
    for spec in kitepath.ARTWORK:
        body = {k: v for k, v in spec.items() if k != "image"}
        await create_asset(BrandAssetIn.model_validate(
            {**body, "media_type": "image/png", "data_base64": art.b64(spec["image"]())}), session, admin)
        made.assets += 1
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="workspace.sample_kit",
                 object_type="workspace", object_id=admin.workspace_id,
                 detail={"brand": SAMPLE_BRAND, **made.model_dump()})
    await session.commit()
    return made
