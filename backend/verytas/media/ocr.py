"""Local OCR (RapidOCR, PP-OCR models on onnxruntime, CPU only).

Local first on purpose: the text inside an image is found without the image
leaving the machine, so confidential terms in it can be blacked out before a
cloud vision model is ever asked to look (media/pixels.py).
"""

from __future__ import annotations

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
    lines, noise = [], []
    for i, (text, score, box) in enumerate(zip(out.txts, out.scores, out.boxes, strict=False)):
        line = OcrLine(text.strip(), float(score), _bbox(box, scale),
                       [(w, _bbox(b, scale)) for w, _, b in (words_per_line[i] if i < len(words_per_line) else ())
                        if w.strip()])
        (lines if _meaningful(text, float(score)) else noise).append(line)
    return OcrResult(_reading_order(lines), noise=noise)


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


def _meaningful(text: str, score: float) -> bool:
    """Drop OCR noise: detectors "read" texture in illustrations as a stray
    letter or two at low confidence. Treating that as text made every
    textless picture look unreadable (found by the black-box simulator)."""
    alnum = sum(ch.isalnum() for ch in text)
    return alnum >= 2 and not (alnum < 4 and score < 0.6) and score >= 0.3
