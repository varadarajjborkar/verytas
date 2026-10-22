"""Voice and topic drift: does a piece still sound like the brand, and is it still about the brand?

Both checks measure against the brand's own approved and published work (BrandProfile), not a
fixed idea of good writing. A brand whose posts are full of slang may use slang; a brand that
never mentions politics should hear about a post that does. When a workspace has too little
approved work to learn from, the floors below stand in for a plain, respectful default voice.

Off-topic needs positive evidence: a paragraph has to land in a named domain the brand never
covers (politics, betting, trading tips...). Low word overlap alone is never enough, because a
new course, a new product or a standard footer always brings new words, and flagging every new
idea would teach reviewers to ignore the check.

Matching runs on word tokens with their offsets in the text as written, in any script, so a
quote is always exactly what the writer typed: no lowercasing shifts, no prefix matches ("u"
inside "us"), and NFD input matches like NFC.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass

from verytas.checks.base import CheckContext, RawFinding, RuleView

MIN_DOCS = 3  # approved or published pieces needed before the brand's own baseline replaces the defaults
_SENTENCE = re.compile(r"[^.!?।॥。！？]+[.!?।॥。！？]*")


@dataclass(frozen=True)
class Token:
    stem: str
    start: int
    end: int


def stem(word: str) -> str:
    """A light, consistent stem so "elections" and "election" meet. Both sides use it, so it needn't be perfect."""
    w = unicodedata.normalize("NFC", word.lower().replace("’", "'").strip("'"))
    if not w.isascii():
        return w  # the suffix rules are English; other words are compared as written
    if w.endswith("'s"):
        w = w[:-2]
    for suffix, keep in (("ies", "y"), ("sses", "ss"), ("ches", "ch"), ("shes", "sh"), ("xes", "x")):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            return w[: -len(suffix)] + keep
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    if w.endswith("ing") and len(w) > 6:
        w = w[:-3]
    elif w.endswith("ed") and len(w) > 5:
        w = w[:-2]
    return w


def tokens(text: str) -> list[Token]:
    """Words of any script: letters plus the combining marks Indic scripts write vowels with, which a regex \\w
    splits on. Danda, digits and punctuation end a word."""
    out: list[Token] = []
    start = None
    for i, ch in enumerate(text):
        cat = unicodedata.category(ch)
        inside = cat[0] in "LM" or (ch in "'’" and start is not None and i + 1 < len(text)
                                     and unicodedata.category(text[i + 1])[0] == "L")
        if inside and start is None:
            if cat[0] == "M":
                continue  # a stray mark can't start a word
            start = i
        elif not inside and start is not None:
            out.append(Token(stem(text[start:i]), start, i))
            start = None
    if start is not None:
        out.append(Token(stem(text[start:]), start, len(text)))
    return out


def _lexicon(*phrases: str) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(t.stem for t in tokens(p.replace("-", " "))) for p in phrases)


@dataclass(frozen=True)
class Hit:
    key: str  # the lexicon phrase, as stems
    start: int
    end: int


def _hits(toks: list[Token], lexicon: tuple[tuple[str, ...], ...]) -> list[Hit]:
    stems = [t.stem for t in toks]
    found = []
    for phrase in lexicon:
        n = len(phrase)
        for i in range(len(stems) - n + 1):
            if tuple(stems[i:i + n]) == phrase:
                found.append(Hit(" ".join(phrase), toks[i].start, toks[i + n - 1].end))
    return sorted(found, key=lambda h: h.start)


# --- topics -------------------------------------------------------------------------------------------

