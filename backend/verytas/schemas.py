"""Request and response bodies for the HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from verytas.models import (
    ContentStatus,
    DecisionAction,
    Level,
    ReviewStatus,
    Role,
    RuleKind,
    RuleStatus,
    Severity,
    Tier,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- identity -------------------------------------------------------------------

class BootstrapIn(BaseModel):
    workspace_name: str = Field(min_length=1, max_length=200)
    admin_email: EmailStr
    admin_name: str = Field(min_length=1, max_length=200)


class UserIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    role: Role
    clearance: Tier = Tier.internal


class UserOut(ORM):
    id: int
    email: str
    name: str
    role: Role
    clearance: Tier


class TokenOut(BaseModel):
    user: UserOut
    token: str = Field(description="Shown once. Send as 'Authorization: Bearer <token>'.")


# --- knowledge base ----------------------------------------------------------------

class RuleIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9-]{1,39}$")
    category: Literal["tone", "terminology", "messaging", "visual", "accessibility", "legal", "claims",
                      "confidentiality"]
    kind: RuleKind
    severity: Severity = Severity.should
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    good_examples: list[str] = []
    bad_examples: list[str] = []
    pattern: dict[str, Any] = {}
    source_ref: str | None = None
    tier: Tier = Tier.internal

    @model_validator(mode="after")
    def deterministic_rules_need_a_matcher(self) -> RuleIn:
        if self.kind is RuleKind.deterministic and "type" not in self.pattern:
            raise ValueError("deterministic rules need pattern.type (e.g. banned_terms, preferred_terms, palette)")
        return self


class RulePatch(BaseModel):
    title: str | None = None
    text: str | None = None
    severity: Severity | None = None
    good_examples: list[str] | None = None
    bad_examples: list[str] | None = None
    pattern: dict[str, Any] | None = None
    status: RuleStatus | None = None


class RuleOut(ORM):
    id: int
    code: str
    version: int
    category: str
    kind: RuleKind
    severity: Severity
    title: str
    text: str
    good_examples: list[str]
    bad_examples: list[str]
    pattern: dict[str, Any]
    source_ref: str | None
    tier: Tier
    status: RuleStatus
    system: bool


class FactIn(BaseModel):
    statement: str = Field(min_length=1)
    value: float | None = None
    unit: str | None = None
    subject: str | None = None
    source_ref: str = Field(min_length=1)
    tier: Tier = Tier.internal
    valid_from: date
    valid_to: date | None = None
    supersedes_id: int | None = None

    @model_validator(mode="after")
    def window_moves_forward(self) -> FactIn:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class FactOut(ORM):
    id: int
    statement: str
    value: float | None
    unit: str | None
    subject: str | None
    source_ref: str
    tier: Tier
    valid_from: date
    valid_to: date | None
    supersedes_id: int | None
    approved: bool


class TermIn(BaseModel):
    term: str = Field(min_length=2, max_length=200)
    note: str | None = None
    embargo_until: date | None = None


class TermOut(ORM):
    id: int
    term: str
    note: str | None
    embargo_until: date | None


# --- content and reviews -------------------------------------------------------

class ImageIn(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    alt: str | None = None
    decorative: bool = False
    media_type: Literal["image/png", "image/jpeg", "image/webp"] = "image/png"
    data_base64: str | None = Field(default=None, max_length=8_000_000)


class ColorPairIn(BaseModel):
    fg: str
    bg: str
    where: str | None = None
    large: bool = False


class AttachmentsIn(BaseModel):
    images: list[ImageIn] = []
    colors: list[ColorPairIn] = []


class ContentIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    channel: str = Field(default="general", max_length=60)
    tier: Tier = Tier.internal
    body: str = Field(min_length=1, max_length=100_000)
    attachments: AttachmentsIn = AttachmentsIn()


class VersionIn(BaseModel):
    body: str = Field(min_length=1, max_length=100_000)
    attachments: AttachmentsIn | None = None


class VersionOut(ORM):
    id: int
    version_no: int
    parent_id: int | None
    body: str
    created_by: int
    created_at: datetime


class ContentOut(ORM):
    id: int
    title: str
    channel: str
    tier: Tier
    status: ContentStatus
    created_by: int
    created_at: datetime


class ContentDetail(ContentOut):
    versions: list[VersionOut]
    latest_review_id: int | None = None


class SuggestionOut(ORM):
    id: int
    original: str
    proposed: str
    rationale: str
    intent_preserved: float | None
    model: str | None


class DecisionOut(ORM):
    id: int
    actor_id: int
    action: DecisionAction
    reason_code: str | None
    reason_text: str | None
    edited_text: str | None
    created_at: datetime


class CitationOut(BaseModel):
    kind: Literal["rule", "fact"]
    id: int
    label: str
    source: str | None


class FindingOut(ORM):
    id: int
    unit_id: str
    category: str
    level: Level
    title: str
    explanation: str
    quote: str | None
    span_start: int | None
    span_end: int | None
    confidence: float
    checker: str
    model: str | None
    citations: list[CitationOut] = []
    suggestions: list[SuggestionOut] = []
    decisions: list[DecisionOut] = []
    signature_valid: bool = False


class ReviewOut(ORM):
    id: int
    version_id: int
    status: ReviewStatus
    summary: dict[str, Any]
    coverage: dict[str, Any]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    findings: list[FindingOut] = []


class SubmitOut(BaseModel):
    content: ContentOut
    version: VersionOut
    review_id: int


class DecisionIn(BaseModel):
    action: DecisionAction
    suggestion_id: int | None = None
    reason_code: Literal["false_positive", "not_applicable", "guideline_unclear", "intentional", "other"] | None = None
    reason_text: str | None = Field(default=None, max_length=2000)
    edited_text: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def reasons_for_overrides(self) -> DecisionIn:
        # Rejections are the raw material for the ambiguity detector; a
        # rejection without a reason teaches it nothing.
        if self.action is DecisionAction.rejected and self.reason_code is None:
            raise ValueError("rejecting a finding needs a reason_code")
        if self.action is DecisionAction.edited and not self.edited_text:
            raise ValueError("an edited decision needs edited_text")
        return self


class TransitionIn(BaseModel):
    to: ContentStatus
    note: str | None = Field(default=None, max_length=2000)
    override_blockers: bool = False


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    version_id: int | None = None
    parent_id: int | None = None
    span_start: int | None = None
    span_end: int | None = None


class CommentOut(ORM):
    id: int
    version_id: int | None
    parent_id: int | None
    actor_id: int
    body: str
    span_start: int | None
    span_end: int | None
    created_at: datetime


class AuditOut(ORM):
    id: int
    actor: str
    action: str
    object_type: str
    object_id: str | None
    detail: dict[str, Any]
    created_at: datetime
    hash: str
