"""Figures that must read the same wherever a post states them.

A post is read as a whole: the caption, the poster, the voice-over and the on-screen text. When two of
them give a different price, discount, rate or count for the same thing, whichever one the viewer
believes, the other misleads them. Each part is already checked on its own against the brand's facts;
this module compares the parts with each other, which no single text check can do.

Everything here is plain code on text the media agents already read. A figure is a number with what it
is about (its "key"): a price with its currency and period, a percentage with the word it qualifies, a
count with its noun. Two figures conflict only when they share a key and no reading makes both true
("up to 50% off" agrees with "30% off"; "50% off" does not). A part that states several figures for the
same key (a price list, three plans) is ambiguous and is not compared: a false alarm on every pricing
table would teach reviewers to ignore the check.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from verytas.checks.phonetic import edit_distance, spelling

_NUM = r"\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_MULT = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7,
         "cr": 1e7, "million": 1e6, "mn": 1e6}
_MULT_RE = r"k|thousand|lakhs?|lac|crores?|cr|million|mn"
_CURRENCY = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "rupees": "INR", "/-": "INR", "$": "USD",
             "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP"}
_PERIOD = {"month": "month", "mo": "month", "monthly": "month", "year": "year", "yr": "year", "annum": "year",
           "yearly": "year", "annually": "year", "week": "week", "day": "day", "session": "session",
           "class": "class", "kg": "kg", "user": "user", "seat": "seat", "person": "person"}

_PRICE_BEFORE = re.compile(
    rf"(?P<cur>₹|\$|€|£|\b(?:rs\.?|inr|usd|eur|gbp)(?![a-z]))\s?(?P<num>{_NUM})(?:\s?(?P<mult>{_MULT_RE})\b)?",
    re.IGNORECASE)
_PRICE_AFTER = re.compile(rf"(?<![\w.,])(?P<num>{_NUM})(?:\s?(?P<mult>{_MULT_RE})\b)?\s?(?P<cur>/-|rupees\b|rs\b\.?)",
                          re.IGNORECASE)
_PER = re.compile(r"\s*(?:/|per\b|a\b|an\b|every\b)\s*(?P<per>[a-z]+)|\s+(?P<adv>monthly|yearly|annually)\b",
                  re.IGNORECASE)
_PERCENT = re.compile(rf"(?<![\w.,])(?P<num>{_NUM})\s?(?:%|percent\b|per cent\b)", re.IGNORECASE)
_COUNT = re.compile(rf"(?<![\w.,@#₹$€£/])(?P<num>{_NUM})(?:\s?(?P<mult>{_MULT_RE})\b)?(?P<plus>\+)?"
                    r"(?:\s|-)(?P<noun>[a-z]{2,})", re.IGNORECASE)
# Dotted abbreviations ("p.a.") are one word, but a full stop is not part of the word before it ("off.").
# Devanagari words too (not the danda), but only the topics listed below count; others are passed over.
_WORD = re.compile(r"[a-z]+(?:\.[a-z]+)*|[\u0900-\u0963\u0966-\u097f]+", re.IGNORECASE)
# "20-30% off", "₹499-999", "3 to 5 days": both ends are one figure, a span of values.
_RANGE = re.compile(rf"(?P<lo>{_NUM})\s?(?:-|–|to)\s?(?:₹|rs\.?\s?)?(?P<hi>{_NUM})", re.IGNORECASE)
# What a price is for, from the words around it. A discount ("Rs 500 off"), a prize ("worth ₹10,000") or a
# spend threshold ("on orders above Rs 999") is a different number from what the thing costs.
_PRICE_OFF_AFTER = re.compile(r"\s*(?:off|discount|cash\s?back|back)\b", re.IGNORECASE)
_PRICE_OFF_BEFORE = re.compile(r"(?:save|saving|discount of|cash\s?back of|get back|off)\s*$", re.IGNORECASE)
_PRICE_PRIZE = re.compile(r"(?:worth|prizes?|win|won|scholarships?|rewards?|vouchers?|gifts?|jackpot)\b[\w ]{0,12}$",
                          re.IGNORECASE)
_PRICE_SPEND = re.compile(r"(?:above|over|more than|minimum|min\.?|orders?(?: of| above| over)?|spend|spending|"
                          r"purchases?(?: of| above| over)?)\s*$", re.IGNORECASE)
MAX_FIGURES = 400  # per source: past this a text is a catalogue, and every comparison would be ambiguous
# A line that is nothing but an amount ("3,499"): on a poster that is a price tag whose currency sign OCR
# dropped (it often misses the rupee sign). Thousands grouping is required, so a lone "15" is not a price.
_TAG_LINE = re.compile(r"^\s*(?P<num>\d{1,2}(?:,\d{2})+,\d{3}|\d{1,3}(?:,\d{3})+)(?:\.\d{2})?\s*(?:/-)?\s*$",
                       re.MULTILINE)
# Speech recognition writes "40% off today" as "40% of today": "of" before these is the discount. Only words
# that can't follow a share ("60% of all customers" is a share, not a sale).
_SPOKEN_OFF = re.compile(r"\s+of\s+(?:today|now|sitewide|storewide|everything|"
                         r"this\s+(?:week|month|weekend|season|sale|festive))\b", re.IGNORECASE)
_YEAR = re.compile(r"^(?:19|20)\d{2}$")

_AT_MOST = ("up to", "upto", "under", "below", "less than", "max", "maximum", "at most", "within")
_AT_LEAST = ("over", "more than", "above", "at least", "from", "starting at", "starts at", "starting from",
             "min", "minimum")
# Words that say nothing about what a figure is: skipped when looking for its topic.
_FILLER = frozenset({
    "of", "on", "the", "a", "an", "all", "every", "your", "our", "flat", "extra", "more", "less", "up", "to",
    "for", "in", "at", "and", "or", "with", "just", "only", "now", "today", "free", "full", "money",
    "back", "no", "new", "happy", "+", "is", "are", "was", "be", "will", "get", "you", "we", "this", "that",
    "it", "from", "by", "per", "over", "nearly", "almost", "about", "around",
    # Hindi and Hinglish speech: "40% tak ki chhoot", "40% की बचत"
    "ki", "ka", "ke", "tak", "की", "का", "के", "तक",
})
_PERCENT_TOPIC = {"discount": "off", "discounts": "off", "off": "off", "savings": "off", "save": "off",
                  "cashback": "cashback", "interest": "interest", "returns": "returns", "return": "returns",
                  "apr": "interest", "p.a": "interest", "pa": "interest",
                  "chhoot": "off", "chhut": "off", "chut": "off", "bachat": "off", "छूट": "off", "छुट": "off",
                  "बचत": "off"}
_TIME_UNITS = {"day", "days", "week", "weeks", "month", "months", "year", "years", "hour", "hours", "hr", "hrs",
               "minute", "minutes", "min", "mins"}
# Nouns a count can't be compared by: clock times, ordinals, multiplication signs, months.
_NOT_NOUNS = frozenset({"am", "pm", "st", "nd", "rd", "th", "x", "jan", "feb", "mar", "apr", "may", "jun", "jul",
                        "aug", "sep", "sept", "oct", "nov", "dec", "january", "february", "march", "april", "june",
                        "july", "august", "september", "october", "november", "december", "and", "or", "to", "of",
                        "in", "on", "at", "for", "the", "is", "are", "with", "by", "per", "percent", "rs",
                        "rupees", "inr", "usd", "lakh", "lakhs", "crore", "crores", "k", "out"})


@dataclass(frozen=True)
class Figure:
    """A number in one source with what it is about."""

    source: str
    key: str  # "price:INR:month", "percent:off", "count:student", "count:day:trial"
    value: float
    bound: str | None  # "max" for "up to X", "min" for "X+" or "from X", None for an exact figure
    start: int  # the figure's span in the source text
    end: int
    quote: str
    time: tuple[float, float] | None = None
    inferred: bool = False  # what it is about was guessed (a price tag that lost its currency sign)
    low: float | None = None  # the lower end of a range ("20-30%"); `value` is then the upper end

    @property
    def kind(self) -> str:
        return self.key.split(":", 1)[0]


def _value(num: str, mult: str | None) -> float:
    v = float(num.replace(",", ""))
    return v * _MULT[mult.lower()] if mult else v


def _bound(text: str, start: int, end: int) -> str | None:
    before = text[max(0, start - 16):start].lower()
    if re.match(rf"\s?(?:{_MULT_RE})?\+", text[end:end + 12], re.IGNORECASE):
        return "min"
    if any(re.search(rf"(?<![a-z]){re.escape(w)}\s*$", before) for w in _AT_MOST):
        return "max"
    if any(re.search(rf"(?<![a-z]){re.escape(w)}\s*$", before) for w in _AT_LEAST):
        return "min"
    return None


def _singular(word: str) -> str:
    w = word.lower().rstrip(".")
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


_HINDI_PARTICLES = frozenset({"ki", "ka", "ke", "tak", "की", "का", "के", "तक"})
# "chhoot" (discount) and "bachat" (saving), which Whisper writes "चुड", "बच्चत", "बाचवत", "Bachat".
_OFF_SPELLINGS = frozenset(spelling(w) for w in ("chhoot", "chhut", "bachat", "छूट", "बचत"))


def _heard_off(text: str, end: int) -> bool:
    """Whether speech names a discount in Hindi that the recogniser misspelt: "40% की बच्चत", "40% ki chhoog".
    Only right after a Hindi particle, so English "40% of the budget" is never read as a sale, and by the
    vowel-keeping spelling, so "ke baad", "ki baat" and "ka bazaar" are not "bachat"."""
    words = [w.group(0).lower() for w in itertools.islice(_WORD.finditer(text, end), 3)]
    lead = list(itertools.takewhile(lambda w: w in _HINDI_PARTICLES, words))
    if not lead or len(lead) == len(words):
        return False
    heard = spelling(words[len(lead)])
    return any(heard == s or (len(heard) >= 4 and heard[0] == s[0] and edit_distance(heard, s) <= 1)
               for s in _OFF_SPELLINGS)


def _topic_after(text: str, end: int, limit: int = 4) -> tuple[str, int] | tuple[None, None]:
    """The first word after a figure that says what it is, and where that word ends."""
    for m in itertools.islice(_WORD.finditer(text, end), limit):
        w = m.group(0).lower()
        if w in _FILLER or (not w.isascii() and w not in _PERCENT_TOPIC):
            continue
        return w, m.end()
    return None, None


def _time_at(timeline: list[tuple[int, int, float, float]], at: int) -> tuple[float, float] | None:
    for c0, c1, t0, t1 in timeline:
        if c0 <= at < c1:
            return (t0, t1)
    return None


TAG = "price:tag"


def figures(source_id: str, text: str, timeline: list[tuple[int, int, float, float]] | None = None,
            kind: str | None = None) -> list[Figure]:
    """Every comparable figure in a text. A number is read once: a price is not also a count.

    `kind` is the source's (Source.kind): text read off pixels may hold price tags without their
    currency sign, and transcribed speech hears "off" as "of"."""
    from verytas.checks.claims import not_quantities

    out: list[Figure] = []
    taken = bytearray(len(text) + 1)
    for a, b in not_quantities(text):  # phone numbers, clock times, opening hours
        taken[a:b] = b"\x01" * (b - a)
    ranges_lo = {m.start("lo"): m for m in _RANGE.finditer(text)}
    ranges_hi = {m.start("hi"): m for m in ranges_lo.values()}

    def free(a: int, b: int) -> bool:
        return not any(taken[a:b])

    def add(key: str, value: float, a: int, num_start: int, num_end: int, quote_end: int) -> None:
        if len(out) >= MAX_FIGURES:
            return
        low = None
        if (r := ranges_lo.get(num_start)) is not None and value == _value(r.group("lo"), None):
            # The low end of a range was matched ("₹499" of "₹499-999"): the figure is the whole range.
            low, value, num_end, quote_end = value, _value(r.group("hi"), None), r.end("hi"), max(quote_end, r.end())
        elif (r := ranges_hi.get(num_start)) is not None:
            low, a = _value(r.group("lo"), None), min(a, r.start("lo"))
        taken[a:quote_end] = b"\x01" * (quote_end - a)
        out.append(Figure(source_id, key, value, None if low is not None else _bound(text, a, num_end), a,
                          quote_end, text[a:quote_end], _time_at(timeline or [], a), low=low))

    for rx in (_PRICE_BEFORE, _PRICE_AFTER):
        for m in rx.finditer(text):
            if not free(m.start(), m.end()):
                continue
            cur = _CURRENCY.get(m.group("cur").lower().rstrip(), "INR")
            end = m.end()
            per = _PER.match(text, end)
            period = None
            if per:
                word = (per.group("per") or per.group("adv") or "").lower()
                period = _PERIOD.get(word) or _PERIOD.get(_singular(word))
                if period:
                    end = per.end()
            before = text[max(0, m.start() - 30):m.start()]
            role = ("off" if _PRICE_OFF_AFTER.match(text, end) or _PRICE_OFF_BEFORE.search(before)
                    else "prize" if _PRICE_PRIZE.search(before)
                    else "spend" if _PRICE_SPEND.search(before) else None)
            key = f"price:{cur}" + (f":{period}" if period else "") + (f":{role}" if role else "")
            add(key, _value(m.group("num"), m.group("mult")), m.start(), m.start("num"), m.end(), end)

    for m in _PERCENT.finditer(text):
        if not free(m.start(), m.end()):
            continue
        topic, topic_end = _topic_after(text, m.end())
        named = _PERCENT_TOPIC.get(topic or "")
        if named is None and kind == "speech" and _heard_off(text, m.end()):
            named, topic_end = "off", None
        if named is None and kind == "speech" and _SPOKEN_OFF.match(text, m.end()):
            named, topic_end = "off", None  # quoted as the bare figure: "40% of" would read as a typo
        # The quote reads "30% OFF" rather than "30%" when the word follows straight on.
        quote_end = topic_end if named and topic_end is not None and topic_end - m.end() <= 12 else m.end()
        if named is None:
            lead = [w.group(0).lower() for w in _WORD.finditer(text[max(0, m.start() - 24):m.start()])][-2:]
            named = next((_PERCENT_TOPIC[w] for w in reversed(lead) if w in _PERCENT_TOPIC), None)
        if named is None and topic:
            named = _singular(topic)
        if not named:
            continue
        add(f"percent:{named}", _value(m.group("num"), None), m.start(), m.start("num"), m.end("num"), quote_end)

    if kind in ("ocr", "captions"):
        for m in _TAG_LINE.finditer(text):
            if free(m.start("num"), m.end("num")):
                add(TAG, _value(m.group("num"), None), m.start("num"), m.start("num"), m.end("num"), m.end("num"))

    for m in _COUNT.finditer(text):
        a, b = m.start("num"), m.end("num")
        if not free(a, m.end()):
            continue
        num, noun = m.group("num"), m.group("noun").lower()
        if (_YEAR.match(num) and not m.group("mult")) or noun in _NOT_NOUNS or len(num.replace(",", "")) > 7:
            continue
        key = f"count:{_singular(noun)}"
        if noun in _TIME_UNITS:
            # "7-day trial" and "30-day refund" are different promises: a time span is keyed by what it is.
            what, _ = _topic_after(text, m.end(), 3)
            if not what or what in _TIME_UNITS:
                continue
            key = f"count:{_singular(noun)}:{_singular(what)}"
        add(key, _value(num, m.group("mult")), a, a, b, m.end())
    return sorted(out, key=lambda f: f.start)


def agree(a: Figure, b: Figure) -> bool:
    """Can both be true? "Up to 50%" allows 30%; "from ₹499" allows ₹999; exact figures must be equal."""
    lo_a, hi_a = _range(a)
    lo_b, hi_b = _range(b)
    return lo_a <= hi_b and lo_b <= hi_a


def _range(f: Figure) -> tuple[float, float]:
    tol = max(abs(f.value) * 0.005, 1e-9)  # "₹4,999" and "₹4999.00" are one price
    if f.low is not None:
        return (f.low - tol, f.value + tol)
    if f.bound == "max":
        return (float("-inf"), f.value + tol)
    if f.bound == "min":
        return (f.value - tol, float("inf"))
    return (f.value - tol, f.value + tol)


@dataclass(frozen=True)
class Conflict:
    """`anchor` is the figure the finding points at; `other` the one it disagrees with."""

    anchor: Figure
    other: Figure


def compare_pools(anchor_pool: list[Figure], other_pool: list[Figure]) -> list[Conflict]:
    """Untimed parts (the caption against an image): one figure per key on each side, or no comparison."""
    other_pool = _priced_tags(anchor_pool, other_pool)
    out = []
    for key in {f.key for f in anchor_pool} & {f.key for f in other_pool}:
        mine = _distinct([f for f in anchor_pool if f.key == key])
        theirs = _distinct([f for f in other_pool if f.key == key])
        if len(mine) == 1 and len(theirs) == 1 and not agree(mine[0], theirs[0]):
            out.append(Conflict(mine[0], theirs[0]))
    return out


TIME_SLACK_S = 3.0  # a voice-over leads or trails the matching on-screen text by a few seconds


def compare_timed(anchor_pool: list[Figure], other_pool: list[Figure]) -> list[Conflict]:
    """Two timed parts of one video: figures for the same key said and shown at about the same moment."""
    out = []
    for f in anchor_pool:
        if f.time is None:
            continue
        near = [g for g in other_pool if g.key == f.key and g.time is not None
                and g.time[0] - TIME_SLACK_S <= f.time[1] and f.time[0] - TIME_SLACK_S <= g.time[1]]
        mine = _distinct([x for x in anchor_pool if x.key == f.key and x.time is not None
                          and x.time[0] - TIME_SLACK_S <= f.time[1] and f.time[0] - TIME_SLACK_S <= x.time[1]])
        theirs = _distinct(near)
        if len(mine) == 1 and len(theirs) == 1 and not agree(f, theirs[0]):
            out.append(Conflict(f, theirs[0]))
    return out


def _priced_tags(anchor_pool: list[Figure], other_pool: list[Figure]) -> list[Figure]:
    """A bare amount on a poster is read as the price the caption names, when the caption names exactly one
    price, the poster states no price of its own, and the poster has one such tag. Otherwise tags are noise."""
    prices = {f.key for f in anchor_pool if f.kind == "price" and f.key.count(":") == 1}
    tags = [f for f in other_pool if f.key == TAG]
    rest = [f for f in other_pool if f.key != TAG]
    if len(prices) != 1 or len(_distinct(tags)) != 1 or any(f.kind == "price" for f in rest):
        return rest
    key = next(iter(prices))
    return rest + [Figure(t.source, key, t.value, t.bound, t.start, t.end, t.quote, t.time, inferred=True)
                   for t in tags]


def _distinct(pool: list[Figure]) -> list[Figure]:
    """One figure per value (the same "50% off" read twice, by OCR and the vision model, is one figure)."""
    seen: dict[tuple[float, str | None, float | None], Figure] = {}
    for f in pool:
        seen.setdefault((round(f.value, 6), f.bound, f.low), f)
    return list(seen.values())
