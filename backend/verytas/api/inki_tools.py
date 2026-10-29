"""The lookups Ask Inki may make while it answers, each acting as the person asking and never more.

The fixed context (assistant.py) holds what most questions need. These cover the rest: a creator's track
record, the escalations inbox, the library's own wording (rules, facts, events, approved people), and a
search through pieces' text. The model picks a tool and its arguments; everything else is decided here.

Every tool calls the route function or helper behind the matching screen, so visibility, role and clearance
rules live in one place, and then narrows further the way the context does: confidential pieces and library
entries are left out, and every string passes the workspace's redactor. The redactor numbers terms by
their place in the workspace's list (stable), so [[TERM_2]] means the same term in the context and in every
tool result of one answer. Results are cut to a size a model can read in one go, and say when they were.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from verytas.api.content import list_contents, visible
from verytas.api.deps import CurrentUser, Session
from verytas.api.governance import list_escalations, list_events
from verytas.api.insights import _visible_tiers, overview_for
from verytas.api.knowledge import list_facts, list_rules
from verytas.api.people import list_people
from verytas.models import ConfidentialTerm, Content, ContentStatus, ContentVersion, Role, RuleStatus, Tier, User
from verytas.security.redaction import Redactor
from verytas.services.inki_guard import RateLimit
from verytas.services.trajectory import _points, trajectory
from verytas.services.trajectory import creators as roster

router = APIRouter(prefix="/assistant", tags=["assistant"])

ANALYSTS = {Role.reviewer, Role.approver, Role.auditor, Role.brand_admin}
# One answer makes a handful of lookups (16 at most); this stops a loop, not a person. The demo's accounts
# are shared by everyone who signs in as that persona, so it leaves room for a room full of them.
CALLS_PER_HOUR = 600
_calls = RateLimit(CALLS_PER_HOUR)
# What one result may hold, in characters of JSON. Lists are cut to fit and say so.
MAX_RESULT = 14_000


def _spec(name: str, description: str, properties: dict[str, Any] | None = None,
          required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or [],
                       "additionalProperties": False}}}


_QUERY = {"type": "string", "maxLength": 100}
SPECS: dict[str, dict[str, Any]] = {
    "creators": _spec(
        "creators",
        "Every creator with how far their recent pieces drifted from the brand as first sent (distance 0 to 100: "
        "each must-fix adds 40, should-fix 15, note 4), how many were on brand, open escalations, and the kinds of "
        "issue that come up most for them. Use for questions comparing creators or about drift."),
    "creator": _spec(
        "creator",
        "One creator's track record, piece by piece in the order sent: distance from the brand, the issues found, "
        "and how each piece ended. Use for questions about one named creator, such as whether they are improving.",
        {"name": {**_QUERY, "description": "The creator's name, or part of it"}}, ["name"]),
    "escalations": _spec(
        "escalations",
        "Requests creators raised to a person about a finding: the piece, the finding, the creator's message and, "
        "once resolved, the outcome. Creators see only their own.",
        {"state": {"type": "string", "enum": ["open", "resolved", "all"], "description": "Default open"}}),
    "rules": _spec(
        "rules",
        "The brand's active rules with their full wording and good and bad examples. Use whenever asked what a "
        "rule says or whether something is allowed.",
        {"query": {**_QUERY, "description": "Words to look for in a rule's code, title or text; empty lists all"}}),
    "facts": _spec(
        "facts",
        "Approved facts valid today: the figures, dates and claims posts may cite, with their source.",
        {"query": {**_QUERY, "description": "What the fact is about; empty lists all"}}),
    "events": _spec(
        "events",
        "Brand events (launches, sales, campaigns, blackouts) with dates, guidance, hashtags, words to avoid and "
        "how many pieces are tied to each."),
    "people": _spec(
        "people",
        "Approved people who may be shown or named in posts, with the channels and dates their agreement covers."),
    "find_pieces": _spec(
        "find_pieces",
        "Search pieces by words in their title or text, and filter by status, channel or creator. Returns each "
        "piece's id, creator, status and latest review score. Use piece for one piece's full story.",
        {"query": {**_QUERY, "description": "Words that must appear in the title or text"},
         "status": {"type": "string", "enum": ["draft", "in_review", "changes_requested", "approved", "published",
                                               "withdrawn"]},
         "channel": {"type": "string", "maxLength": 40},
         "creator": {**_QUERY, "description": "The creator's name, or part of it"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 40}}),
    "piece": _spec(
        "piece",
        "One piece in full: latest text, every version's review score and counts, and the open issues with the "
        "rule and words behind each.",
        {"id": {"type": "integer", "minimum": 1, "description": "A piece id from the context or find_pieces"}},
        ["id"]),
    "trend": _spec(
        "trend",
        "Findings per day by level over a window, with totals by category and the rules that fired most.",
        {"days": {"type": "integer", "minimum": 7, "maximum": 90, "description": "Default 30"}}),
}
# Workspace-wide views are the brand team's; a creator's Inki works from their own pieces.
ANALYST_ONLY = {"creators", "creator", "trend"}


def specs_for(user: User) -> list[dict[str, Any]]:
    return [s for name, s in SPECS.items() if user.role in ANALYSTS or name not in ANALYST_ONLY]


class ToolCall(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


async def stable_redactor(session, user: User) -> Redactor:
    # Every term is redacted, embargo passed or not, the same as Prism does on egress.
    terms = (await session.scalars(select(ConfidentialTerm.term).where(
        ConfidentialTerm.workspace_id == user.workspace_id))).all()
    return Redactor(list(terms), stable=True)


def _open_tiers(user: User) -> list[Tier]:
    return [t for t in _visible_tiers(user) if t is not Tier.confidential]


def _text(args: dict[str, Any], key: str) -> str:
    """A text argument as text, whatever type the model sent it as."""
    value = args.get(key)
    return "" if value is None else str(value)


def _words(text: str | None) -> list[str]:
    return [w for w in (text or "").lower().split() if w]


def _matches(query: str | None, *fields: str | None) -> bool:
    words = _words(query)
    hay = " ".join(f or "" for f in fields).lower()
    return all(w in hay for w in words)


def _fit(items: list[Any], key: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """The list under `key`, cut from the end until the whole result fits MAX_RESULT, saying how many were left."""
    out = {**(extra or {}), key: items}
    while items and len(json.dumps(out, default=str)) > MAX_RESULT:
        items = items[:max(1, len(items) * 3 // 4)] if len(items) > 1 else []
        out = {**(extra or {}), key: items, "cut": f"showing {len(items)} of the matches; ask about fewer"}
    return out


async def _names(session, workspace_id: int) -> dict[int, str]:
    return dict((await session.execute(select(User.id, User.name).where(User.workspace_id == workspace_id))).all())


async def _creator_named(session, user: User, name: str, redactor: Redactor) -> User:
    people = (await session.scalars(select(User).where(User.workspace_id == user.workspace_id,
                                                       User.role == Role.creator))).all()
    wanted = name.strip().lower()
    shown = {p.id: redactor.redact(p.name).lower() for p in people}
    exact = [p for p in people if shown[p.id] == wanted]
    found = exact or [p for p in people if wanted and wanted in shown[p.id]]
    if len(found) != 1:
        hint = ", ".join(sorted(redactor.redact(p.name) for p in found)[:8]) if found else "no creator by that name"
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"name one creator ({hint})")
    return found[0]


async def _creators(session, user: User, _args: dict[str, Any], _redactor: Redactor) -> dict[str, Any]:
    tiers = _open_tiers(user)
    rows = await roster(session, user, tiers)
    lines, _ = await _points(session, user, [r["id"] for r in rows], tiers)
    out = []
    for r in rows:
        recent = lines[r["id"]][-5:]
        kinds: dict[str, int] = {}
        for p in recent:
            for issue in p["issues"]:
                kinds[issue["category"]] = kinds.get(issue["category"], 0) + 1
        out.append({"name": r["name"], "pieces": r["pieces"], "reviewed": r["reviewed"],
                    "on_brand_as_sent": r["on_brand_as_sent"], "average_distance": r["average_distance"],
                    "recent_distances": r["recent"][-5:], "open_escalations": r["open_escalations"],
                    "recent_issue_kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])[:4]),
                    "recent_tone_drift": sorted({d for p in recent for d in p["drift"]}),
                    "last_sent": r["last_at"]})
    out.sort(key=lambda c: -(sum(c["recent_distances"]) / len(c["recent_distances"]) if c["recent_distances"] else -1))
    return _fit(out, "creators", {"sorted_by": "average distance of the last five reviewed pieces, furthest first"})


async def _creator(session, user: User, args: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    person = await _creator_named(session, user, _text(args, "name"), redactor)
    track = await trajectory(session, user, person, _open_tiers(user))
    stats = {k: v for k, v in track["stats"].items() if k != "above_clearance"}
    points = [{k: p[k] for k in ("content_id", "title", "channel", "status", "at", "distance", "issues", "summary",
                                 "event")} for p in track["points"][-15:]]
    return _fit(points, "pieces", {"name": person.name, "stats": stats, "issue_kinds": track["categories"],
                                   "note": "oldest first; distance is the piece as first sent"})


async def _escalations(session, user: User, args: dict[str, Any], _redactor: Redactor) -> dict[str, Any]:
    state = args.get("state") if args.get("state") in ("open", "resolved", "all") else "open"
    rows = await list_escalations(session, user, state=state, content_id=None, limit=60)
    out = [{"id": e["id"], "status": e["status"], "raised": e["created_at"], "by": (e["raised_by"] or {}).get("name"),
            "piece": {"id": e["content"]["id"], "title": e["content"]["title"], "channel": e["content"]["channel"]},
            "finding": {"title": e["finding"]["title"], "level": e["finding"]["level"],
                        "category": e["finding"]["category"]},
            "creator_message": (e["message"] or "")[:400],
            "resolution": e["resolution"] and {"outcome": e["resolution"]["outcome"],
                                               "note": (e["resolution"]["note"] or "")[:300]}}
           for e in rows if e["content"]["tier"] is not Tier.confidential]
    return _fit(out, "escalations", {"state": state})


async def _rules(session, user: User, args: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    query = _text(args, "query")
    rules = [r for r in await list_rules(session, user, state=RuleStatus.active)
             if r.tier is not Tier.confidential
             and _matches(query, *(redactor.redact(f or "") for f in (r.code, r.title, r.text, r.category)))]
    out = [{"code": r.code, "title": r.title, "text": r.text, "severity": r.severity, "category": r.category,
            "good_examples": r.good_examples[:3], "bad_examples": r.bad_examples[:3],
            "for_event": r.event_id is not None} for r in rules]
    return _fit(out, "rules")


async def _facts(session, user: User, args: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    # Ranked by the library's own relevance, on the query as redacted: a guessed confidential term becomes a
    # placeholder before it is searched, so it finds no more than any other word would.
    query = redactor.redact(_text(args, "query")).strip()
    facts = await list_facts(session, user, valid_on=date.today(), q=query or None)
    out = [{"statement": f.statement, "value": f.value, "unit": f.unit, "subject": f.subject,
            "source": f.source_ref, "valid_from": f.valid_from, "valid_to": f.valid_to}
           for f in facts if f.approved and f.tier is not Tier.confidential]
    return _fit(out, "facts", {"valid_on": date.today().isoformat()})


async def _events(session, user: User, _args: dict[str, Any], _redactor: Redactor) -> dict[str, Any]:
    events = [e for e in await list_events(session, user) if e.tier is not Tier.confidential]
    # The pieces tied to each event that this person may open, by title, so "which pieces" has an answer.
    tied: dict[int, list[str]] = {}
    for c in (await session.scalars(select(Content).where(
            Content.workspace_id == user.workspace_id, Content.event_id.in_([e.id for e in events])))).all():
        if visible(user, c) and c.tier is not Tier.confidential:
            tied.setdefault(c.event_id, []).append(f"{c.title} ({c.status.value})")
    out = [{"name": e.name, "kind": e.kind, "starts_on": e.starts_on, "ends_on": e.ends_on, "status": e.status,
            "live": e.live, "blackout": e.blackout, "summary": e.summary, "guidance": e.guidance[:600],
            "hashtags": e.hashtags, "avoid": e.avoid_terms, "rules": e.rules, "pieces": tied.get(e.id, [])[:20]}
           for e in sorted(events, key=lambda e: e.starts_on)]
    return _fit(out, "events", {"today": date.today().isoformat()})


async def _people(session, user: User, _args: dict[str, Any], _redactor: Redactor) -> dict[str, Any]:
    out = [{"name": p.name, "aliases": p.aliases, "kind": p.kind, "channels": p.channels, "active": p.active,
            "valid_from": p.valid_from, "valid_to": p.valid_to}
           for p in await list_people(session, user) if p.tier is not Tier.confidential]
    return _fit(out, "people", {"today": date.today().isoformat()})


async def _find_pieces(session, user: User, args: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    state = ContentStatus(args["status"]) if args.get("status") else None
    rows = [r for r in await list_contents(session, user, state=state, mine=False, limit=500)
            if r.tier is not Tier.confidential]
    names = await _names(session, user.workspace_id)
    if channel := _text(args, "channel").lower():
        rows = [r for r in rows if r.channel.lower() == channel]
    if who := _text(args, "creator").strip().lower():
        rows = [r for r in rows if who in redactor.redact(names.get(r.created_by, "")).lower()]
    if _words(query := _text(args, "query")):
        # The text of each piece's newest version, in one query.
        newest: dict[int, str] = {}
        for content_id, body in (await session.execute(
                select(ContentVersion.content_id, ContentVersion.body)
                .where(ContentVersion.content_id.in_([r.id for r in rows])).order_by(ContentVersion.version_no))):
            newest[content_id] = body
        # Matched as the model sees the text: redacted, so a placeholder in the query finds the pieces that
        # carry that term, whichever spelling of it they use, and the term itself is never searched for.
        rows = [r for r in rows
                if _matches(query, redactor.redact(r.title), redactor.redact(newest.get(r.id) or ""))]
    limit = min(max(int(args.get("limit") or 20), 1), 40)
    out = [{"id": r.id, "title": r.title, "creator": names.get(r.created_by), "channel": r.channel,
            "status": r.status, "updated_at": r.updated_at,
            "score": r.latest_review.overall if r.latest_review else None}
           for r in rows[:limit]]
    return _fit(out, "pieces", {"matched": len(rows)})


async def _piece(session, user: User, args: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    from verytas.api.assistant import _detail

    content = await session.get(Content, int(args.get("id") or 0))
    # One answer for missing, someone else's and confidential, so ids can't be probed.
    if content is None or not visible(user, content) or content.tier is Tier.confidential:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no piece with that id that you can open")
    names = await _names(session, user.workspace_id)
    return {"id": content.id, "title": content.title, "channel": content.channel, "status": content.status,
            "creator": names.get(content.created_by), **await _detail(session, content.id, redactor)}


async def _trend(session, user: User, args: dict[str, Any], _redactor: Redactor) -> dict[str, Any]:
    days = min(max(int(args.get("days") or 30), 7), 90)
    o = await overview_for(session, user, _open_tiers(user), days)
    return {"days": days, "trend": o["trend"], "findings": o["findings"], "top_rules": o["top_rules"]}


RUN = {"creators": _creators, "creator": _creator, "escalations": _escalations, "rules": _rules, "facts": _facts,
       "events": _events, "people": _people, "trend": _trend, "find_pieces": _find_pieces, "piece": _piece}


@router.get("/tools")
async def tools(user: CurrentUser) -> list[dict[str, Any]]:
    return specs_for(user)


@router.post("/tools/{name}")
async def run_tool(name: str, body: ToolCall, request: Request, session: Session, user: CurrentUser) -> dict[str, Any]:
    """One lookup. Errors a model can act on (a name that matches nobody, an id it can't open) come back as
    {"error": ...} with a 200, so the answer carries on; anything else is the API's usual error."""
    if name not in SPECS or name not in {s["function"]["name"] for s in specs_for(user)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such tool")
    if not _calls.take(user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many lookups; try again later")
    redactor = await stable_redactor(session, user)
    # Arguments are never restored: every search matches the text as the model sees it, redacted. A
    # placeholder then finds what carries that term, and a guessed term finds nothing, so a lookup can't be
    # used to confirm what a confidential term is.
    try:
        result = await RUN[name](session, user, body.arguments, redactor)
    except HTTPException as e:
        if e.status_code not in (status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_CONTENT):
            raise
        result = {"error": str(e.detail)}
    except (TypeError, ValueError, AttributeError):
        result = {"error": "those arguments don't fit this tool"}
    out = json.loads(json.dumps(result, default=_plain))
    return redactor.redact_any(out) | {"as_of": datetime.now(UTC).isoformat(timespec="minutes")}


def _plain(value: Any) -> Any:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return str(value)
