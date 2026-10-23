"""The evidence board: what every agent found, in one place, so the parts of a post can be compared.

Each agent checks its own part: OCR checks the poster's text, the speech agent checks what is said.
A post is read as a whole, though, and some defects exist only between parts: the caption promises
50% off and the poster 30%; the voice-over says Rs 499 while the screen shows Rs 999; the caption
introduces one ambassador and the face on screen is another. Agents post typed evidence here as they
work (figures from every text source, artwork matches, identified people), and the cross-check agent
runs after all of them and compares directly.

The comparisons are plain code and the findings they make are mechanical: two quotes from the
submission that cannot both be true. No model reads or argues them, so they are signed and levelled
like any other deterministic finding.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from verytas.checks.base import RawFinding, Source
from verytas.checks.crosscheck import Conflict, Figure, compare_pools, compare_timed

RULE = "CLAIM-MISMATCH"
CHECKER = "crosscheck"
WORKER = "cross-check"
_TIMED = ("captions", "subtitles", "speech")
# Speech recognition mishears numbers more often than OCR misreads a printed one ("fifteen", "fifty").
_SPEECH_TRUST = 0.85
# Counts are the loosest figures ("10,000 students" and "30 students" may be the community and a batch),
# and a price tag whose currency was guessed may be something else: worth a look, never a block.
_GUESS_CEILING = 0.6
_FIGURE_TRUST = 0.95


@dataclass(frozen=True)
class Evidence:
    kind: str  # figure | artwork | person
    source: str  # the source or media id it came from
    value: Any  # a Figure, an asset name, a person's name
    time: tuple[float, float] | None = None
    box: tuple[int, int, int, int] | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Board:
    items: list[Evidence] = field(default_factory=list)

    def post(self, item: Evidence) -> None:
        self.items.append(item)

    def of(self, kind: str) -> list[Evidence]:
        return [e for e in self.items if e.kind == kind]

    def summary(self) -> dict[str, int]:
        return dict(Counter(e.kind for e in self.items))


def origin(source_id: str) -> str:
    """The part of the submission a source belongs to: the text, one image, one document or one video.
    An image's local OCR and the vision model's reading of it are one part, as are a document's pages."""
    parts = source_id.split(":")
    if parts[0] in ("img", "doc", "vid") and len(parts) > 1:
        return ":".join(parts[:2])
    return source_id


def plain_where(source: Source | None) -> str:
    if source is None or source.id == "body":
        return "the text"
    if source.kind in _TIMED:
        return {"captions": "the on-screen text", "subtitles": "the subtitles", "speech": "the voice-over"}[
            source.kind]
    if source.id.startswith("doc:"):
        return "the document"
    return "the image"


def _clock(t: tuple[float, float] | None) -> str:
    if t is None:
        return ""
    return f" at {int(t[0] // 60)}:{int(t[0] % 60):02d}"


def _box(source: Source | None, at: int) -> tuple[int, int, int, int] | None:
    for c0, c1, box, _t0, _t1 in (source.regions if source else []):
        if c0 <= at < c1:
            return box
    return None


def _trust(source: Source | None) -> float:
    if source is None:
        return 1.0
    return source.confidence * (_SPEECH_TRUST if source.kind == "speech" else 1.0)


def conflicts(board: Board, sources: dict[str, Source]) -> list[Conflict]:
    """Every pair of figures that cannot both be true, anchored where a reader meets the claim first:
    the post's own text against each attachment, and inside a video the screen against the voice."""
    figs = [e.value for e in board.of("figure")]
    body = [f for f in figs if f.source == "body"]
    out: list[Conflict] = []
    for part in sorted({origin(f.source) for f in figs} - {"body"}):
        pool = [f for f in figs if origin(f.source) == part]
        out += compare_pools(body, pool)
        if part.startswith("vid:"):
            by_kind = {k: [f for f in pool if (s := sources.get(f.source)) is not None and s.kind == k]
                       for k in _TIMED}
            out += compare_timed(by_kind["captions"], by_kind["speech"])
            out += compare_timed(by_kind["subtitles"], by_kind["speech"])
            out += compare_timed(by_kind["captions"], by_kind["subtitles"])
    return out


def _unit_of(run: Any, f: Figure) -> str:
    if f.source != "body":
        return f"{f.source}/fig{f.start}"[:200]
    unit = next((u for u in run.base.units if u.kind == "sentence" and u.start <= f.start < u.end), None)
    return unit.id if unit else "body"