# Domains a brand post can wander into that most brands never want to be seen in. Each is named in the
# finding, so a reviewer sees "moves to politics" rather than a similarity number. Words a brand uses
# innocently are left out on purpose, in every language: "government exam prep", "invest in yourself", "a
# portfolio you can show", "against the odds", "vote for your favourite", "betting big on", "dating back", "an
# artist's manifesto", German "Wahl" (choice), Spanish "elección" (choice; "elecciones" needs a second hit),
# Spanish "apuesta" and Portuguese "aposta" (a commitment), Hindi "neta" (Portuguese for granddaughter).
DOMAINS: dict[str, tuple[tuple[str, ...], ...]] = {
    "politics": _lexicon(
        "election", "minister", "prime minister", "parliament", "politician", "political", "politics",
        "party leader", "opposition", "bjp", "congress party", "campaign rally", "election manifesto", "mla",
        "democrat",
        "republican", "left wing", "right wing", "regime",
        "chunav", "mantri", "matdan", "चुनाव", "मंत्री", "मतदान",  # Hindi
        "elecciones", "ministro", "diputado", "partido político",  # Spanish
        "élection", "élections", "ministre", "député", "parti politique",  # French
        "bundestag", "bundeskanzler", "partei", "abgeordneter",  # German
        "eleição", "eleições", "deputado"),  # Portuguese ("ministro" above)
    "religion": _lexicon(
        "religion", "religious", "temple", "mosque", "church", "hindu", "muslim", "christian", "sikh", "atheist",
        "mandir", "masjid", "मंदिर", "मस्जिद", "religión", "iglesia", "mezquita", "église", "mosquée", "kirche",
        "moschee", "religião", "igreja", "mesquita"),
    "trading tips": _lexicon(
        "bitcoin", "crypto", "cryptocurrency", "ethereum", "nft", "stock tip", "stock market", "trading", "forex",
        "sensex", "nifty", "intraday", "multibagger", "to the moon", "share bazaar", "शेयर बाजार",
        "criptomoneda", "criptomonedas", "cryptomonnaie", "cryptomonnaies", "kryptowährung", "criptomoeda"),
    "betting": _lexicon(
        "sports betting", "online betting", "casino", "odds", "jackpot", "gamble", "gambling", "poker",
        "fantasy team", "satta", "lottery", "jua", "सट्टा", "जुआ", "apuestas deportivas", "casa de apuestas",
        "paris sportifs", "glücksspiel", "sportwetten", "apostas esportivas", "casa de apostas"),
    "celebrity gossip": _lexicon("gossip", "breakup", "rumour", "rumor", "celebrity", "bollywood", "scandal",
                                 "paparazzi", "chisme", "potin", "fofoca"),
    "personal life": _lexicon("my girlfriend", "my boyfriend", "my wife", "my husband", "my ex", "hangover",
                              "party last night", "drunk", "my landlord", "my vacation", "my holiday"),
}
# One of these alone is enough; everything else needs two different hits from the same domain.
_STRONG = frozenset(" ".join(p) for p in _lexicon(
    "election", "bitcoin", "crypto", "cryptocurrency", "casino", "sports betting", "online betting", "bjp",
    "parliament", "gossip", "satta", "nft", "hangover", "chunav", "चुनाव", "सट्टा", "élection", "élections",
    "eleição", "eleições", "bundestag", "criptomoneda", "criptomonedas", "cryptomonnaie", "cryptomonnaies",
    "kryptowährung", "criptomoeda", "apuestas deportivas", "casa de apuestas", "apostas esportivas",
    "casa de apostas", "glücksspiel", "sportwetten"))


def domain_hits(text: str) -> dict[str, list[Hit]]:
    toks = tokens(text)
    found = {}
    for name, lexicon in DOMAINS.items():
        hits = _hits(toks, lexicon)
        keys = {h.key for h in hits}
        if len(keys) >= 2 or keys & _STRONG:
            found[name] = hits
    return found


def domains_in(text: str) -> dict[str, list[str]]:
    """Each domain the text lands in, with the words that put it there, as written."""
    return {d: sorted({text[h.start:h.end] for h in hits}) for d, hits in domain_hits(text).items()}


# --- tone ---------------------------------------------------------------------------------------------

TONE: dict[str, tuple[tuple[str, ...], ...]] = {
    # Only words that are insults wherever they appear. "We hate to see", "no dumb questions", "garbage
    # collection", "damn good coffee", "take out the trash", "April fools", "ridiculous value", Spanish
    # "basura" and Portuguese "lixo" (litter), "burro" (donkey) and "Depp" (a surname) are all fine in copy.
    "hostile": _lexicon(
        "idiot", "stupid", "pathetic", "loser", "moron", "shut up", "sucks", "crap", "shame on", "brainless",
        "disgusting",
        "bewakoof", "bevkoof", "gadha", "nalayak", "kamina", "बेवकूफ", "गधा", "नालायक", "कमीना",  # Hindi
        "idiota", "estúpido", "imbécil", "patético", "cállate",  # Spanish
        "imbécile", "débile", "connard", "crétin", "ta gueule",  # French
        "dumm", "blöd", "vollidiot", "halt die klappe",  # German
        "otário", "cala a boca"),  # Portuguese ("idiota" above)
    # English only: Spanish "ya", "sus" and "u" are ordinary words.
    "slangy": _lexicon("lol", "lmao", "rofl", "bro", "bruh", "gonna", "wanna", "gotta", "af", "ngl", "omg", "tbh",
                       "dude", "yolo", "deadass", "kinda", "sorta", "ur", "pls", "plz", "thx", "y'all", "fam",
                       "vibes", "no cap", "lowkey", "slay", "bestie", "wtf"),
    # Phrases that are sarcastic as a rule; "thanks a lot" and "as if" are usually sincere, so they are out.
    "sarcastic": _lexicon("yeah right", "oh great another", "oh sure because", "totally not", "what a surprise",
                          "big surprise", "slow clap", "because that worked", "how original", "wow just wow"),
    "stiff": _lexicon("hereby", "herein", "pursuant", "aforementioned", "notwithstanding", "henceforth",
                      "heretofore", "please be advised", "kindly be informed", "synergy", "leverage", "paradigm",
                      "utilize", "stakeholder", "deliverable", "going forward", "circle back", "best in class",
                      "operationalize", "ideate"),
    "hyped": _lexicon("insane", "crazy", "mind blowing", "epic", "unbelievable", "game changer", "revolutionary",
                      "killer", "ultimate", "unreal", "jaw dropping", "craziest", "hurry", "last chance",
                      "don't miss", "limited time", "act now"),
}
# How many hits make a dimension, when the brand's own work shows none of it.
_MIN_HITS = {"hostile": 1, "sarcastic": 1, "slangy": 2, "stiff": 2, "hyped": 3}
_SAY = {"hostile": "hostile", "slangy": "slangy and casual", "sarcastic": "sarcastic", "stiff": "stiff and corporate",
        "hyped": "hyped"}
