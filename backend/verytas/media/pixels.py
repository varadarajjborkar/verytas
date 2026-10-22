"""Pixel redaction: black out confidential text before an image leaves the machine.

Text redaction (security/redaction.py) can't touch words drawn inside an
image. Local OCR gives each line a box and each word its own box; where a
confidential term sits in a line, the boxes of the words it touches are
filled, padded by a share of the line height. When word boxes are missing or
don't line up with the line text, the whole line is filled instead. Covering
a neighbouring word costs the vision model a little context; missing part of
the term leaks it (a proportional slice once left "Proj" readable after
narrow glyphs earlier in the line).

Terms broken over two lines are matched on the joined text, and lines the
OCR dropped as low-confidence noise are redacted too.
"""

from __future__ import annotations

import re

from PIL import Image, ImageDraw

from verytas.media.ocr import OcrLine, OcrResult
from verytas.security.terms import find_folded

PAD_X = 0.35  # of the line height, either side of the covered words
PAD_Y = 0.2

Box = tuple[float, float, float, float]


def redact(img: Image.Image, ocr: OcrResult, patterns: list[re.Pattern[str]]) -> tuple[Image.Image, int]:
    """A copy of `img` with every match blacked out, and how many were hidden."""
    if not patterns:
        return img, 0
    boxes: list[Box] = []
    hidden = 0
    lines = [*ocr.lines, *ocr.noise]
    for line in lines:
        for pattern in patterns:
            for start, end, _ in find_folded(pattern, line.text):
                boxes.append(_cover(line, start, end))
                hidden += 1
    # A term wrapped onto the next line: only matches that cross the join count,
    # so a term already found inside one line isn't hidden twice.
    for a, b in zip(ocr.lines, ocr.lines[1:], strict=False):
        joined = f"{a.text} {b.text}"
        for pattern in patterns:
            for start, end, _ in find_folded(pattern, joined):
                if start < len(a.text) < end:
                    boxes += [_pad(a.box, a), _pad(b.box, b)]
                    hidden += 1
    if not boxes:
        return img, 0
    out = img.copy()
    draw = ImageDraw.Draw(out)
    for box in boxes:
        draw.rectangle(box, fill="black")
    return out, hidden


def _cover(line: OcrLine, start: int, end: int) -> Box:
    """The padded union of the word boxes that chars [start, end) fall in, or the whole line."""
    spans = _word_spans(line)
    if spans is None:
        return _pad(line.box, line)
    hit = [box for (a, b), box in spans if a < end and start < b]
    if not hit:
        return _pad(line.box, line)
    return _pad((min(b[0] for b in hit), min(b[1] for b in hit), max(b[2] for b in hit), max(b[3] for b in hit)),
                line)


def _word_spans(line: OcrLine) -> list[tuple[tuple[int, int], tuple[int, int, int, int]]] | None:
    """Character span of each word box within the line text; None if they can't be placed exactly."""
    if not line.words:
        return None
    out, pos = [], 0
    for word, box in line.words:
        at = line.text.find(word, pos)
        if at < 0:
            return None
        out.append(((at, at + len(word)), box))
        pos = at + len(word)
    return out


def _pad(box: tuple[float, float, float, float], line: OcrLine) -> Box:
    h = max(1.0, line.box[3] - line.box[1])
    return box[0] - h * PAD_X, box[1] - h * PAD_Y, box[2] + h * PAD_X, box[3] + h * PAD_Y