def figure_findings(run: Any, found: list[Conflict]) -> list[RawFinding]:
    rule = run.rule_by_code.get(RULE)
    if rule is None:
        return []
    sources = {s.id: s for s in run.sources}
    merged: dict[tuple[str, int, int], list[Conflict]] = {}
    for c in found:
        merged.setdefault((c.anchor.source, c.anchor.start, c.anchor.end), []).append(c)
    out = []
    for group in merged.values():
        a = group[0].anchor
        others = list({(c.other.source, c.other.start): c.other for c in group}.values())
        src_a = sources.get(a.source)
        where_a = plain_where(src_a)
        said = "; ".join(f"{plain_where(sources.get(b.source))} gives {b.quote}{_clock(b.time)}" for b in others)
        trust = min([_trust(src_a)] + [_trust(sources.get(b.source)) for b in others])
        confidence = _FIGURE_TRUST * trust
        if a.kind == "count" or any(f.inferred for f in (a, *others)):
            confidence = min(confidence, _GUESS_CEILING)
        first = others[0]
        locator = dict(src_a.locator) if src_a and a.source != "body" else {}
        if a.time is not None:
            locator["time"] = [a.time[0], a.time[1]]
        if (box := _box(src_a, a.start)) is not None:
            locator["box"] = list(box)
        locator["evidence"] = [{
            "source": b.source, "quote": b.quote,
            **({"time": [b.time[0], b.time[1]]} if b.time else {}),
            **({"box": list(bx)} if (bx := _box(sources.get(b.source), b.start)) else {}),
        } for b in others]
        out.append(RawFinding(
            unit_id=_unit_of(run, a), category=rule.category,
            title=f"{where_a[0].upper()}{where_a[1:]} says {a.quote}, {plain_where(sources.get(first.source))} "
                  f"says {first.quote}",
            explanation=f"{where_a[0].upper()}{where_a[1:]} gives {a.quote}{_clock(a.time)}; {said}. Viewers "
                        f"see both and can't tell which is right. {rule.text} Decide which figure is correct "
                        "and make the other match.",
            confidence=round(confidence, 4), checker=CHECKER, rule_code=rule.code, quote=a.quote,
            span_start=a.start, span_end=a.end, source=a.source, locator=locator or None,
        ))
    return out


def person_findings(run: Any) -> list[RawFinding]:
    """The text names an approved person, faces were identified in the media, and none of them is that
    person: the caption introduces one ambassador while another is on screen."""
    rule = run.rule_by_code.get(RULE)
    people = getattr(run.people, "people", None) if run.people is not None else None
    seen = run.board.of("person")
    if rule is None or not people or not seen or "legal" in run.partial:
        return []
    shown = {e.value.casefold() for e in seen}
    # Only people with a reference photo could have been recognised; anyone else's absence proves nothing.
    with_photos = {pid for pid, photos in (getattr(run.people, "photos", {}) or {}).items() if photos}
    body = run.base.body
    out = []
    for p in people:
        if p.id not in with_photos or p.name.casefold() in shown:
            continue
        hit = next((m for n in (p.name, *p.aliases) if (m := _named(body, n)) is not None), None)
        if hit is None:
            continue
        at, end = hit.span()
        other = seen[0]
        out.append(RawFinding(
            unit_id=_unit_of(run, Figure("body", "", 0, None, at, end, hit.group(0))), category=rule.category,
            title=f"The text names {p.name}, but the face shown is {other.value}",
            explanation=f"The text names {p.name}; the face identified in the media{_clock(other.time)} is "
                        f"{other.value}, and {p.name} isn't recognised anywhere in it. {rule.text} Check the "
                        "picture is the right person, or name the person shown.",
            confidence=0.8, checker=CHECKER, rule_code=rule.code, quote=hit.group(0),
            span_start=at, span_end=end, source="body",
            locator={"evidence": [{"source": other.source, "quote": other.value,
                                   **({"time": list(other.time)} if other.time else {}),
                                   **({"box": list(other.box)} if other.box else {})}]},
        ))
    return out


def _named(text: str, name: str) -> re.Match[str] | None:
    """Where the text names this person: the whole name or alias as a capitalised word ("Rose", not the
    "rose" in "rosewater" or "Rosemary"). Aliases under four letters are too often ordinary words."""
    if not name or len(name) < 4:
        return None
    for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
        if m.group(0)[0].isupper():
            return m
    return None


async def crosscheck_agent(run: Any, node: Any) -> None:
    """Runs after every part has been read: compares what the parts say about the same things."""
    sources = {s.id: s for s in run.sources}
    found = conflicts(run.board, sources)
    out = figure_findings(run, found) + person_findings(run)
    node.detail = {"evidence": run.board.summary(), "parts": len({origin(s) for s in sources}),
                   "conflicts": len(out)}
    run.add(node, WORKER, out)
