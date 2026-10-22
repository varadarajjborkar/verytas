"""Planted violations and the variants a real writer (or a sneaky one) would use.

Every plant is an *arm*: a (family, variant) pair such as ("banned",
"homoglyph") or ("stat", "outdated:indian"). The evolver learns which arms the
system under test misses and spends more of each generation on them.

Expectations come from what a careful human reviewer holding the brand book
would say, never from how the tool is built: "game-changer" written with a
Cyrillic "а" is still the banned word to a reader, so it should be flagged.
Controls (expect="clean") are things a reviewer would let through; flagging
them is a false positive.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass

# --- text variants -----------------------------------------------------------------------------
# tier "core": ordinary writing a brand checker must handle.
# tier "evasion": deliberate or accidental obfuscation a human still reads as the term.

_HOMOGLYPH = {"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "i": "і"}
_LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}


def _fullwidth(s: str) -> str:
    return "".join(chr(ord(ch) + 0xFEE0) if "!" <= ch <= "~" else ch for ch in s)


def _swap_first(s: str, table: dict[str, str]) -> str:
    for i, ch in enumerate(s):
        if ch.lower() in table:
            return s[:i] + table[ch.lower()] + s[i + 1:]
    return s


def _squash(s: str) -> str:
    return re.sub(r"[\s\-]+", "", s)


TEXT_VARIANTS: dict[str, tuple[str, callable]] = {
    "identity": ("core", lambda t: t),
    "upper": ("core", str.upper),
    "title": ("core", lambda t: t.title()),
    "plural": ("core", lambda t: t + "s" if t[-1:].isalpha() and not t.endswith("s") else t + "es"),
    "possessive": ("core", lambda t: t + "'s"),
    "markdown": ("core", lambda t: f"**{t}**"),
    "quoted": ("core", lambda t: f"“{t}”"),
    "hashtag": ("core", lambda t: "#" + _squash(t)),
    "squashed": ("evasion", _squash),
    "hyphen_swap": ("evasion", lambda t: t.replace("-", " ") if "-" in t else t.replace(" ", "-")),
    "zero_width": ("evasion", lambda t: t[:1] + "\u200b" + t[1:]),
    "homoglyph": ("evasion", lambda t: _swap_first(t, _HOMOGLYPH)),
    "fullwidth": ("evasion", _fullwidth),
    "leet": ("evasion", lambda t: "".join(_LEET.get(ch.lower(), ch) for ch in t)),
    "spaced": ("evasion", lambda t: " ".join(t.replace(" ", ""))),
    "line_break": ("evasion", lambda t: t.replace(" ", "\n", 1) if " " in t else t),
}

# A slug in a URL still names the project. (A tease like "Project K." was
# tried and dropped: no reviewer could tell it from any other initial.)
CODENAME_EXTRA: dict[str, tuple[str, callable]] = {
    "slug_url": ("evasion", lambda t: f"https://drops.example.com/{re.sub(r'[^a-z0-9]+', '-', t.lower())}"),
}


def casing_variants(correct: str) -> dict[str, tuple[str, str]]:
    out = {
        "lower": ("core", correct.lower()),
        "upper_first": ("core", correct[:1].upper() + correct[1:].lower()),
        "all_caps": ("core", correct.upper()),
        "lower_possessive": ("core", correct.lower() + "'s"),
    }
    return {k: v for k, v in out.items() if v[1] != correct}


# --- numbers -----------------------------------------------------------------------------------

def _indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


NUMBER_FORMATS: dict[str, callable] = {
    "plain": lambda n: str(n),
    "comma": lambda n: f"{n:,}",
    "indian": _indian,
    "k": lambda n: f"{n / 1000:g}k" if n >= 1000 and n % 100 == 0 else f"{n:,}",
    "words": lambda n: f"{n / 1000:g} thousand" if n >= 1000 and n % 100 == 0 else f"{n:,}",
    "plus": lambda n: f"{n:,}+",
}

# outdated: last year's approved value. inflated: well above the current one.
# supported / understated: true today, so a reviewer would pass them.
STAT_KINDS = {"outdated": "flag", "inflated": "flag", "supported": "clean", "understated": "clean"}


def stat_value(kind: str, old: int, new: int) -> tuple[int, str]:
    if kind == "outdated":
        return old, ""
    if kind == "inflated":
        return int(math.ceil(new * 2.2 / 10) * 10) if new >= 50 else new * 3, ""
    if kind == "understated":
        low = int(new * 0.8)
        return (low // 10 * 10 if low >= 100 else max(1, low)), "more than "
    return new, ""


# --- appended sentences (offline realism and families with no natural slot) ---------------------

APPENDED: dict[str, dict[str, tuple[str, str, list[str]]]] = {
    # family -> variant -> (expect, category, sentence choices with {brand}/{product})
    "superlative": {
        "number_one": ("flag", "claims", ["{brand} is the #1 {industry} brand in the world.",
                                          "Officially the number one choice for {audience}."]),
        "fastest": ("flag", "claims", ["{product} is the fastest in the market, full stop.",
                                       "Nobody does it faster than {brand}. Nobody."]),
        "only": ("flag", "claims", ["We are the only {industry} brand that truly gets {audience}."]),
    },
    "caps": {
        "shout": ("flag", "accessibility", ["THIS IS THE BIGGEST DROP OF THE YEAR AND YOU ARE NOT READY",
                                            "DO NOT SCROLL PAST THIS ONE SERIOUSLY"]),
        "acronyms": ("clean", "accessibility", ["Works with UPI, NFC and GST invoices out of the box.",
                                                "Now on iOS and Android via the API."]),
    },
    "hashtag": {
        "long_lower": ("flag", "accessibility", ["#bestdealsofthesummerseasonever", "#neverstopshowingupforyourself"]),
        "camel": ("clean", "accessibility", ["#BestDealsOfTheSummer", "#NeverStopShowingUp"]),
    },
    "link": {
        "click_here": ("flag", "accessibility", ["Want in? [Click here](https://example.com/join).",
                                                 "Details: [here](https://example.com/details)"]),
        "descriptive": ("clean", "accessibility", ["Read the [full pricing guide](https://example.com/pricing)."]),
    },
    "hype": {
        "brand_forbidden": ("flag", "tone", []),  # filled from the reality's own hype examples
    },
}


@dataclass
class Plant:
    family: str
    variant: str
    tier: str  # core | evasion | adversarial | control
    expect: str  # flag | clean
    categories: tuple[str, ...]
    text: str
    start: int = -1
    end: int = -1
    attachment: str | None = None  # image id or "colors" for attachment plants

    @property
    def arm(self) -> str:
        return f"{self.family}:{self.variant}"


def arms_for(family: str) -> list[str]:
    if family in ("banned", "codename"):
        names = list(TEXT_VARIANTS) + (list(CODENAME_EXTRA) if family == "codename" else []) + ["adversarial"]
        return [f"{family}:{v}" for v in names]
    if family == "casing":
        return [f"casing:{v}" for v in ("lower", "upper_first", "all_caps", "lower_possessive", "correct")]
    if family == "stat":
        # "3,000+" with last year's 3,000 is still true when the count grew, so
        # a reviewer can't call it wrong; that pairing has no clear verdict.
        return [f"stat:{k}:{f}" for k in STAT_KINDS for f in NUMBER_FORMATS
                if not (k == "outdated" and f == "plus")]
    if family in APPENDED:
        return [f"{family}:{v}" for v in APPENDED[family]]
    if family == "alt":
        return ["alt:missing", "alt:filename", "alt:decorative", "alt:good"]
    if family == "contrast":
        return ["contrast:low", "contrast:large_borderline", "contrast:good"]
    raise KeyError(family)


def term_plant(family: str, variant: str, term: str, adversarial: list[str], rng: random.Random) -> Plant:
    category = "terminology" if family == "banned" else "confidentiality"
    if variant == "adversarial":
        text = rng.choice(adversarial) if adversarial else term
        return Plant(family, variant, "adversarial" if adversarial else "core", "flag", (category,), text)
    table = TEXT_VARIANTS | (CODENAME_EXTRA if family == "codename" else {})
    tier, fn = table[variant]
    return Plant(family, variant, tier, "flag", (category,), fn(term))


def casing_plant(variant: str, correct: str) -> Plant:
    if variant == "correct":
        return Plant("casing", "correct", "control", "clean", ("terminology",), correct)
    choices = casing_variants(correct)
    if variant not in choices:
        return Plant("casing", "correct", "control", "clean", ("terminology",), correct)
    tier, text = choices[variant]
    return Plant("casing", variant, tier, "flag", ("terminology",), text)


def stat_plant(variant: str, old: int, new: int, percent: bool) -> Plant:
    kind, fmt = variant.split(":")
    value, prefix = stat_value(kind, old, new)
    text = prefix + NUMBER_FORMATS[fmt](value) + ("%" if percent else "")
    expect = STAT_KINDS[kind]
    return Plant("stat", variant, "control" if expect == "clean" else "core", expect, ("claims",), text)


def appended_plant(family: str, variant: str, ctx: dict[str, str], hype: list[str], rng: random.Random) -> Plant:
    expect, category, choices = APPENDED[family][variant]
    text = rng.choice(hype if family == "hype" else choices).format(**ctx)
    return Plant(family, variant, "control" if expect == "clean" else "core", expect, (category,), text)


def attachment_plant(arm: str) -> tuple[Plant, dict]:
    """Returns the plant and the attachment payload fragment it adds."""
    family, variant = arm.split(":")
    if family == "alt":
        img = {"id": f"img{variant}", "media_type": "image/png", "decorative": variant == "decorative",
               "alt": {"missing": None, "filename": "IMG_20260412_0931.png", "decorative": None,
                       "good": "A runner drinking from a cold can after a race"}[variant]}
        expect = "flag" if variant in ("missing", "filename") else "clean"
        tier = "core" if variant == "missing" else "evasion" if variant == "filename" else "control"
        return Plant("alt", variant, tier, expect, ("accessibility",), "", attachment=img["id"]), {"images": [img]}
    pair = {"low": {"fg": "#9a9a9a", "bg": "#b0b0b0", "large": False},
            "large_borderline": {"fg": "#767676", "bg": "#ffffff", "large": True},
            "good": {"fg": "#111111", "bg": "#ffffff", "large": False}}[variant]
    expect = "flag" if variant == "low" else "clean"
    return (Plant("contrast", variant, "core" if expect == "flag" else "control", expect, ("accessibility",), "",
                  attachment="colors"), {"colors": [{**pair, "where": "hero banner"}]})