_BANGS = re.compile(r"[!！]{2,}")


def tone_spans(text: str) -> dict[str, list[Hit]]:
    """Each tone dimension's triggers with their offsets. "Hyped" also counts shouted punctuation: each run of
    "!!" (a run of three or more counts twice), and, when at least half the sentences end in "!", two more.
    Exclamations alone never reach the bar: an upbeat launch post is not hype until it also pushes ("hurry",
    "!!!") or oversells ("insane", "ultimate")."""
    toks = tokens(text)
    found = {name: _hits(toks, lexicon) for name, lexicon in TONE.items()}
    bangs = [Hit("!!!" if m.end() - m.start() >= 3 else "!!", m.start(), m.end()) for m in _BANGS.finditer(text)]
    sentences = [m for m in _SENTENCE.finditer(text) if m.group().strip()]
    shouted = [m for m in sentences if m.group().rstrip().endswith(("!", "！"))]
    if sentences and len(shouted) / len(sentences) >= 0.5:
        for m in shouted[:2]:
            end = m.start() + len(m.group().rstrip())
            bangs.append(Hit("!", end - 1, end))
    found["hyped"] = sorted(found["hyped"] + bangs, key=lambda h: h.start)
    return found


def tone_hits(text: str) -> dict[str, list[str]]:
    """The same, as the words that triggered each dimension, as written."""
    return {k: [text[h.start:h.end] for h in v] for k, v in tone_spans(text).items()}


_PUNCT = {"!!!": 2, "!!": 1, "!": 1}


def _count(hits: list[Hit]) -> int:
    # Repeating one insult is one hit for the threshold; punctuation counts per run.
    return len({h.key for h in hits if h.key not in _PUNCT}) + sum(_PUNCT.get(h.key, 0) for h in hits)


# --- the brand's own baseline ------------------------------------------------------------------------

@dataclass(frozen=True)
class BrandProfile:
    """What the brand's approved and published work sounds like and covers. Built from pieces at or below the
    reviewed piece's tier (and the brand's facts and examples for topics). It carries no text of its own, only
    which tone dimensions and domains are the brand's, so nothing from one piece can surface in another's
    review."""

    docs: int = 0
    domains: frozenset[str] = frozenset()  # domains the brand itself covers, so they are not off-topic for it
    tones: frozenset[str] = frozenset()  # tone dimensions the brand's own work uses

    @property
    def learned(self) -> bool:
        return self.docs >= MIN_DOCS


def build_profile(voice_texts: list[str], topic_texts: list[str] | None = None) -> BrandProfile:
    voice = [t for t in voice_texts if t and t.strip()]
    topics = voice + [t for t in (topic_texts or []) if t and t.strip()]
    domain_df: dict[str, int] = {}
    for t in topics:
        for d in domain_hits(t):
            domain_df[d] = domain_df.get(d, 0) + 1
    tone_df: dict[str, int] = {}
    for t in voice:
        for name, hits in tone_spans(t).items():
            if _count(hits) >= _MIN_HITS[name]:
                tone_df[name] = tone_df.get(name, 0) + 1
    # A domain or tone is the brand's own once it shows up more than once: one stray post doesn't set the voice.
    return BrandProfile(docs=len(voice), domains=frozenset(d for d, n in domain_df.items() if n >= 2),
                        tones=frozenset(t for t, n in tone_df.items() if n >= 2))


# --- matchers -----------------------------------------------------------------------------------------

def _paragraphs(ctx: CheckContext):
    return [u for u in ctx.units if u.kind == "paragraph" and u.text.strip()]


