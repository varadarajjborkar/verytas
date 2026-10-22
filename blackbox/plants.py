"""Planted violations and the variants a real writer (or a sneaky one) would use.

Every plant is an *arm*: a (family, variant) pair such as ("banned",
"homoglyph") or ("stat", "outdated:indian"). The evolver learns which arms the
system under test misses and spends more of each generation on them.

Expectations come from what a careful human reviewer holding the brand book
would say, never from how the tool is built: "game-changer" written with a
Cyrillic "\u0430" is still the banned word to a reader, so it should be flagged.
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

_HOMOGLYPH = {"a": "\u0430", "e": "\u0435", "o": "\u043e", "c": "\u0441", "p": "\u0440", "i": "\u0456"}
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
    # An emoji dropped into the phrase: "Project\U0001f525Lumen", "game\U0001f680changer".
    "emoji_split": ("evasion", lambda t: t.replace(" ", "\U0001f525", 1) if " " in t
                    else t[: len(t) // 2] + "\U0001f680" + t[len(t) // 2:]),
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
    # Drift, as the brief puts it: tone that changes partway, and posts that wander off the brand's subject.
    # Each lands as its own paragraph after an on-brand opening, which is how it happens in real drafts.
    "tone": {
        "hostile": ("flag", "tone", ["Honestly, anyone still doing it the old way is an idiot.",
                                     "If you still don't get it, that's pathetic. Shame on the rest of them."]),
        "slang": ("flag", "tone", ["ngl this one is lowkey the best bro, gonna sell out lol",
                                   "omg u have to try this fam, no cap"]),
        "sarcasm": ("flag", "tone", ["Oh great, another launch. Yeah right, as if anyone asked.",
                                     "Thanks a lot to everyone who said it couldn't be done. How original."]),
        "stiff": ("flag", "tone", [("Please be advised that, pursuant to the aforementioned launch, stakeholders "
                                    "shall be notified going forward."),
                                   "Kindly be informed that we will leverage synergies henceforth."]),
        "warm": ("clean", "tone", ["We can't wait to see what you make with it.",
                                   "Thanks for growing with us, {audience}. Tell us what you think."]),
    },
    "topic": {
        "politics": ("flag", "messaging", ["Also, the election was rigged and the minister must resign.",
                                           "Side note: the opposition's new manifesto is a disaster for voters."]),
        "crypto": ("flag", "messaging", [
            "Unrelated, but put your savings in bitcoin now, crypto is going to the moon.",
            "Quick stock tip while you're here: the Sensex rally isn't over, buy intraday."]),
        "betting": ("flag", "messaging", ["Bonus tip: the casino odds this weekend are the best they've been."]),
        "personal": ("flag", "messaging", [("Anyway, my girlfriend and I had a massive hangover "
                                            "after the party last night.")]),
        "on_topic": ("clean", "messaging", [("{product} ships to every city we serve, and support "
                                             "answers within a day.")]),
    },
    "emoji": {
        "gesture": ("flag", "messaging", ["To everyone who doubted us \U0001f595",
                                          "Haters gonna hate \U0001f595\U0001f595"]),
        "spam": ("flag", "accessibility", ["Sale is LIVE \U0001f525\U0001f525\U0001f525\U0001f525\U0001f525\U0001f525",
                                           "We did it \U0001f389\U0001f389\U0001f389\U0001f389\U0001f389"]),
        "friendly": ("clean", "messaging", ["Thanks for being here \U0001f60a", "See you there \U0001f44b"]),
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
    # Rule codes (prefixes) that count as catching a flag plant. Empty means any
    # finding in the category. Codes are part of the public output (citations),
    # so this is still black-box: it stops an unrelated finding in the same
    # category (a crop warning on a mascot image) from counting as a catch.
    codes: tuple[str, ...] = ()
    ref: str | None = None  # the reality term this plant spells, for the adversary

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
    if family == "media":
        return [f"media:{v}" for v in MEDIA_VARIANTS]
    if family == "mascot":
        return ["mascot:extended", "mascot:recoloured", "mascot:exact", "mascot:other_character"]
    if family == "alt":
        return ["alt:missing", "alt:filename", "alt:decorative", "alt:good"]
    if family == "contrast":
        return ["contrast:low", "contrast:large_borderline", "contrast:good"]
    raise KeyError(family)


def term_plant(family: str, variant: str, term: str, adversarial: list[str], rng: random.Random) -> Plant:
    category = "terminology" if family == "banned" else "confidentiality"
    codes = ("CONF-LEAK",) if family == "codename" else ()
    if variant == "adversarial":
        if adversarial:
            return Plant(family, variant, "adversarial", "flag", (category,), rng.choice(adversarial), codes=codes,
                         ref=term)
        # No adversarial spellings yet: this is a plain identity plant, recorded under that arm.
        variant = "identity"
    table = TEXT_VARIANTS | (CODENAME_EXTRA if family == "codename" else {})
    tier, fn = table[variant]
    return Plant(family, variant, tier, "flag", (category,), fn(term), codes=codes, ref=term)


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
    # A wrong figure is caught by the fact check, not by a generic "unsupported".
    codes = ("CLAIM-OUTDATED", "CLAIM-CONTRADICTED") if expect == "flag" else ()
    return Plant("stat", variant, "control" if expect == "clean" else "core", expect, ("claims",), text, codes=codes)


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


# --- media: text a reviewer would see inside an image, a document or a video -----------------------
# A codename or banned phrase that a person reading the post would plainly see
# must be flagged wherever it sits. tier "evasion" marks formats that are hard
# for machines but still legible to people.
MEDIA_VARIANTS: dict[str, str] = {
    "image_plain": "core", "image_stylised": "core", "image_low_contrast": "evasion",
    "pdf_layer": "core", "pdf_scan": "core", "pdf_screenshot": "core", "video_caption": "core",
}


def media_plant(variant: str, needle: str, needle_kind: str, rng: random.Random, case_no: str):
    """(Plant, attachments fragment, uploads) for one media plant. Uploads are
    (attachment key, local id, bytes, filename) the runner sends to /media first."""
    from blackbox import media

    category = "confidentiality" if needle_kind == "codename" else "terminology"
    lines = [rng.choice(["Coming soon:", "Sneak peek!", "This week only", "Big news"]), needle,
             rng.choice(["Stay tuned", "Link in bio", "Save the date"])]
    att_id = f"m{case_no}"
    tier = MEDIA_VARIANTS[variant]
    plant = Plant("media", variant, tier, "flag", (category,), needle, attachment=att_id,
                  codes=("CONF-LEAK",) if needle_kind == "codename" else ())
    if variant.startswith("image_"):
        img = media.text_card(lines, variant.split("_", 1)[1], rng)
        return plant, {"images": [{"id": att_id, "alt": "A promotional card", "media_type": "image/png",
                                   "data_base64": media.b64(media.png(img))}]}, []
    if variant == "pdf_layer":
        raw = media.pdf([{"text": ["Brand update", *lines]}, {"text": ["Thanks for reading."]}])
    elif variant == "pdf_scan":
        raw = media.scanned_pdf(media.text_card(lines, "plain", rng))
    elif variant == "pdf_screenshot":
        raw = media.pdf([{"text": ["Brand update", "Please see the picture below."],
                          "image": media.text_card(lines, "plain", rng)}])
    else:
        return plant, {}, [("videos", att_id, media.caption_video(lines), f"{att_id}.mp4")]
    return plant, {"documents": [{"id": att_id, "name": f"{att_id}.pdf", "media_type": "application/pdf",
                                  "data_base64": media.b64(raw)}]}, []


def mascot_plant(variant: str, colour: tuple[int, int, int], case_no: str):
    from blackbox import media

    att_id = f"k{case_no}"
    if variant == "other_character":
        img, expect, tier = media.other_character(), "clean", "control"
    elif variant == "exact":
        img, expect, tier = media.mascot_post(media.mascot(colour), colour, body=False), "clean", "control"
    elif variant == "recoloured":
        img, expect, tier = (media.mascot_post(media.mascot(colour, eye=(30, 140, 220)), colour, body=False),
                             "flag", "core")
    else:
        img, expect, tier = media.mascot_post(media.mascot(colour), colour, body=True), "flag", "core"
    # Only asset findings speak to the mascot, either way: a crop or safe-zone
    # note on the same image is neither a catch nor a false positive.
    plant = Plant("mascot", variant, tier, expect, ("visual",), "", attachment=att_id, codes=("VIS-ASSET",))
    return plant, {"images": [{"id": att_id, "alt": "Our mascot in a new post", "media_type": "image/png",
                               "data_base64": media.b64(media.png(img))}]}
