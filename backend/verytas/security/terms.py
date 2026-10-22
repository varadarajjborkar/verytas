"""Matching confidential terms the way people actually write them.

"Project Lumen" also appears as "Project-Lumen", "project_lumen", "ProjectLumen",
"Project  Lumen", a line-wrapped "Project\\nLumen", or "Project Lumens". Both the
leak check and the egress redactor need to catch those.

Two strictness levels:
  bounded : not glued to other letters or digits on either side, so "Zebra" does
            not fire inside "Zebrafish". Used for CONF-LEAK findings, where a false
            positive becomes a blocker.
  loose   : plain substring. Used for egress redaction, where over-redacting only
            costs the model a little context and under-redacting leaks a secret.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator
from functools import lru_cache

# Codepoints that render as nothing (or as blank) but split a word for a regex.
# Format characters (category Cf) cover soft hyphen, zero-width space and
# joiners, bidi marks and embeddings, invisible operators and the BOM; the rest
# are variation selectors, the combining grapheme joiner and Hangul fillers.
_BLANK = frozenset({0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0})


def _invisible(ch: str) -> bool:
    o = ord(ch)
    return (unicodedata.category(ch) == "Cf" or 0xFE00 <= o <= 0xFE0F or 0xE0100 <= o <= 0xE01EF
            or o in _BLANK)


# Cyrillic and Greek letters that are pixel-identical to Latin ones. NFKC
# leaves them alone (they are different letters), so they are mapped by hand,
# and only inside words that also contain Latin letters: a genuinely Cyrillic
# word like "\u0441\u043e\u0440" must stay itself, not become "cop".
_CONFUSABLES = {
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0445": "x", "\u0443": "y",
    "\u0456": "i", "\u0458": "j", "\u0455": "s", "\u0501": "d", "\u04bb": "h",
    "\u0410": "A", "\u0412": "B", "\u0415": "E", "\u041a": "K", "\u041c": "M", "\u041d": "H", "\u041e": "O",
    "\u0420": "P", "\u0421": "C", "\u0422": "T", "\u0425": "X", "\u0406": "I", "\u0408": "J", "\u0405": "S",
    "\u03bf": "o", "\u03b1": "a", "\u03b5": "e", "\u03b9": "i", "\u03ba": "k", "\u03bd": "v", "\u03c1": "p",
    "\u03c4": "t", "\u03c5": "u", "\u03c7": "x",
    "\u0391": "A", "\u0392": "B", "\u0395": "E", "\u0396": "Z", "\u0397": "H", "\u0399": "I", "\u039a": "K",
    "\u039c": "M", "\u039d": "N", "\u039f": "O", "\u03a1": "P", "\u03a4": "T", "\u03a5": "Y", "\u03a7": "X",
}
# Word-joining dashes that word processors and phones substitute for "-"
# (hyphen, non-breaking hyphen, figure dash, en dash, minus sign). Em dashes
# are left alone: they separate clauses, so "cheap\u2014really" must still match "cheap".
_DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2212": "-",
                         "\ufe63": "-"})
# Hyphenated and apostrophe compounds count as one word for the mixed-script
# test, so a look-alike first letter in "\u0415-mail" is still seen as a spoof.
_WORD = re.compile(r"\w+(?:[-']\w+)*")
_LATIN = re.compile(r"[A-Za-z]")


def fold(text: str) -> tuple[str, tuple[int, ...]]:
    """A matching copy of `text` plus, for each of its characters, the index
    of the original character it came from (with one sentinel at the end).

    Folding drops invisible characters, applies NFKC (full-width and other
    compatibility forms become plain ASCII), unifies word-joining dashes and
    maps look-alike letters to Latin inside mixed-script words. Case is kept,
    so the casing check still sees what was typed. Results are cached: every
    term and rule folds the same body.
    """
    return _fold(text)


@lru_cache(maxsize=256)
def _fold(text: str) -> tuple[str, tuple[int, ...]]:
    visible = [(i, unicodedata.normalize("NFKC", ch).translate(_DASHES))
               for i, ch in enumerate(text) if not _invisible(ch)]
    # Decide mixed-script words on the visible text, so a zero-width space
    # can't split "\u0441\u200bodename" into a "pure Cyrillic" part and a Latin part.
    joined = "".join(piece for _, piece in visible)
    owner = [k for k, (_, piece) in enumerate(visible) for _ in piece]
    mixed: set[int] = set()
    for m in _WORD.finditer(joined):
        word = m.group(0)
        if _LATIN.search(word) and any(c in _CONFUSABLES for c in word):
            mixed.update(owner[j] for j in range(m.start(), m.end()))

    out: list[str] = []
    index: list[int] = []
    for k, (i, piece) in enumerate(visible):
        if k in mixed:
            piece = "".join(_CONFUSABLES.get(c, c) for c in piece)
        for c in piece:
            out.append(c)
            index.append(i)
    index.append(len(text))
    return "".join(out), tuple(index)


def find_folded(pattern: re.Pattern[str], text: str) -> Iterator[tuple[int, int, str]]:
    """Matches of `pattern` in the folded text as (start, end, folded match),
    with start and end pointing into the original text."""
    folded, index = fold(text)
    for m in pattern.finditer(folded):
        if m.end() > m.start():
            yield index[m.start()], index[m.end() - 1] + 1, m.group(0)


def sub_folded(pattern: re.Pattern[str], text: str, repl: Callable[[str], str]) -> str:
    """Like pattern.sub, but matching on the folded text. `repl` receives the
    original substring, so a placeholder can still be mapped back to it.

    One original character can expand into several folded ones ("\ufb00" -> "ff"),
    so two matches may land on the same original character. Overlapping spans
    are merged into one replacement rather than spliced twice.
    """
    merged: list[list[int]] = []
    for start, end, _ in find_folded(pattern, text):
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for start, end in reversed(merged):
        text = text[:start] + repl(text[start:end]) + text[end:]
    return text


_SPLIT = re.compile(r"[\s_\-]+")
_SEP = r"[\s_\-]*"


def term_pattern(term: str, *, loose: bool = False) -> re.Pattern[str]:
    # Patterns run against folded text (find_folded), so fold the term too: an
    # admin who typed "Projekt\u2011Lumen" with a non-breaking hyphen still matches.
    parts = [re.escape(p) for p in _SPLIT.split(fold(term.strip())[0]) if p]
    if not parts:
        raise ValueError("empty confidential term")
    core = _SEP.join(parts) + r"(?:e?s)?"  # tolerate simple plurals
    if loose:
        return re.compile(core, re.IGNORECASE)
    return re.compile(rf"(?<![A-Za-z0-9]){core}(?![A-Za-z0-9])", re.IGNORECASE)
