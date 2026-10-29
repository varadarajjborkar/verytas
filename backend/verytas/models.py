"""Relational model. Maps to architecture section 11.

Integrity rules from the design board are enforced in the schema, not just in
code, so a bug in a worker can't produce an uncited finding or a dangling
version chain.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from verytas.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Tier(enum.StrEnum):
    """Security label carried by every record (architecture section 3)."""

    public = "public"
    internal = "internal"
    confidential = "confidential"

    @property
    def rank(self) -> int:
        return {"public": 0, "internal": 1, "confidential": 2}[self.value]


class Role(enum.StrEnum):
    creator = "creator"
    reviewer = "reviewer"
    approver = "approver"
    brand_admin = "brand_admin"
    auditor = "auditor"


class RuleKind(enum.StrEnum):
    deterministic = "deterministic"  # compiled to matchers, no model involved
    semantic = "semantic"  # judged by Jev against the rule text and examples


class RuleStatus(enum.StrEnum):
    draft = "draft"
    active = "active"
    retired = "retired"


class Severity(enum.StrEnum):
    must = "must"  # can become a blocker
    should = "should"
    may = "may"


class ContentStatus(enum.StrEnum):
    draft = "draft"
    in_review = "in_review"
    changes_requested = "changes_requested"
    approved = "approved"
    published = "published"
    withdrawn = "withdrawn"


class ReviewStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Level(enum.StrEnum):
    """What a finding means for the creator (architecture section 8.1)."""

    blocker = "blocker"
    warning = "warning"
    advisory = "advisory"


class DecisionAction(enum.StrEnum):
    accepted = "accepted"
    rejected = "rejected"
    edited = "edited"
    escalated = "escalated"


def _enum(e: type[enum.Enum]) -> Enum:
    # Store values as plain strings so the DB stays readable and portable.
    return Enum(e, native_enum=False, length=32, values_callable=lambda x: [m.value for m in x])


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Workspaces made by someone signing up on the public demo (api/accounts.py), as against seeded or
    # bootstrapped ones. Their creators join with the join code their admin was given.
    self_serve: Mapped[bool | None] = mapped_column(default=False, nullable=True)
    join_code: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(_enum(Role))
    # Highest tier this person may read; brand admins usually get confidential.
    clearance: Mapped[Tier] = mapped_column(_enum(Tier), default=Tier.internal)
    # Only the SHA-256 of the bearer token is stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Only for accounts made by signing up; everyone else signs in with a token. scrypt (api/accounts.py).
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # When a password account's current token was issued (api/accounts.py); it lapses after
    # Settings.account_token_days. None for token-only accounts.
    token_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When this person agreed that Inki may read a conversation they bring it into (api/messages.py).
    inki_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersonalToken(Base):
    """A token a person hands to their own AI client so it can use the /mcp endpoint as them (api/tokens.py).

    A separate table from User.token_hash on purpose: the web session token and this one are different
    audiences, and neither lookup can ever find the other's hash. Only the SHA-256 is stored; `prefix` is the
    start of the random part, kept so a person can tell their tokens apart in a list.
    """

    __tablename__ = "personal_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(8))
    # A subset of ["read", "write"] that always includes "read".
    scopes: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["read"])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("workspace_id", "code", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))  # e.g. VOICE-03
    version: Mapped[int] = mapped_column(Integer, default=1)
    # tone | terminology | messaging | visual | accessibility | legal | claims | confidentiality
    category: Mapped[str] = mapped_column(String(40))
    kind: Mapped[RuleKind] = mapped_column(_enum(RuleKind))
    severity: Mapped[Severity] = mapped_column(_enum(Severity), default=Severity.should)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    good_examples: Mapped[list[str]] = mapped_column(JSON, default=list)
    bad_examples: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Matcher config for deterministic rules (terms, replacements, thresholds, palette).
    pattern: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_ref: Mapped[str | None] = mapped_column(String(300))  # "Brand book v3, p.12"
    tier: Mapped[Tier] = mapped_column(_enum(Tier), default=Tier.internal)
    status: Mapped[RuleStatus] = mapped_column(_enum(RuleStatus), default=RuleStatus.draft)
    system: Mapped[bool] = mapped_column(default=False)  # built-in (WCAG, confidentiality)
    # Set on rules a brand event generates; they apply while the event runs, or to pieces tagged with it.
    event_id: Mapped[int | None] = mapped_column(ForeignKey("brand_events.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="fact_validity_window"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    statement: Mapped[str] = mapped_column(Text)  # "Verytas is used by 800+ teams"
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(40))
    subject: Mapped[str | None] = mapped_column(String(120))  # what the number measures: "teams"
    source_ref: Mapped[str] = mapped_column(String(300))
    tier: Mapped[Tier] = mapped_column(_enum(Tier), default=Tier.internal)
    # The board's "timeline of events chain": a fact is only true inside its window.
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id"))
    approved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def valid_on(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day < self.valid_to)


class ConfidentialTerm(Base):
    __tablename__ = "confidential_terms"
    __table_args__ = (UniqueConstraint("workspace_id", "term"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    term: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(String(300))
    # After this date the term may be published; until then it must not leak.
    embargo_until: Mapped[date | None] = mapped_column(Date)


class Content(Base):
    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    channel: Mapped[str] = mapped_column(String(60), default="general")  # blog|linkedin|x|email|...
    tier: Mapped[Tier] = mapped_column(_enum(Tier), default=Tier.internal)
    status: Mapped[ContentStatus] = mapped_column(_enum(ContentStatus), default=ContentStatus.draft)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # The brand event this piece is for (a launch, a sale): its brief and hashtags apply to it.
    event_id: Mapped[int | None] = mapped_column(ForeignKey("brand_events.id"), index=True)

    versions: Mapped[list[ContentVersion]] = relationship(
        back_populates="content", order_by="ContentVersion.version_no"
    )


class ContentVersion(Base):
    """One link in the raw -> first cite -> corrected chain."""

    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("content_id", "version_no"),
        # Only the first version may lack a parent, and it must lack one, so the
        # chain can never dangle ("bounds it from having null on the other end").
        CheckConstraint(
            "(version_no = 1 AND parent_id IS NULL) OR (version_no > 1 AND parent_id IS NOT NULL)",
            name="version_chain_closed",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("content_versions.id"))
    body: Mapped[str] = mapped_column(Text)
    # Non-text parts of the bundle: images (as asset refs + alt text), colours, links.
    attachments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # What the creator says about the content: intended meaning, why an
    # irregular upload is the way it is, whether AI was used. Kept apart from
    # the content on purpose: no check ever reads it. Prism consults it only
    # after findings exist, and never as evidence on its own (prism/intent.py).
    creator_notes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    content: Mapped[Content] = relationship(back_populates="versions")

    @property
    def images(self) -> list[dict[str, Any]]:
        """The attached images as references (id, alt text, type), never their bytes: the bytes are served
        one at a time by GET /contents/{id}/versions/{version_id}/images/{image_id}."""
        return [{"id": i["id"], "alt": i.get("alt"), "decorative": bool(i.get("decorative")),
                 "media_type": i.get("media_type") or "image/png"}
                for i in (self.attachments or {}).get("images", []) if isinstance(i, dict) and i.get("id")]

    @property
    def videos(self) -> list[dict[str, Any]]:
        """The attached videos by id and name; the bytes are streamed in ranges by the version video route."""
        return [{"id": v["id"], "name": v.get("name")}
                for v in (self.attachments or {}).get("videos", []) if isinstance(v, dict) and v.get("id")]

    @property
    def documents(self) -> list[dict[str, Any]]:
        """The attached documents by id, name and type, so a review can title each one; never the bytes."""
        return [{"id": d["id"], "name": d.get("name"), "media_type": d.get("media_type") or "application/pdf"}
                for d in (self.attachments or {}).get("documents", []) if isinstance(d, dict) and d.get("id")]


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"), index=True)
    status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus), default=ReviewStatus.queued)
    # Per-category scores and confidence from the judge.
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Which check families ran, which were skipped and why. Never silently passes.
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    findings: Mapped[list[Finding]] = relationship(back_populates="review", order_by="Finding.id")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        # No uncited findings: every flag points at the rule or fact behind it.
        CheckConstraint("rule_id IS NOT NULL OR fact_id IS NOT NULL", name="finding_is_cited"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="finding_confidence_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"), index=True)
    # Nested sources make long ids: "doc:brochure:p3:img2:ocr/p1.s2".
    unit_id: Mapped[str] = mapped_column(String(200))
    # Where the flagged text lives: "body" for the typed draft, otherwise a
    # derived source (PDF text layer, OCR of an image or a scanned page).
    # Spans are offsets into that source's text, not into the body.
    source: Mapped[str] = mapped_column(String(160), default="body")
    # Page, image and pixel box for non-body findings, so the UI can point at them.
    locator: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # How the creator's notes or an earlier dispute bear on this finding.
    assessment: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    category: Mapped[str] = mapped_column(String(40))
    level: Mapped[Level] = mapped_column(_enum(Level))
    title: Mapped[str] = mapped_column(String(300))
    explanation: Mapped[str] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text)
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id"), index=True)
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id"))
    confidence: Mapped[float] = mapped_column(Float)
    checker: Mapped[str] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(80))  # AI disclosure: which model, if any
    signature: Mapped[str] = mapped_column(String(200))
    # Past decisions on the same rule about similar words (prism/precedent.py): context, not verdict.
    precedents: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # How often reviewers agreed with findings like this one (prism/calibration.py): {agree, n, family}.
    calibration: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Web results for an unsupported claim (prism/research.py): shown as not approved, never a verdict.
    research: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    review: Mapped[Review] = relationship(back_populates="findings")
    rule: Mapped[Rule | None] = relationship()
    fact: Mapped[Fact | None] = relationship()
    suggestions: Mapped[list[Suggestion]] = relationship(back_populates="finding")
    decisions: Mapped[list[Decision]] = relationship(back_populates="finding", order_by="Decision.id")


class Suggestion(Base):
    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), index=True)
    original: Mapped[str] = mapped_column(Text)
    proposed: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    intent_preserved: Mapped[float | None] = mapped_column(Float)  # P(meaning unchanged)
    model: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str | None] = mapped_column(String(10))  # replace | rewrite | delete (model-written fixes)

    finding: Mapped[Finding] = relationship(back_populates="suggestions")


class Decision(Base):
    """The board's "suggestion accepted True/False" table. Rows are never deleted:
    rejections are the raw material for the ambiguity detector."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), index=True)
    suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("suggestions.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[DecisionAction] = mapped_column(_enum(DecisionAction))
    # false_positive | not_applicable | guideline_unclear | intentional
    reason_code: Mapped[str | None] = mapped_column(String(40))
    reason_text: Mapped[str | None] = mapped_column(Text)
    edited_text: Mapped[str | None] = mapped_column(Text)
    # Set on a dismissal copied onto the same issue in a later check (prism/carryover.py): the call it repeats.
    # Learning reads only the original, so one call counts once.
    carried_from_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    finding: Mapped[Finding] = relationship(back_populates="decisions")


class Change(Base):
    """The board's "what exact changes" table: version-to-version diffs."""

    __tablename__ = "changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"))
    to_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"))
    diff: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), index=True)
    from_status: Mapped[ContentStatus] = mapped_column(_enum(ContentStatus))
    to_status: Mapped[ContentStatus] = mapped_column(_enum(ContentStatus))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("content_versions.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)
    # Pinned to a place in an image or video of the version: a moment or a range in seconds, and an area
    # as fractions of the frame (x0, y0, x1, y1 in 0..1), so the pin holds at any display size.
    media_id: Mapped[str | None] = mapped_column(String(64))
    time_start: Mapped[float | None] = mapped_column(Float)
    time_end: Mapped[float | None] = mapped_column(Float)
    box: Mapped[list[float] | None] = mapped_column(JSON)
    # What a manager drew on the image or the paused frame: pen strokes and text labels, in the same
    # fractions of the frame as `box` (schemas.Marks).
    marks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEntry(Base):
    """Append-only, hash-chained log (X.800 notarization + audit trail)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120))  # "user:3" or "agent:claims-worker"
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str] = mapped_column(String(40))
    object_id: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class Person(Base):
    """Someone whose face may appear in the brand's content, and on what terms: the company's own record.

    The visual checks only identify a face; this record decides whether it may be there. A celebrity or
    ambassador is allowed for the channels and campaigns their agreement covers (empty means any) and
    between its dates. A creator registers themselves, so their own face in their own posts is fine.
    """

    __tablename__ = "people"
    # One record per creator; brand-recorded people have no user and don't collide.
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    kind: Mapped[str] = mapped_column(String(20))  # celebrity | ambassador | creator | staff | other
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # a creator's own record
    channels: Mapped[list[str]] = mapped_column(JSON, default=list)
    event_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[Tier] = mapped_column(_enum(Tier), default=Tier.internal)
    active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    references: Mapped[list[PersonReference]] = relationship(
        back_populates="person", cascade="all, delete-orphan", order_by="PersonReference.id")


class PostResult(Base):
    """How a piece did once it went live: the post's link and the numbers someone recorded for it.

    Numbers only, never the post itself, and nothing is fetched from the platform: the creator or the brand
    team pastes the link and types (or imports) what the platform showed them. One per piece.
    """

    __tablename__ = "post_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), unique=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    url: Mapped[str] = mapped_column(String(500), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    posted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # views, reach, likes, comments, shares, saves, watch_seconds: each a count, each optional.
    metrics: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | csv
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PersonReference(Base):
    """A photo a face is compared against, and where it came from: uploaded by the brand or the person,
    or found on the web (the address is kept, so a match can be traced to its source)."""

    __tablename__ = "person_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    media_type: Mapped[str] = mapped_column(String(40))
    data_base64: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))  # upload | web
    source_url: Mapped[str | None] = mapped_column(String(500))
    # Only approved photos identify anyone: the brand team adds approved ones, a creator's own wait.
    approved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    person: Mapped[Person] = relationship(back_populates="references")


class BrandAsset(Base):
    """An official visual asset: the ground truth content is compared against.

    `part` says what the image shows. A mascot registered only as a face means
    the brand has never approved a body for it, so a post that attaches one is
    an unapproved extension, not a creative choice.
    """

    __tablename__ = "brand_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))  # schemas.BrandAssetIn.kind
    part: Mapped[str] = mapped_column(String(20), default="full")  # full | face | head | body | wordmark | icon
    # Exact spelling of any text in the artwork. Logo generators garble
    # lettering, so OCR'd text near a matched logo is checked against this.
    wordmark: Mapped[str | None] = mapped_column(String(120))
    media_type: Mapped[str] = mapped_column(String(40))
    data_base64: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # Nullable so an existing database gains it in place; None reads as current.
    retired: Mapped[bool | None] = mapped_column(default=False)
    tier: Mapped[Tier] = mapped_column(_enum(Tier), default=Tier.public)
    active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaBlob(Base):
    """An uploaded file, stored once and referenced from versions by id.

    Videos are too large to travel inside JSON, so every file can go through
    POST /media first. The type is sniffed from the bytes at upload.
    """

    __tablename__ = "media_blobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    media_type: Mapped[str] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(200))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Dispute(Base):
    """A creator's "this isn't what it means", queued for re-evaluation.

    The claim is untrusted: Prism re-reads the content at growing context
    without it, and only overturns when an independent reading agrees. Hard
    rules (leaks, approved facts, exact terms) are never overturned by a claim.
    """

    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    claim: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|upheld|overturned|escalated
    verdict: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatThread(Base):
    """One Ask Inki conversation, private to the person who had it.

    Messages are stored as the client sent them ({role, content, images?});
    image attachments are small data URLs kept for a future vision model.
    """

    __tablename__ = "chat_threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # How many of the person's own messages have been read for things to remember (verytas/memory/personal.py).
    remembered: Mapped[int | None] = mapped_column(Integer)
    # The browser it was had in, on a shared demo sign-in (memory/personal.py): visitors who pick the same
    # person don't see each other's chats. Null for a person's own account.
    device: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PublicContact(Base):
    """A contact detail the company publishes. Anything phone- or email-shaped in a post or a message that
    is not listed here is treated as private: posts and messages carrying it are flagged for the brand team."""

    __tablename__ = "public_contacts"
    __table_args__ = (UniqueConstraint("workspace_id", "kind", "normalized", name="uq_public_contact"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # phone | email | handle | url
    value: Mapped[str] = mapped_column(String(200))
    normalized: Mapped[str] = mapped_column(String(200))
    label: Mapped[str | None] = mapped_column(String(120))
    source_ref: Mapped[str | None] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BrandEvent(Base):
    """Something the brand is doing (a launch, a sale, a partnership) or going through (a crisis).

    An event is context for every review while it runs: its brief becomes a model-judged rule, its
    words to avoid an exact-match rule, and its hashtags are required on pieces tagged with it. Each
    change bumps `revision` and starts the update chain (services/events.py)."""

    __tablename__ = "brand_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20), default="campaign")  # launch|campaign|sale|crisis|partnership|other
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text, default="")
    guidance: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    avoid_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Promotional posts pause while it runs (a crisis, a day of mourning).
    blackout: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | cancelled
    tier: Mapped[Tier] = mapped_column(_enum(Tier), default=Tier.public)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def live_on(self, day: date) -> bool:
        return self.status == "active" and self.starts_on <= day and (self.ends_on is None or day <= self.ends_on)


class EventImpact(Base):
    """One link in the update chain: an event changed, so this piece was re-checked against it."""

    __tablename__ = "event_impacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("brand_events.id"), index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    change: Mapped[str] = mapped_column(String(20))  # created | updated | cancelled
    review_id: Mapped[int | None] = mapped_column(ForeignKey("reviews.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Escalation(Base):
    """A creator asking a person to look at a finding: "this is wrong, please review it by hand".

    Unlike a dispute (re-judged by Prism), an escalation goes to the brand team's inbox. Its message is
    screened first (security/guard.py); what was flagged travels with it so the reviewer sees it."""

    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), index=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"))
    raised_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    guard: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | upheld | cleared | withdrawn
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolution_code: Mapped[str | None] = mapped_column(String(40))
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentSeen(Base):
    """When a person last opened a piece: news on it from the other side after this is unread for them
    (services/review_news.py)."""

    __tablename__ = "content_seen"
    __table_args__ = (UniqueConstraint("user_id", "content_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), index=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntakeBatch(Base):
    """One drop of company material into Prism Intake (prism/intake): files, links and the admin's note on them.

    Nothing in a batch governs anything until an admin approves its drafts; the batch is the record of what
    came in, what was understood, and what was asked back."""

    __tablename__ = "intake_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)  # what the admin says the material is
    tier: Mapped[Tier] = mapped_column(_enum(Tier), default=Tier.internal)
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued | running | done | failed
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntakeItem(Base):
    """One file, link or pasted text in a batch, as it was read and understood."""

    __tablename__ = "intake_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("intake_batches.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    blob_id: Mapped[str | None] = mapped_column(String(32))
    source_url: Mapped[str | None] = mapped_column(String(500))  # a read-only live source
    text: Mapped[str | None] = mapped_column(Text)  # pasted material
    media_type: Mapped[str | None] = mapped_column(String(100))
    context: Mapped[str | None] = mapped_column(Text)  # what the admin said about this item, or answered
    # queued | reading | understood | needs_context | failed
    status: Mapped[str] = mapped_column(String(16), default="queued")
    kind: Mapped[str | None] = mapped_column(String(40))  # brand book, price sheet, chart, logo...
    purpose: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    reading: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # what the readers found, previewed
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    model: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(Text)
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntakeDraft(Base):
    """Something an item would add to the library: a rule, fact, term or asset, with where it came from.
    pending until an admin approves (it is then created through the same checks as by hand) or rejects it."""

    __tablename__ = "intake_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("intake_items.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    target: Mapped[str] = mapped_column(String(10))  # rule | fact | term | asset
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # page, sheet and cell, box, quote
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | approved | rejected
    created_object: Mapped[str | None] = mapped_column(String(40))  # "fact:12" once approved
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    """A creator and one member of the brand team talking it through: one thread per pair, like a direct
    message, with each message free to point at the piece it is about (services/messages.py).

    Each side's read position is the id of the last message they have seen, so unread counts are one
    comparison and a second device catches up from the same number."""

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("creator_id", "manager_id", name="one_conversation_per_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    creator_read_id: Mapped[int] = mapped_column(Integer, default=0)
    manager_read_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Message(Base):
    """One message in a conversation. The text and any shared call link are sealed together (AES-GCM,
    bound to the conversation) in `sealed`. The piece it points at stays a plain key, because who may
    open that piece is checked against it.

    sender_id is None for Inki; asked_by then names the person whose @Inki it answered. client_id makes
    a resend after a dropped connection land once."""

    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "client_id", name="message_sent_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    asked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(12), default="text")  # text | call | inki
    sealed: Mapped[str] = mapped_column(Text)
    content_id: Mapped[int | None] = mapped_column(ForeignKey("contents.id"))
    reply_to_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    client_id: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Deleted for everyone: the sealed body is replaced by an empty one and its uploads are released.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageAttachment(Base):
    """An upload a message carries. The name and type travel sealed in the message; this row only says
    which upload belongs to which message, so access can be checked and the storage sweep keeps it."""

    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    blob_id: Mapped[str] = mapped_column(String(64), index=True)


class MessageVector(Base):
    """A message's meaning as numbers, so Inki can find the turns of a long conversation that bear on a question
    (verytas/memory/thread.py). Sealed with the conversation's key like the message itself: what the words were
    about is not left readable at rest either. `model` and `digest` say what it was made from, so an edited
    message or a changed model is embedded again rather than matched on stale numbers."""

    __tablename__ = "message_vectors"

    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(80))
    digest: Mapped[str] = mapped_column(String(16))
    sealed: Mapped[str] = mapped_column(Text)


class MediaDigest(Base):
    """What Inki read out of an upload (document text, text in an image, a video's speech and captions),
    kept so the same file is read once. Goes when the upload goes."""

    __tablename__ = "media_digests"

    blob_id: Mapped[str] = mapped_column(ForeignKey("media_blobs.id", ondelete="CASCADE"), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
