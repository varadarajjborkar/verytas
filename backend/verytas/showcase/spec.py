"""What a demo company is made of. Each company module builds one `Company`; the engine seeds it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

NOW = datetime.now(UTC).replace(microsecond=0)
TODAY = date.today()

Flow = list[tuple[float, str, dict]]  # (hours after the piece was written, action, args)


@dataclass
class Member:
    key: str  # the token key and the handle used in piece flows ("dev", "approver")
    email: str
    name: str
    role: str  # brand_admin | approver | reviewer | auditor | creator
    persona: str = ""  # how a creator behaves, see gen.PERSONAS
    title: str = ""
    blurb: str = ""


@dataclass
class Piece:
    key: str
    who: str  # a creator's member key
    title: str
    channel: str
    body: str
    days_ago: float
    flow: Flow
    event: str | None = None
    images: Callable[[], list[dict]] | None = None  # attachments, drawn when the piece is written
    colors: list[dict] | None = None  # colour pairs the creator declares, checked for contrast
    notes: dict | None = None  # creator_notes: intent, language, ai_used, ...
    fix_colors: list[dict] | None = None
    fix_images: Callable[[], list[dict]] | None = None  # replaces the images when the creator fixes the piece


@dataclass
class Company:
    key: str
    brand: str
    industry: str
    domain: str
    days: int  # length of the history
    team: list[Member]  # first is the head of brand (brand_admin), second the approver
    creators: list[Member]
    rules: list[dict]
    facts: list[dict]
    terms: list[dict]
    contacts: list[dict]
    assets: list[dict]
    events: list[dict]
    people: list[dict]
    pieces: Callable[[], list[Piece]]
    # (piece key, hours after it was written, rule code, member key, action, reason_code, note)
    decisions: list[tuple] = field(default_factory=list)
    # Per reviewer: rule code (or "*") -> (chance a finding is accepted, [(reason_code, note)] used when it is not).
    stance: dict[str, dict[str, tuple[float, list[tuple[str, str]]]]] = field(default_factory=dict)
    # (days ago, action, args): the brand team editing its library mid-history.
    admin_log: list[tuple[float, str, dict]] = field(default_factory=list)
    # (json key, member key, side, title, blurb): who a judge can sign in as.
    demo: list[tuple[str, str, str, str, str]] = field(default_factory=list)


def at(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago)


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


SEND = (1, "send", {})
CLEAN: Flow = [(1, "send", {}), (4, "approve", {}), (20, "publish", {})]


def fixed(note: str, body: str, by: str = "reviewer") -> Flow:
    return [(1, "send", {}), (3, "autodecide", {"by": by}), (6, "back", {"note": note}), (20, "fix", {"body": body}),
            (21, "send", {}), (26, "approve", {}), (40, "publish", {})]
