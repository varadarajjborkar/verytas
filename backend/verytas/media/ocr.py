"""Local OCR (RapidOCR, PP-OCR models on onnxruntime, CPU only).

Local first on purpose: the text inside an image is found without the image
leaving the machine, so confidential terms in it can be blacked out before a
cloud vision model is ever asked to look (media/pixels.py).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from verytas.media.files import shrink, to_array


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 in the image's pixels
    # Per-word boxes, when the engine gives them. Redaction uses these instead
    # of guessing positions from character counts.
    words: list[tuple[str, tuple[int, int, int, int]]] = field(default_factory=list)


@dataclass
class OcrResult:
    lines: list[OcrLine] = field(default_factory=list)
    engine: str = "rapidocr"
    # Lines dropped as noise. Not checked as text, but still redacted: a term
    # read at low confidence is still a term a cloud model could read better.
    noise: list[OcrLine] = field(default_factory=list)
    # Lines in a script the engine can't read. Its models know Latin and Chinese, so Devanagari or another
    # Indic script comes back as look-alike Chinese and Japanese glyphs ("市H市149" for a Hindi price; no
    # Devanagari at all on evals/ocr). Not checked as text, which would be checking garbage; redacted
    # like noise; and the review says the image's text went unread instead of passing it.
    foreign: list[OcrLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def confidence(self) -> float:
        """Character-weighted, so one confident word can't mask a garbled paragraph."""
        total = sum(len(line.text) for line in self.lines)
        if not total:
            return 0.0
        return sum(line.confidence * len(line.text) for line in self.lines) / total


_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr import RapidOCR

            _engine = RapidOCR(params={"Global.log_level": "critical"})
        return _engine


def read(img: Image.Image) -> OcrResult:
    """Blocking; call through asyncio.to_thread. Boxes are in `img`'s pixels."""
    work = shrink(img)
    scale = img.width / work.width
    out = _get_engine()(to_array(work), return_word_box=True)
    if out is None or out.txts is None:
        return OcrResult()
    words_per_line = list(out.word_results or ())
    lines, noise, foreign = [], [], []
    for i, (text, score, box) in enumerate(zip(out.txts, out.scores, out.boxes, strict=False)):
        line = OcrLine(text.strip(), float(score), _bbox(box, scale),
                       [(w, _bbox(b, scale)) for w, _, b in (words_per_line[i] if i < len(words_per_line) else ())
                        if w.strip()])
        if _foreign(text):
            foreign.append(line)
        else:
            if _FOREIGN.search(line.text):
                # One stray glyph is the engine's reading of a dash or a box, not a script it can't read:
                # setting the line aside would hide "call 98765 43210" from every check.
                line.text = re.sub(r"\s+", " ", _FOREIGN.sub(" ", line.text)).strip()
            (lines if _meaningful(text, float(score)) else noise).append(line)
    return OcrResult(_reading_order(lines), noise=noise, foreign=foreign)


def _reading_order(lines: list[OcrLine]) -> list[OcrLine]:
    """Top to bottom, then left to right within a row.

    A row is lines whose vertical centres sit within half a typical line height
    of the row's first line. Bucketing each line by its own height instead put
    a heading and the body text beside it into different rows.
    """
    if not lines:
        return lines
    heights = sorted(max(1, ln.box[3] - ln.box[1]) for ln in lines)
    tolerance = heights[len(heights) // 2] / 2
    rows: list[list[OcrLine]] = []
    anchor = None
    for ln in sorted(lines, key=lambda ln: ln.box[1] + ln.box[3]):
        mid = (ln.box[1] + ln.box[3]) / 2
        if anchor is None or mid - anchor > tolerance:
            rows.append([])
            anchor = mid
        rows[-1].append(ln)
    return [ln for row in rows for ln in sorted(row, key=lambda ln: ln.box[0])]


def _bbox(points, scale: float) -> tuple[int, int, int, int]:
    pts = np.asarray(points, dtype=float) * scale
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    return int(x0), int(y0), int(x1), int(y1)


# Chinese, Japanese and Korean characters. Brands here don't write in them; the engine produces them when
# it meets a script it has no model for.
_FOREIGN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")


# Glyphs the recogniser trades for one another in sans-serif type, where capital I and lowercase l are
# the same stroke: "#MadeInIndia" comes back as "#Madelnlndia" (evals/ocr, every time it appeared).
_LOOKALIKE = "Il1|"


def restore_names(text: str, names: list[str]) -> tuple[str, int]:
    """Put the brand's own names back where OCR read one of their I or l strokes as the other.

    Only those strokes are forgiven: case and every other letter must already match, so a name written
    in the wrong case or misspelt is left for the casing and terminology checks to find.
    """
    count = 0
    # Short names are skipped: "AI" would turn the name Al into it.
    wanted = {n for n in names if len(n) >= 4 and any(ch in _LOOKALIKE for ch in n)}
    for name in sorted(wanted, key=len, reverse=True):
        body = "".join(f"[{re.escape(_LOOKALIKE)}]" if ch in _LOOKALIKE else re.escape(ch) for ch in name)
        pattern = re.compile(rf"(?<![^\W_]){body}(?![^\W_])")

        def put(m: re.Match, name: str = name) -> str:
            nonlocal count
            count += m.group(0) != name
            return name

        text = pattern.sub(put, text)
    return text, count


def _foreign(text: str) -> bool:
    """Read from a script the engine has no model for: two or more such glyphs, or a quarter of the line."""
    n = len(_FOREIGN.findall(text))
    return n >= 2 or (n == 1 and n / max(1, len(text.replace(" ", ""))) >= 0.25)


def _meaningful(text: str, score: float) -> bool:
    """Drop OCR noise: detectors "read" texture in illustrations as a stray
    letter or two at low confidence. Treating that as text made every
    textless picture look unreadable (found by the black-box simulator)."""
    alnum = sum(ch.isalnum() for ch in text)
    return alnum >= 2 and not (alnum < 4 and score < 0.6) and score >= 0.3
