"""Deterministic checkers: free, instant and fully explainable.

Each matcher handles one `pattern.type`. Rules carry their own config, so a
brand admin tunes behaviour by editing a rule, not by changing code.
"""

from __future__ import annotations

import base64
import io
import math
import re
from collections.abc import Callable, Iterator

import numpy as np
from PIL import Image, UnidentifiedImageError

from verytas.checks.base import CheckContext, RawFinding, RuleView, SuggestedEdit, Unit
from verytas.checks.color import (
    contrast_ratio,
    dominant_colours,
    hex_to_rgb,
    nearest_brand_colour,
    rgb_to_hex,
    rgb_to_lab,
)
from verytas.checks.readability import flesch_kincaid_grade, words
from verytas.security.terms import term_pattern

CHECKER = "deterministic"
Matcher = Callable[[CheckContext, RuleView], Iterator[RawFinding]]
_MATCHERS: dict[str, Matcher] = {}


def matcher(pattern_type: str):
    def register(fn: Matcher) -> Matcher:
        _MATCHERS[pattern_type] = fn
        return fn

    return register


def run_deterministic(ctx: CheckContext) -> list[RawFinding]:
    findings: list[RawFinding] = []
    for rule in ctx.rules:
        fn = _MATCHERS.get(rule.pattern.get("type", ""))
        if fn is not None and rule.kind == "deterministic":
            findings.extend(fn(ctx, rule))
    return findings


# --- helpers -----------------------------------------------------------------

def _term_regex(term: str) -> re.Pattern[str]:
    # Word boundaries that also work for terms starting/ending in punctuation.
    return re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE)


def _paragraph_for(ctx: CheckContext, offset: int) -> Unit:
    for u in ctx.units:
        if u.kind == "sentence" and u.start <= offset < u.end:
            return u
    for u in ctx.units:
        if u.kind == "paragraph" and u.start <= offset < u.end:
            return u
    return ctx.units[0]


def _match_case(original: str, replacement: str) -> str:
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _finding(ctx: CheckContext, rule: RuleView, start: int, end: int, title: str, explanation: str,
             suggestion: SuggestedEdit | None = None, confidence: float = 1.0) -> RawFinding:
    unit = _paragraph_for(ctx, start)
    return RawFinding(
        unit_id=unit.id, category=rule.category, title=title, explanation=explanation,
        confidence=confidence, checker=CHECKER, rule_code=rule.code, quote=ctx.body[start:end],
        span_start=start, span_end=end, suggestion=suggestion,
    )


# --- terminology -------------------------------------------------------------

