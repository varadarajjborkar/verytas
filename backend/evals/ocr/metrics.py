"""Text-error metrics shared by the OCR and speech benchmarks (no third-party edit-distance package)."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from difflib import SequenceMatcher


def edit_distance(a: Sequence, b: Sequence) -> int:
    """Levenshtein distance over any two sequences (characters or words), two-row dynamic programme."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def squash(text: str) -> str:
    """NFKC, case-folded, every whitespace removed.

    Used for CER and for finding critical tokens: where a line break or a space falls is a segmentation
    question (WER answers it), not a question of whether the characters were read.
    """
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())


_EDGE = ".,!?:;\"'()[]"


def words(text: str) -> list[str]:
    """NFKC, case-folded whitespace tokens with sentence punctuation trimmed from their edges.

    Inner punctuation stays, so a price like "rs.1,499" or a URL is still one word.
    """
    toks = (t.strip(_EDGE) for t in unicodedata.normalize("NFKC", text).casefold().split())
    return [t for t in toks if t]


def cer(truth: str, got: str) -> tuple[int, int]:
    t, g = squash(truth), squash(got)
    return edit_distance(t, g), len(t)


def wer(truth: str, got: str) -> tuple[int, int]:
    t, g = words(truth), words(got)
    return edit_distance(t, g), len(t)


def bag_recall(truth: str, got: str) -> tuple[int, int]:
    """Truth words found in the output, order ignored (each output word is used once)."""
    t, g = Counter(words(truth)), Counter(words(got))
    return sum(min(n, g[w]) for w, n in t.items()), sum(t.values())


def substitutions(truth: str, got: str) -> Counter:
    """Character edits needed to turn the truth into the output, as ("a", "b") for a read as b."""
    out: Counter = Counter()
    for op, i1, i2, j1, j2 in SequenceMatcher(None, truth, got, autojunk=False).get_opcodes():
        if op == "replace" and i2 - i1 == j2 - j1:
            for x, y in zip(truth[i1:i2], got[j1:j2], strict=True):
                out[(x, y)] += 1
        elif op == "delete":
            for x in truth[i1:i2]:
                out[(x, "")] += 1
        elif op == "insert":
            for y in got[j1:j2]:
                out[("", y)] += 1
    return out
