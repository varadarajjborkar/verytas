"""Request and response bodies for the HTTP API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator, model_validator

from verytas.checks.patterns import validate_pattern
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


class UTCModel(BaseModel):
    """Times leave the API marked as UTC. SQLite returns them without a zone,
    and a browser would read a zone-less time as local, hours off."""

    @field_serializer("*", mode="wrap")
    def _utc(self, value: Any, handler: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return handler(value)


class ORM(UTCModel):
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


class PersonOut(ORM):
    """A colleague as anyone in the workspace sees them: enough to put a name on an action."""

    id: int
    name: str
    role: Role


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
    def pattern_matches_its_matcher(self) -> RuleIn:
        self.pattern = validate_pattern(self.kind.value, self.pattern)
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
    event_id: int | None = None


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
    note: str | None = Field(default=None, max_length=2000)
    embargo_until: date | None = None

    @field_validator("term")
    @classmethod
    def _matchable(cls, v: str) -> str:
        from verytas.security.terms import fold

        # Matching runs on folded text; a term with no letters or digits left
        # after folding (dashes, emoji, invisible characters) can never match.
        if sum(ch.isalnum() for ch in fold(v, "drop")[0]) < 2:
            raise ValueError("a confidential term needs at least two letters or digits")
        return v


class TermPatch(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
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
    media_type: Literal["image/png", "image/jpeg", "image/webp", "image/gif"] = "image/png"
    data_base64: str | None = Field(default=None, max_length=8_000_000)
    blob_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class ColorPairIn(BaseModel):
    fg: str = Field(pattern=r"^#?(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
    bg: str = Field(pattern=r"^#?(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
    where: str | None = None
    large: bool = False


class DocumentIn(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str | None = Field(default=None, max_length=200)
    media_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ] = "application/pdf"
    # About 20 MB of file once decoded. Real type is checked from the bytes.
    data_base64: str | None = Field(default=None, max_length=28_000_000)
    blob_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")

    @model_validator(mode="after")
    def has_payload(self) -> DocumentIn:
        if not (self.data_base64 or self.blob_id):
            raise ValueError("a document needs data_base64 or a blob_id from POST /media")
        return self


class VideoIn(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str | None = Field(default=None, max_length=200)
    blob_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class AttachmentsIn(BaseModel):
    images: list[ImageIn] = Field(default=[], max_length=20)
    colors: list[ColorPairIn] = []
    documents: list[DocumentIn] = Field(default=[], max_length=5)
    videos: list[VideoIn] = Field(default=[], max_length=3)


class CreatorNotesIn(BaseModel):
    """The creator's own account of the content. Optional, untrusted, and never read by
    the checks: Prism weighs it only after findings exist (prism/intent.py)."""

    intent: str | None = Field(default=None, max_length=2000,
                               description="What the content means to say, especially if it could be misread")
    irregularity: str | None = Field(default=None, max_length=2000,
                                     description="Why the upload is unusually large or long, if it is")
    ai_used: bool | None = Field(default=None, description="Was generative AI used to make any part of it?")
    language: str | None = Field(default=None, max_length=60,
                                 description="Language or dialect the audience reads it in, e.g. Hinglish")
    brief: str | None = Field(default=None, max_length=4000, description=(
        "What is in the images or video, in the creator's words: characters, people, products, and roughly "
        "when they appear. Required with a video (or a voice note instead)."))
    brief_audio_blob_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$",
                                            description="A voice note saying the same, uploaded with POST /media")


class ContentIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    # Free text on purpose: "Other" in the UI lets creators name any app.
    channel: str = Field(default="general", min_length=1, max_length=60)
    tier: Tier = Tier.internal
    body: str = Field(min_length=1, max_length=100_000)
    attachments: AttachmentsIn = AttachmentsIn()
    creator_notes: CreatorNotesIn = CreatorNotesIn()
    event_id: int | None = Field(default=None, description="The brand event this piece is for, if any")


class VersionIn(BaseModel):
    body: str = Field(min_length=1, max_length=100_000)
    attachments: AttachmentsIn | None = None
    creator_notes: CreatorNotesIn | None = None


class PrecheckIn(BaseModel):
    channel: str = Field(default="general", min_length=1, max_length=60)
    body: str = Field(default="", max_length=100_000)
    attachments: AttachmentsIn = AttachmentsIn()


class MediaOut(BaseModel):
    id: str
    media_type: str
    name: str | None
    bytes: int
    sha256: str
    metrics: dict[str, Any] = {}


class ImageRefOut(BaseModel):
    id: str
    alt: str | None = None
    decorative: bool = False
    media_type: str = "image/png"


class VersionOut(ORM):
    id: int
    version_no: int
    parent_id: int | None
    body: str
    created_by: int
    created_at: datetime
    images: list[ImageRefOut] = []


class ContentOut(ORM):
    id: int
    title: str
    channel: str
    tier: Tier
    status: ContentStatus
    created_by: int
    created_at: datetime
    event_id: int | None = None


class LatestReview(UTCModel):
    id: int
    status: str
    overall: float | None = None
    blockers: int = 0
    warnings: int = 0
    advisories: int = 0
    finished_at: datetime | None = None


class ContentListItem(ContentOut):
    """A row in a review history list: where the piece stands, at a glance."""

    version_count: int = 0
    updated_at: datetime | None = None
    status_since: datetime | None = Field(default=None, description="When it entered its current status")
    latest_review: LatestReview | None = None
    open_escalations: int = 0
    rechecked_for_event: int | None = Field(default=None, description="Event whose change last re-checked it")


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
    source: str = "body"
    locator: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
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
    media_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:@-]{1,64}$",
                                 description="The image or video of the version the comment is pinned to")
    time_start: float | None = Field(default=None, ge=0, le=86_400, description="Seconds into the video")
    time_end: float | None = Field(default=None, ge=0, le=86_400)
    box: list[float] | None = Field(default=None, min_length=4, max_length=4,
                                    description="x0, y0, x1, y1 as fractions of the frame")

    @model_validator(mode="after")
    def _pin(self) -> CommentIn:
        if (self.time_start is not None or self.box is not None) and (self.media_id is None or self.version_id is None):
            raise ValueError("a moment or an area is pinned to a media_id of a version_id")
        if self.time_end is not None and (self.time_start is None or self.time_end < self.time_start):
            raise ValueError("time_end needs a time_start before it")
        if self.box is not None:
            x0, y0, x1, y1 = self.box
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError("box is x0, y0, x1, y1 within 0..1, with x0 < x1 and y0 < y1")
        return self


class CommentOut(ORM):
    id: int
    version_id: int | None
    parent_id: int | None
    actor_id: int
    body: str
    span_start: int | None
    span_end: int | None
    media_id: str | None = None
    time_start: float | None = None
    time_end: float | None = None
    box: list[float] | None = None
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


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    kind: Literal["celebrity", "ambassador", "creator", "staff", "other"]
    channels: list[str] = Field(default_factory=list, max_length=20, description="Empty means every channel")
    event_ids: list[int] = Field(default_factory=list, max_length=20, description="Empty means every campaign")
    valid_from: date
    valid_to: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    tier: Tier = Tier.internal

    @model_validator(mode="after")
    def _window(self) -> PersonIn:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class PersonPatch(BaseModel):
    aliases: list[str] | None = Field(default=None, max_length=10)
    channels: list[str] | None = Field(default=None, max_length=20)
    event_ids: list[int] | None = Field(default=None, max_length=20)
    valid_to: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    active: bool | None = None


class ReferenceIn(BaseModel):
    media_type: Literal["image/png", "image/jpeg", "image/webp"] = "image/jpeg"
    data_base64: str = Field(min_length=16, max_length=8_000_000)
    source: Literal["upload", "web"] = "upload"
    source_url: str | None = Field(default=None, max_length=500, pattern=r"^https://")


class ReferenceOut(ORM):
    id: int
    media_type: str
    source: str
    source_url: str | None
    created_at: datetime


class ApprovedPersonOut(ORM):
    id: int
    name: str
    aliases: list[str]
    kind: str
    user_id: int | None
    channels: list[str]
    event_ids: list[int]
    valid_from: date
    valid_to: date | None
    notes: str | None
    tier: Tier
    active: bool
    created_at: datetime
    references: list[ReferenceOut] = []


class BrandAssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["logo", "mascot", "other"]
    part: Literal["full", "face", "head", "body", "wordmark", "icon"] = "full"
    media_type: Literal["image/png", "image/jpeg", "image/webp"] = "image/png"
    data_base64: str = Field(min_length=16, max_length=8_000_000)
    wordmark: str | None = Field(default=None, max_length=120, description="Exact spelling of text in the artwork")
    notes: str | None = Field(default=None, max_length=2000)
    tier: Tier = Tier.public


class BrandAssetOut(ORM):
    id: int
    name: str
    kind: str
    part: str
    wordmark: str | None
    media_type: str
    notes: str | None
    tier: Tier
    active: bool
    created_at: datetime
    # Set on registration only: how the artwork will be matched, when that is weaker than usual.
    warning: str | None = None


class DisputeIn(BaseModel):
    claim: str = Field(min_length=10, max_length=2000,
                       description="Why this is not what the finding says, e.g. what the phrase means in context")
    language: str | None = Field(default=None, max_length=60)


class DisputeOut(ORM):
    id: int
    finding_id: int
    content_id: int
    status: str
    claim: str
    language: str | None
    verdict: dict[str, Any]
    created_at: datetime
    decided_at: datetime | None


class ResubmitIn(BaseModel):
    """One round trip from the checklist: apply chosen fixes, record what was done by hand,
    dispute what was misread, optionally replace the text, and run everything again."""

    body: str | None = Field(default=None, min_length=1, max_length=100_000)
    apply: list[int] = Field(default=[], max_length=200, description="Finding ids whose suggested fix to apply")
    resolved: list[int] = Field(default=[], max_length=200, description="Finding ids the creator fixed by hand")
    disputes: list[DisputeItem] = Field(default=[], max_length=50)
    creator_notes: CreatorNotesIn | None = None
    attachments: AttachmentsIn | None = None


class DisputeItem(BaseModel):
    finding_id: int
    claim: str = Field(min_length=10, max_length=2000)
    language: str | None = Field(default=None, max_length=60)


class ResubmitOut(BaseModel):
    submit: SubmitOut
    disputes: list[int]
    applied: int
    skipped: list[str]


class AiEditIn(BaseModel):
    instruction: str = Field(min_length=3, max_length=2000)


class AiEditOut(BaseModel):
    body: str
    changes: list[str]
    remaining: list[str]
    model: str


# --- the brand team's inbox, events and public contacts ----------------------------------

ContactKind = Literal["phone", "email", "handle", "url"]


class ContactIn(BaseModel):
    kind: ContactKind
    value: str = Field(min_length=3, max_length=200,
                       description="An email, or *@domain to list a whole company domain")
    label: str | None = Field(default=None, max_length=120)
    source_ref: str | None = Field(default=None, max_length=300)


class ContactOut(ORM):
    id: int
    kind: str
    value: str
    normalized: str
    label: str | None
    source_ref: str | None
    active: bool


EventKind = Literal["launch", "campaign", "sale", "crisis", "partnership", "other"]


class EventIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    kind: EventKind = "campaign"
    starts_on: date
    ends_on: date | None = None
    summary: str = Field(default="", max_length=4000)
    guidance: str = Field(default="", max_length=4000, description="What posts should and shouldn't say while it runs")
    hashtags: list[str] = Field(default=[], max_length=20)
    avoid_terms: list[str] = Field(default=[], max_length=200)
    blackout: bool = False
    tier: Tier = Tier.public

    @field_validator("hashtags", "avoid_terms")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out = []
        for t in v:
            t = t.strip()
            if t and len(t) <= 100 and t not in out:
                out.append(t)
        return out

    @model_validator(mode="after")
    def _window(self) -> EventIn:
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class EventPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    kind: EventKind | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    summary: str | None = Field(default=None, max_length=4000)
    guidance: str | None = Field(default=None, max_length=4000)
    hashtags: list[str] | None = Field(default=None, max_length=20)
    avoid_terms: list[str] | None = Field(default=None, max_length=200)
    blackout: bool | None = None


class EventOut(ORM):
    id: int
    name: str
    kind: str
    starts_on: date
    ends_on: date | None
    summary: str
    guidance: str
    hashtags: list[str]
    avoid_terms: list[str]
    blackout: bool
    status: str
    tier: Tier
    revision: int
    updated_at: datetime
    live: bool = False
    rules: list[str] = []
    pieces: int = 0
    rechecked: list[int] = []


class EscalationIn(BaseModel):
    message: str = Field(min_length=10, max_length=2000,
                         description="Why this finding is wrong or needs a person, in the creator's words")


class EscalationResolveIn(BaseModel):
    outcome: Literal["upheld", "cleared"]
    reason_code: Literal["false_positive", "not_applicable", "guideline_unclear", "intentional", "other"] | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _reason_to_clear(self) -> EscalationResolveIn:
        # Clearing is a dismissal: guideline health learns from its reason, so one is required.
        if self.outcome == "cleared" and self.reason_code is None:
            raise ValueError("clearing a finding needs a reason_code")
        return self