@matcher("banned_terms")
def banned_terms(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    for term in rule.pattern.get("terms", []):
        for m in _term_regex(term).finditer(ctx.body):
            yield _finding(ctx, rule, m.start(), m.end(), f'Avoid "{m.group(0)}"', rule.text)


@matcher("preferred_terms")
def preferred_terms(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    for wrong, right in rule.pattern.get("map", {}).items():
        for m in _term_regex(wrong).finditer(ctx.body):
            proposed = _match_case(m.group(0), right)
            yield _finding(
                ctx, rule, m.start(), m.end(), f'Use "{right}" instead of "{m.group(0)}"', rule.text,
                SuggestedEdit(m.group(0), proposed, f"House style ({rule.code}) prefers '{right}'."),
            )


@matcher("casing")
def casing(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    for term in rule.pattern.get("terms", []):
        for m in _term_regex(term).finditer(ctx.body):
            if m.group(0) != term:
                yield _finding(
                    ctx, rule, m.start(), m.end(), f'Write "{term}" with its official casing', rule.text,
                    SuggestedEdit(m.group(0), term, f"Official spelling is '{term}'."),
                )


# --- confidentiality ---------------------------------------------------------

@matcher("confidential_terms")
def confidential_terms(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    for t in ctx.terms:
        if t.embargo_until is not None and ctx.today >= t.embargo_until:
            continue
        until = f" until {t.embargo_until.isoformat()}" if t.embargo_until else ""
        for m in term_pattern(t.term).finditer(ctx.body):
            yield _finding(
                ctx, rule, m.start(), m.end(), f'Confidential term "{m.group(0)}"',
                f'"{t.term}" is marked confidential{until}. Publishing it would leak protected information.',
            )


# --- accessibility -----------------------------------------------------------

_PLACEHOLDER_ALT = {"image", "photo", "picture", "img", "graphic", "screenshot", "banner", "logo"}


@matcher("alt_text")
def alt_text(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    min_len = int(rule.pattern.get("min_length", 8))
    for i, img in enumerate(ctx.attachments.get("images", []), start=1):
        alt = (img.get("alt") or "").strip()
        unit_id = f"img:{img.get('id', i)}"
        if img.get("decorative"):
            continue
        if not alt:
            problem = "has no alt text"
        elif alt.lower().strip(".") in _PLACEHOLDER_ALT or len(alt) < min_len:
            problem = f'has placeholder alt text ("{alt}")'
        else:
            continue
        yield RawFinding(
            unit_id=unit_id, category=rule.category, title=f"Image {img.get('id', i)} {problem}",
            explanation=rule.text, confidence=1.0, checker=CHECKER, rule_code=rule.code, quote=alt or None,
        )


@matcher("contrast")
def contrast(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    for i, pair in enumerate(ctx.attachments.get("colors", []), start=1):
        try:
            ratio = contrast_ratio(hex_to_rgb(pair["fg"]), hex_to_rgb(pair["bg"]))
        except (KeyError, ValueError):
            continue
        minimum = float(rule.pattern.get("min_ratio_large" if pair.get("large") else "min_ratio", 4.5))
        if ratio < minimum:
            where = pair.get("where", f"colour pair {i}")
            yield RawFinding(
                unit_id=f"color:{i}", category=rule.category,
                title=f"Low contrast in {where}: {ratio:.2f}:1 (needs {minimum:g}:1)",
                explanation=f"{pair['fg']} on {pair['bg']} has a contrast ratio of {ratio:.2f}:1. {rule.text}",
                confidence=1.0, checker=CHECKER, rule_code=rule.code,
            )


_HASHTAG = re.compile(r"(?<![\w#])#([A-Za-z][A-Za-z0-9_]+)")


@matcher("hashtag_case")
def hashtag_case(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    min_len = int(rule.pattern.get("min_length", 10))
    for m in _HASHTAG.finditer(ctx.body):
        tag = m.group(1)
        # Without a dictionary we can't split words, so only long all-lowercase
        # tags are flagged, at reduced confidence.
        if len(tag) >= min_len and tag.islower():
            yield _finding(ctx, rule, m.start(), m.end(), f"Hashtag #{tag} is hard for screen readers",
                           rule.text, confidence=0.75)


_CAPS_WORD = re.compile(r"\b[A-Z]{2,}\b")


@matcher("all_caps")
def all_caps(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    max_run = int(rule.pattern.get("max_run", 2))
    words = list(_CAPS_WORD.finditer(ctx.body))
    run: list[re.Match[str]] = []
    for w in [*words, None]:
        contiguous = w is not None and run and ctx.body[run[-1].end():w.start()].strip(" ,!?.-") == ""
        if w is not None and (not run or contiguous):
            run.append(w)
            continue
        if len(run) > max_run:
            yield _finding(ctx, rule, run[0].start(), run[-1].end(),
                           f"{len(run)} capitalised words in a row", rule.text)
        run = [w] if w is not None else []


_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


@matcher("link_text")
def link_text(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    banned = {b.lower() for b in rule.pattern.get("banned", [])}
    for m in _MD_LINK.finditer(ctx.body):
        if m.group(1).strip().lower() in banned:
            yield _finding(ctx, rule, m.start(1), m.end(1), f'Vague link text "{m.group(1)}"', rule.text)


@matcher("readability")
def readability(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    max_grade = float(rule.pattern.get("max_grade", 10))
    min_words = int(rule.pattern.get("min_words", 25))
    for p in ctx.units_of("paragraph"):
        if len(words(p.text)) < min_words:
            continue
        grade = flesch_kincaid_grade(p.text)
        if grade > max_grade:
            yield RawFinding(
                unit_id=p.id, category=rule.category,
                title=f"Reading grade {grade:.1f} is above the target of {max_grade:g}",
                explanation=f"{rule.text} Shorter sentences and plainer words would help.",
                confidence=1.0, checker=CHECKER, rule_code=rule.code,
                quote=p.text[:160], span_start=p.start, span_end=p.end,
            )


# --- visual ------------------------------------------------------------------

def _decode_image(img: dict) -> np.ndarray | None:
    data = img.get("data_base64")
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(base64.b64decode(data, validate=True))) as im:
            im = im.convert("RGB")
            im.thumbnail((96, 96))
            return np.asarray(im)
    except (ValueError, UnidentifiedImageError, OSError):
        return None


def _chroma(rgb: tuple[int, int, int]) -> float:
    _, a, b = rgb_to_lab(rgb)
    return math.hypot(a, b)


@matcher("palette")
def palette(ctx: CheckContext, rule: RuleView) -> Iterator[RawFinding]:
    brand = [hex_to_rgb(c) for c in rule.pattern.get("colors", [])]
    if not brand:
        return
    max_de = float(rule.pattern.get("max_delta_e", 12))
    min_share = float(rule.pattern.get("min_share", 0.1))
    allow_neutrals = bool(rule.pattern.get("allow_neutrals", True))
    for i, img in enumerate(ctx.attachments.get("images", []), start=1):
        pixels = _decode_image(img)
        if pixels is None:
            continue
        for colour, share in dominant_colours(pixels, k=5):
            if share < min_share or (allow_neutrals and _chroma(colour) < 8):
                continue
            nearest, de = nearest_brand_colour(colour, brand)
            if de > max_de:
                yield RawFinding(
                    unit_id=f"img:{img.get('id', i)}", category=rule.category,
                    title=f"Off-palette colour {rgb_to_hex(colour)} covers {share:.0%} of the image",
                    explanation=(
                        f"Closest brand colour is {rgb_to_hex(nearest)} at a CIEDE2000 distance of {de:.1f} "
                        f"(limit {max_de:g}). {rule.text}"
                    ),
                    confidence=1.0, checker=CHECKER, rule_code=rule.code,
                )