def _span(unit, hits: list[Hit]) -> tuple[int, int]:
    """Body offsets from the first trigger to the last while that stays a short quote, else the first alone.
    A sentence's closing "!" counts toward hype but makes a poor quote; words and "!!" runs are quoted instead."""
    hits = [h for h in hits if h.key != "!"] or hits
    first, last = hits[0], max(hits, key=lambda h: h.end)
    end = last.end if last.end - first.start <= 140 else first.end
    return unit.start + first.start, unit.start + end


def _words(text: str, hits: list[Hit], fallback: str) -> str:
    said = list(dict.fromkeys(text[h.start:h.end] for h in hits if h.key not in _PUNCT))
    return ", ".join(f"'{w}'" for w in said[:5]) or fallback


def _brand_says(profile: BrandProfile | None) -> str:
    if profile and profile.learned:
        return f"None of the brand's {profile.docs} approved or published pieces read this way."
    return "The brand voice is plain and respectful by default, and too little is approved yet to learn otherwise."


def tone_shift(ctx: CheckContext, rule: RuleView, profile: BrandProfile | None) -> Iterator[RawFinding]:
    allowed = set(rule.pattern.get("allow") or ()) | (profile.tones if profile and profile.learned else set())
    paras = _paragraphs(ctx)
    if not paras:
        return

    def tripped(text: str) -> dict[str, list[Hit]]:
        return {k: v for k, v in tone_spans(text).items() if k not in allowed and _count(v) >= _MIN_HITS[k]}

    per_para = [tripped(p.text) for p in paras]
    seen: set[str] = set()
    # A paragraph that turns when the opening didn't: the tone changed partway, which a skim most often misses.
    for p, found in zip(paras[1:], per_para[1:], strict=True):
        for dim, hits in found.items():
            if dim in per_para[0] or dim in seen:
                continue
            seen.add(dim)
            s, e = _span(p, hits)
            yield RawFinding(unit_id=p.id, category=rule.category, confidence=0.8 if dim == "hostile" else 0.7,
                             title=f"Tone turns {_SAY[dim]} partway through", checker="deterministic",
                             rule_code=rule.code, quote=ctx.body[s:e], span_start=s, span_end=e,
                             explanation=f"The opening reads in the brand's voice, then this paragraph turns "
                                         f"{_SAY[dim]} ({_words(p.text, hits, 'the run of exclamation marks')}). "
                                         f"{_brand_says(profile)}")
    # Otherwise the piece as a whole: a dimension may build up across paragraphs that each stay under the bar.
    whole = tone_spans(ctx.body)
    for dim, hits in whole.items():
        if dim in seen or dim in allowed or _count(hits) < _MIN_HITS[dim]:
            continue
        p = next((p for p in paras if p.start <= hits[0].start < p.end), paras[0])
        local = [h for h in hits if p.start <= h.start and h.end <= p.end]
        shifted = [Hit(h.key, h.start - p.start, h.end - p.start) for h in local] or [
            Hit("!", hits[0].start - p.start, hits[0].end - p.start)]
        s, e = _span(p, shifted)
        yield RawFinding(unit_id=p.id, category=rule.category, confidence=0.8 if dim == "hostile" else 0.65,
                         title=f"Off the brand's voice: {_SAY[dim]}", checker="deterministic", rule_code=rule.code,
                         quote=ctx.body[s:e], span_start=s, span_end=e,
                         explanation=f"This reads {_SAY[dim]} "
                                     f"({_words(ctx.body, hits, 'exclamation after exclamation')}). "
                                     f"{_brand_says(profile)}")


def topic_drift(ctx: CheckContext, rule: RuleView, profile: BrandProfile | None) -> Iterator[RawFinding]:
    covered = set(rule.pattern.get("allow") or ()) | (set(profile.domains) if profile else set())
    paras = _paragraphs(ctx)
    about = [{d: h for d, h in domain_hits(p.text).items() if d not in covered} for p in paras]
    on_brand = [i for i, found in enumerate(about) if not found]
    reported: set[str] = set()
    for i, p in enumerate(paras):
        for domain, hits in about[i].items():
            if domain in reported:
                continue
            reported.add(domain)
            s, e = _span(p, hits)
            partway = bool(on_brand) and on_brand[0] < i
            title = f"Drifts off topic into {domain}" if partway else f"Off the brand's topics: {domain}"
            lead = "The piece starts on its subject, then this paragraph moves to " if partway else "This is about "
            yield RawFinding(unit_id=p.id, category=rule.category, confidence=0.85 if partway else 0.75,
                             title=title, checker="deterministic", rule_code=rule.code,
                             quote=ctx.body[s:e], span_start=s, span_end=e,
                             explanation=f"{lead}{domain} ({_words(p.text, hits, domain)}). Nothing the brand has "
                                         f"approved or published covers {domain}; off-topic posts dilute the message "
                                         f"and can pull the brand into debates it never chose.")
