"""Split a content body into addressable units with stable character offsets.

Findings point at units and spans, so offsets must always index into the
original body exactly; nothing here normalises or rewrites the text.
"""

from __future__ import annotations

import re

from verytas.checks.base import Unit

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# A sentence ends at . ! or ? (optionally closed by a quote or bracket) followed
# by whitespace and something that can start a sentence. Deliberately simple:
# a missed split only makes a unit longer, it never loses text.
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z0-9\"'(#@À-ɏ])")
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "Mr.", "Ms.", "Dr.", "Inc.", "Ltd.", "approx.", "No.")


def _paragraph_spans(body: str) -> list[tuple[int, int]]:
    spans, cursor = [], 0
    for m in _PARAGRAPH_BREAK.finditer(body):
        spans.append((cursor, m.start()))
        cursor = m.end()
    spans.append((cursor, len(body)))
    return [(s, e) for s, e in (_trim(body, s, e) for s, e in spans) if e > s]


def _trim(body: str, start: int, end: int) -> tuple[int, int]:
    while start < end and body[start].isspace():
        start += 1
    while end > start and body[end - 1].isspace():
        end -= 1
    return start, end


def _sentence_spans(body: str, start: int, end: int) -> list[tuple[int, int]]:
    spans, cursor = [], start
    for m in _SENTENCE_END.finditer(body, start, end):
        # The match is [optional closing quote/bracket][whitespace]; the sentence
        # keeps its closer and drops the whitespace.
        closer = len(m.group(0)) - len(m.group(0).lstrip("\"')]"))
        sentence_end = m.start() + closer
        if body[cursor:sentence_end].endswith(_ABBREVIATIONS):
            continue
        spans.append(_trim(body, cursor, sentence_end))
        cursor = m.end()
    spans.append(_trim(body, cursor, end))
    return [(s, e) for s, e in spans if e > s]


def segment(body: str) -> list[Unit]:
    units: list[Unit] = []
    for p_idx, (ps, pe) in enumerate(_paragraph_spans(body), start=1):
        units.append(Unit(id=f"p{p_idx}", kind="paragraph", text=body[ps:pe], start=ps, end=pe))
        for s_idx, (ss, se) in enumerate(_sentence_spans(body, ps, pe), start=1):
            units.append(Unit(id=f"p{p_idx}.s{s_idx}", kind="sentence", text=body[ss:se], start=ss, end=se))
    return units


def image_units(attachments: dict) -> list[Unit]:
    return [
        Unit(id=f"img:{img.get('id', i)}", kind="image", text=img.get("alt") or "", start=-1, end=-1)
        for i, img in enumerate(attachments.get("images", []), start=1)
    ]
