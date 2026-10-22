"""Flesch-Kincaid grade level with a heuristic syllable counter.

Owned here rather than pulled from a library because the common packages fetch
pronunciation dictionaries over the network at first use, which is slow and
breaks in locked-down deployments. The heuristic is within about one grade of
dictionary-based counts on ordinary prose, which is plenty for a threshold check.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_SENTENCE = re.compile(r"[.!?]+(?=\s|$)")
_VOWEL_GROUPS = re.compile(r"[aeiouy]+")


def count_syllables(word: str) -> int:
    w = word.lower().strip("'")
    if len(w) <= 3:
        return 1
    # Silent endings: "make", "named", "takes" (but keep "-le" as in "table").
    w = re.sub(r"(?:[^laeiouy]es|[^laeiouy]ed|[^laeiouy]e)$", lambda m: m.group(0)[0], w)
    w = re.sub(r"^y", "", w)
    return max(1, len(_VOWEL_GROUPS.findall(w)))


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def sentence_count(text: str) -> int:
    return max(1, len(_SENTENCE.findall(text.strip())) or 1)


def flesch_kincaid_grade(text: str) -> float:
    ws = words(text)
    if not ws:
        return 0.0
    syllables = sum(count_syllables(w) for w in ws)
    return 0.39 * (len(ws) / sentence_count(text)) + 11.8 * (syllables / len(ws)) - 15.59
