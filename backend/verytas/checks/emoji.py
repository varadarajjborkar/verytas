"""Emoji: meaning, evasion and accessibility.

Emoji carry meaning of their own, and much of it is coded: sexual innuendo,
drug slang, mockery, gestures, flags and religious symbols. Most of it
depends entirely on context (a peach in a smoothie post is a peach), so
lexicon hits are not flagged outright: they go to the judge with their known
slang reading and the surrounding text, and only a likely reading becomes a
finding (prism/onion.py). One gesture is never on-brand and is flagged
directly.

The lexicon is data, dated and meant to be edited: slang moves fast, and a
brand can add its own banned emoji with a `banned_emoji` rule.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass

# As of October 2026. Readings are the common online slang meaning, which is
# what a brand risks being read as, not the only meaning.
LEXICON: dict[str, tuple[str, str]] = {
    "\U0001f346": ("sexual", "eggplant: common sexual innuendo"),
    "\U0001f351": ("sexual", "peach: common innuendo for buttocks"),
    "\U0001f4a6": ("sexual", "sweat droplets: common sexual innuendo"),
    "\U0001f445": ("sexual", "tongue: often sexual innuendo"),
    "\U0001f975": ("sexual", "hot face: often reads as sexual arousal"),
    "\U0001f33f": ("drugs", "herb: slang for cannabis"),
    "\U0001f341": ("drugs", "leaf: slang for cannabis"),
    "\U0001f343": ("drugs", "leaves: slang for cannabis"),
    "\u2744": ("drugs", "snowflake: slang for cocaine"),
    "\U0001f50c": ("drugs", "plug: slang for a drug dealer"),
    "\U0001f48a": ("drugs", "pill: drug use"),
    "\U0001f344": ("drugs", "mushroom: slang for psychedelics"),
    "\U0001f489": ("drugs", "syringe: drug use"),
    "\U0001f52b": ("violence", "pistol: firearms"),
    "\U0001f52a": ("violence", "knife: violence"),
    "\U0001f4a3": ("violence", "bomb: violence"),
    "\U0001fa78": ("violence", "blood: violence or gore"),
    "\U0001f921": ("mockery", "clown: calls someone a fool"),
    "\U0001f40d": ("mockery", "snake: calls someone a traitor"),
    "\U0001f9e2": ("mockery", "cap: 'cap' means lying"),
    "\U0001f5d1": ("mockery", "wastebasket: calls something trash"),
    "\U0001f412": ("slur_risk", "monkey: used as a racist slur when aimed at people"),
    "\U0001f98d": ("slur_risk", "gorilla: used as a racist slur when aimed at people"),
    "\U0001f435": ("slur_risk", "monkey face: used as a racist slur when aimed at people"),
    "\u271d": ("religious", "cross: religious symbol"),
    "\u262a": ("religious", "star and crescent: religious symbol"),
    "\U0001f549": ("religious", "om: religious symbol"),
    "\u2721": ("religious", "star of David: religious symbol"),
    "\u2626": ("religious", "Orthodox cross: religious symbol"),
    "\U0001f6d0": ("religious", "place of worship: religious symbol"),
    "\U0001f911": ("financial_promise", "money face: next to an offer it can read as a promise of returns"),
    "\U0001f4b0": ("financial_promise", "money bag: next to an offer it can read as a promise of returns"),
    "\U0001f4b8": ("financial_promise", "flying money: next to an offer it can read as a promise of returns"),
}
# Never on-brand, whatever the context.
ALWAYS = {"\U0001f595": "middle finger: an obscene gesture"}

# Pictographs (U+1F000 and up, minus the letter-like enclosed alphanumerics
# that read as letters) are emoji on their own. Older symbols (arrows, stars,
# check marks, (c), TM) are plain text unless they carry the emoji variation
# selector or are among the few that default to emoji presentation.
_PICTO = ((0x1F000, 0x1F0FF), (0x1F18E, 0x1F18E), (0x1F191, 0x1F19A), (0x1F1E6, 0x1F1FF), (0x1F200, 0x1FAFF))
_DEFAULT_EMOJI = set(
    "\u231a\u231b\u23e9\u23ea\u23eb\u23ec\u23f0\u23f3\u25fd\u25fe\u2614\u2615\u267f\u2693\u26a1"
    "\u26aa\u26ab\u26bd\u26be\u26c4\u26c5\u26ce\u26d4\u26ea\u26f2\u26f3\u26f5\u26fa\u26fd\u2705"
    "\u270a\u270b\u2728\u274c\u274e\u2753\u2754\u2755\u2757\u2795\u2796\u2797\u27b0\u27bf\u2b1b"
    "\u2b1c\u2b50\u2b55" + "".join(chr(c) for c in range(0x2648, 0x2654)))
_TEXT_SYMBOLS = ((0x00A9, 0x00A9), (0x00AE, 0x00AE), (0x203C, 0x203C), (0x2049, 0x2049), (0x2122, 0x2122),
                 (0x2139, 0x2139), (0x2194, 0x21AA), (0x2300, 0x23FF), (0x24C2, 0x24C2), (0x25AA, 0x25FE),
                 (0x2600, 0x27BF), (0x2934, 0x2935), (0x2B05, 0x2B55), (0x3030, 0x3030), (0x303D, 0x303D),
                 (0x3297, 0x3299), (0x1F170, 0x1F189))
_KEYCAP = "\u20e3"


def _is_ri(ch: str) -> bool:
    return 0x1F1E6 <= ord(ch) <= 0x1F1FF


def is_emoji(ch: str, following: str = "") -> bool:
    """Whether `ch` is shown as an emoji; `following` is the next character, if any.

    Lexicon entries count whatever their presentation: a plain-text snowflake
    carries the same slang as the emoji one.
    """
    o = ord(ch)
    if any(a <= o <= b for a, b in _PICTO) or ch in _DEFAULT_EMOJI or ch in LEXICON or ch in ALWAYS:
        return True
    return following == "\ufe0f" and any(a <= o <= b for a, b in _TEXT_SYMBOLS)


@dataclass
class EmojiHit:
    start: int
    end: int
    emoji: str
    kind: str
    reading: str


def _clusters(text: str) -> Iterator[tuple[int, int, str]]:
    """Emoji with their modifiers (skin tone, variation selector, ZWJ sequences, keycaps) as one unit."""
    i, n = 0, len(text)
    while i < n:
        nxt = text[i + 1] if i + 1 < n else ""
        keycap = text[i] in "0123456789#*" and (nxt == _KEYCAP or (nxt == "\ufe0f" and text[i + 2:i + 3] == _KEYCAP))
        if keycap or is_emoji(text[i], nxt):
            j = i + 1
            # A flag is two regional-indicator letters read as one symbol.
            if _is_ri(text[i]) and j < n and _is_ri(text[j]):
                j += 1
            while j < n and (0x1F3FB <= ord(text[j]) <= 0x1F3FF or text[j] in "\ufe0f\u200d" + _KEYCAP
                             or (text[j - 1] == "\u200d" and is_emoji(text[j], text[j + 1:j + 2]))):
                j += 1
            yield i, j, text[i:j]
            i = j
        else:
            i += 1


def lexicon_hits(text: str) -> list[EmojiHit]:
    hits = []
    for start, end, cluster in _clusters(text):
        base = cluster[0]
        if base in ALWAYS:
            hits.append(EmojiHit(start, end, cluster, "gesture", ALWAYS[base]))
        elif base in LEXICON:
            kind, reading = LEXICON[base]
            hits.append(EmojiHit(start, end, cluster, kind, reading))
        elif _is_ri(base) and len(cluster) >= 2:
            hits.append(EmojiHit(start, end, cluster, "political", "flag: national flags carry political meaning"))
    return hits


def count(text: str) -> int:
    return sum(1 for _ in _clusters(text))


_RUN = re.compile(r"(?:[\U0001F000-\U0001FAFF☀-➿⌀-⏿][️‍\U0001F3FB-\U0001F3FF]*\s?){4,}")


def accessibility_issues(text: str, max_run: int = 3) -> list[tuple[int, int, str]]:
    """(start, end, problem) for emoji that get in the way of screen-reader users.

    Screen readers read every emoji's full name aloud ("face with tears of
    joy"), so long runs become noise, and an emoji inside a word breaks the
    word in two.
    """
    out = []
    clusters = list(_clusters(text))
    run_start, run_end, run_len = None, None, 0
    for start, end, _ in clusters + [(len(text) + 10, len(text) + 10, "")]:
        if run_start is not None and text[run_end:start].strip() == "" and start - run_end <= 1:
            run_end, run_len = end, run_len + 1
            continue
        if run_start is not None and run_len > max_run:
            out.append((run_start, run_end, f"{run_len} emoji in a row; screen readers read each one's name aloud"))
        run_start, run_end, run_len = start, end, 1
    for start, end, cluster in clusters:
        before = text[start - 1] if start > 0 else " "
        after = text[end] if end < len(text) else " "
        if before.isalpha() and after.isalpha():
            names = unicodedata.name(cluster[0], "emoji").lower()
            out.append((start, end, f"emoji inside a word; read aloud as “{names}” mid-word"))
    return out
