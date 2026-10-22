"""Voice and topic drift: does a piece still sound like the brand, and is it still about the brand?

Both checks measure against the brand's own published work (BrandProfile), not
a fixed idea of good writing. A brand whose posts are full of slang may use
slang; a brand that never mentions politics should hear about a post that
does. When a workspace has published too little to learn from, the floors
below stand in for a plain, respectful default voice.

Off-topic needs positive evidence: a paragraph has to land in a named domain
the brand never covers (politics, betting, trading tips...). Low word overlap
alone is not enough, because a new course or a new product always brings new
words, and flagging every new idea would teach reviewers to ignore the check.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from verytas.checks.base import CheckContext, RawFinding, RuleView
from verytas.ingest.language import COMMON_WORDS, detect

MIN_DOCS = 3  # published pieces needed before the brand's own baseline replaces the defaults

# Letters of any script, plus the combining marks Indic scripts write vowels with (which \w alone splits on).
_LETTER = r"(?:[^\W\d_]|[\u0300-\u036F\u0900-\u0DFF])"
_WORD = re.compile(rf"{_LETTER}(?:{_LETTER}|')*")
_SENTENCE = re.compile(r"[^.!?\u0964\u3002\uff01\uff1f]+[.!?\u0964\u3002\uff01\uff1f]*")

_STOP_WORDS = """
a about above after again against all am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers
herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on
once only or other our ours ourselves out over own same she should so some such than that the their theirs them
themselves then there these they this those through to too under until up very was we were what when where which
while who whom why will with would you your yours yourself yourselves also get got one two new like make made
let lets us every day today week time way thing things really much many even still back go going come know see
want need take use via per s t ll ve re d m don won can't isn't it's i'm you're we're they're that's
"""
# Other languages' commonest words are stop words too, so they never pass for brand vocabulary.
STOP = frozenset(_STOP_WORDS.split()) | COMMON_WORDS


def stem(word: str) -> str:
    """A light, consistent stem so "elections" and "election" meet. Both sides use it, so it needn't be perfect."""
    w = unicodedata.normalize("NFC", word.lower().strip("'"))
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


def content_words(text: str) -> list[str]:
    return [stem(w) for w in _WORD.findall(text) if w.lower() not in STOP and len(w) > 2]


def _lexicon(*phrases: str) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(stem(w) for w in p.replace("-", " ").split()) for p in phrases)


# --- topics -------------------------------------------------------------------------------------------

# Domains a brand post can wander into that most brands never want to be seen in. Each is named in the
# finding, so a reviewer sees "moves to politics" rather than a similarity number.
DOMAINS: dict[str, tuple[tuple[str, ...], ...]] = {
    # Words an education or consumer brand uses innocently ("government exam prep", "invest in yourself", "a
    # portfolio you can show", "against the odds", "a launch party") are left out on purpose, in every language
    # (German "Wahl" is also "choice", Hindi "neta" is Portuguese for granddaughter).
    "politics": _lexicon(
        "election", "vote", "voting", "voter", "minister", "prime minister", "parliament", "politician", "political",
        "politics", "party leader", "opposition", "bjp", "congress party", "campaign rally", "manifesto", "mla",
        "democrat", "republican", "left wing", "right wing", "protest", "regime",
        "chunav", "mantri", "matdan", "चुनाव", "मंत्री", "मतदान",  # Hindi
        "elecciones", "elección", "ministro", "diputado", "partido político", "votar",  # Spanish
        "élection", "élections", "ministre", "député", "parti politique",  # French
        "bundestag", "bundeskanzler", "partei", "abgeordneter",  # German
        "eleição", "eleições", "deputado"),  # Portuguese ("ministro", "votar" above)
    "religion": _lexicon(
        "religion", "religious", "temple", "mosque", "church", "hindu", "muslim", "christian", "sikh", "atheist",
        "mandir", "masjid", "मंदिर", "मस्जिद", "religión", "iglesia", "mezquita", "église", "mosquée", "kirche",
        "moschee", "religião", "igreja", "mesquita"),
    "trading tips": _lexicon(
        "bitcoin", "crypto", "cryptocurrency", "ethereum", "nft", "stock tip", "stock market", "trading", "forex",
        "sensex", "nifty", "intraday", "multibagger", "to the moon", "share bazaar", "शेयर बाजार",
        "criptomoneda", "criptomonedas", "cryptomonnaie", "cryptomonnaies", "kryptowährung", "criptomoeda"),
    "betting": _lexicon(
        "betting", "casino", "odds", "jackpot", "gamble", "gambling", "poker", "fantasy team", "satta", "lottery",
        "jua", "सट्टा", "जुआ", "apuestas", "apuesta", "paris sportifs", "glücksspiel", "sportwetten", "apostas"),
    "celebrity gossip": _lexicon("gossip", "affair", "breakup", "dating", "rumour", "rumor", "celebrity",
                                 "bollywood", "scandal", "paparazzi", "chisme", "potin", "fofoca"),
    "personal life": _lexicon("my girlfriend", "my boyfriend", "my wife", "my husband", "my ex", "hangover",
                              "party last night", "drunk", "my landlord", "my vacation", "my holiday"),
}
# One of these alone is enough; everything else needs two hits from the same domain.
_STRONG = frozenset(stem(w) for w in (
    "election", "bitcoin", "crypto", "cryptocurrency", "casino", "betting", "bjp", "parliament", "gossip", "satta",
    "nft", "hangover", "chunav", "चुनाव", "सट्टा", "elecciones", "elección", "élection", "élections", "eleição",
    "eleições", "bundestag", "criptomoneda", "criptomonedas", "cryptomonnaie", "cryptomonnaies", "kryptowährung",
    "criptomoeda", "apuestas", "apostas", "glücksspiel", "sportwetten"))


def _phrase_hits(words: list[str], lexicon: Iterable[tuple[str, ...]]) -> list[str]:
    hits = []
    for phrase in lexicon:
        n = len(phrase)
        for i in range(len(words) - n + 1):
            if tuple(words[i:i + n]) == phrase:
                hits.append(" ".join(phrase))
    return hits


def _all_words(text: str) -> list[str]:
    return [stem(w) for w in _WORD.findall(text)]


def domains_in(text: str) -> dict[str, list[str]]:
    words = _all_words(text)
    found = {}
    for name, lexicon in DOMAINS.items():
        hits = _phrase_hits(words, lexicon)
        distinct = set(hits)
        if len(distinct) >= 2 or distinct & _STRONG:
            found[name] = sorted(distinct)
    return found


# --- tone ---------------------------------------------------------------------------------------------

TONE: dict[str, tuple[tuple[str, ...], ...]] = {
    # Kept to words that are insults in any context: "we hate to see", "no useless theory" and "wake up early"
    # are fine in brand copy.
    "hostile": _lexicon(
        "idiot", "stupid", "dumb", "pathetic", "loser", "trash", "garbage", "clown", "moron", "shut up", "sucks",
        "crap", "damn", "ridiculous", "shame on", "sheep", "fools", "brainless", "disgusting",
        "bewakoof", "bevkoof", "gadha", "nalayak", "kamina", "बेवकूफ", "गधा", "नालायक", "कमीना",  # Hindi
        "idiota", "estúpido", "imbécil", "basura", "patético", "cállate",  # Spanish
        "imbécile", "débile", "connard", "crétin", "ta gueule",  # French
        "dumm", "blöd", "vollidiot", "halt die klappe", "depp",  # German
        "burro", "otário", "lixo", "cala a boca"),  # Portuguese ("idiota" above)
    "slangy": _lexicon("lol", "lmao", "rofl", "bro", "bruh", "gonna", "wanna", "gotta", "ya", "af", "ngl", "omg",
                       "tbh", "dude", "yolo", "sus", "deadass", "kinda", "sorta", "u", "ur", "pls", "plz", "thx",
                       "y'all", "fam", "vibes", "no cap", "lowkey", "slay", "bestie", "wtf"),
    "sarcastic": _lexicon("yeah right", "oh great", "oh sure", "as if", "totally not", "what a surprise",
                          "big surprise", "thanks a lot", "slow clap", "because that worked", "how original"),
    "stiff": _lexicon("hereby", "herein", "pursuant", "aforementioned", "notwithstanding", "henceforth",
                      "heretofore", "please be advised", "kindly be informed", "synergy", "leverage", "paradigm",
                      "utilize", "stakeholder", "deliverable", "going forward", "circle back", "best in class",
                      "operationalize", "ideate"),
    "hyped": _lexicon("insane", "crazy", "mind blowing", "epic", "unbelievable", "game changer", "revolutionary",
                      "killer", "ultimate", "unreal", "jaw dropping", "craziest"),
}
# How many hits make a dimension, when the brand's own posts show none of it.
_MIN_HITS = {"hostile": 1, "sarcastic": 1, "slangy": 2, "stiff": 2, "hyped": 3}
_SAY = {"hostile": "hostile", "slangy": "slangy and casual", "sarcastic": "sarcastic", "stiff": "stiff and corporate",
        "hyped": "hyped"}


def tone_hits(text: str) -> dict[str, list[str]]:
    """Each tone dimension's trigger words in the text. "Hyped" also counts shouted punctuation."""
    words = _all_words(text)
    lowered = text.lower()
    hits: dict[str, list[str]] = {}
    for name, lexicon in TONE.items():
        found = _phrase_hits(words, lexicon)
        if name == "sarcastic":
            found += [p for p in ("sure, because", "wow, just wow") if p in lowered]
        hits[name] = sorted(set(found))
    bangs = re.findall(r"[!\uff01]{2,}", text)
    sentences = [s for s in _SENTENCE.findall(text) if s.strip()]
    exclaimed = sum(1 for s in sentences if s.rstrip().endswith(("!", "\uff01")))
    hits["hyped"] += ["!!"] * len(bangs) + (["!"] * exclaimed if sentences and exclaimed / len(sentences) > 0.5 else [])
    return hits


# --- the brand's own baseline ------------------------------------------------------------------------

@dataclass(frozen=True)
class BrandProfile:
    """What the brand's published work sounds like and talks about. Built per review from approved and
    published pieces (and the brand's facts and examples for topics), at or below the piece's tier."""

    docs: int = 0
    vocab: frozenset[str] = frozenset()
    domains: frozenset[str] = frozenset()  # domains the brand itself covers, so they are not off-topic for it
    tones: frozenset[str] = frozenset()  # tone dimensions the brand's own posts use
    sample: tuple[str, ...] = field(default=())  # a few frequent brand words, for the explanation
    language: str = "und"  # the language most of the brand's published work is in

    @property
    def learned(self) -> bool:
        return self.docs >= MIN_DOCS


def build_profile(voice_texts: list[str], topic_texts: list[str] | None = None) -> BrandProfile:
    voice = [t for t in voice_texts if t and t.strip()]
    topics = voice + [t for t in (topic_texts or []) if t and t.strip()]
    df: dict[str, int] = {}
    for t in topics:
        for w in set(content_words(t)):
            df[w] = df.get(w, 0) + 1
    domain_df: dict[str, int] = {}
    for t in topics:
        for d in domains_in(t):
            domain_df[d] = domain_df.get(d, 0) + 1
    tone_df: dict[str, int] = {}
    for t in voice:
        for name, found in tone_hits(t).items():
            if len(found) >= _MIN_HITS[name]:
                tone_df[name] = tone_df.get(name, 0) + 1
    # A domain or tone counts as the brand's own once it shows up more than once: one stray post doesn't set the voice.
    sample = tuple(w for w, _ in sorted(df.items(), key=lambda kv: (-kv[1], kv[0]))[:6])
    languages = Counter(detect(t).code for t in voice)
    return BrandProfile(docs=len(voice), vocab=frozenset(df), sample=sample,
                        language=languages.most_common(1)[0][0] if languages else "und",
                        domains=frozenset(d for d, n in domain_df.items() if n >= 2),
                        tones=frozenset(t for t, n in tone_df.items() if n >= 2))


# --- matchers -----------------------------------------------------------------------------------------

def _paragraphs(ctx: CheckContext):
    return [u for u in ctx.units if u.kind == "paragraph" and u.text.strip()]


def _span(text: str, start: int, needles: list[str]) -> tuple[int, int]:
    """From the first trigger word to the last, whole words, while that stays a short quote; the paragraph's
    first sentence when the trigger is punctuation."""
    lowered = text.lower()
    found = []
    for n in needles:
        if n.strip("!"):
            # Needles are stems ("aforemention"), so run on to the end of the word as written.
            m = re.search(r"\b" + r"\W+".join(map(re.escape, n.split())) + r"[\w']*", lowered)
            if m:
                found.append((m.start(), m.end()))
    if found:
        found.sort()
        first, last = found[0], max(found, key=lambda f: f[1])
        end = last[1] if last[1] - first[0] <= 140 else first[1]
        return start + first[0], start + end
    first_sentence = _SENTENCE.match(text)
    end = first_sentence.end() if first_sentence else len(text)
    return start, start + len(text[:end].rstrip())


def _brand_says(profile: BrandProfile | None) -> str:
    if profile and profile.learned:
        return f"None of the brand's {profile.docs} published pieces read this way."
    return "The brand voice is plain and respectful by default, and too little is published yet to learn otherwise."


def tone_shift(ctx: CheckContext, rule: RuleView, profile: BrandProfile | None) -> Iterator[RawFinding]:
    allowed = set(rule.pattern.get("allow") or ()) | (profile.tones if profile and profile.learned else set())
    paras = _paragraphs(ctx)
    if not paras:
        return

    def tripped(text: str) -> dict[str, list[str]]:
        return {k: v for k, v in tone_hits(text).items() if k not in allowed and len(v) >= _MIN_HITS[k]}

    opening = tripped(paras[0].text)
    whole = tripped(ctx.body)
    seen: set[str] = set()
    # A paragraph that turns when the opening didn't: the tone changed partway, which is the drift a reviewer
    # most often misses on a skim.
    for p in paras[1:]:
        for dim, found in tripped(p.text).items():
            if dim in opening or dim in seen:
                continue
            seen.add(dim)
            s, e = _span(p.text, p.start, found)
            words = ", ".join(f"'{w}'" for w in found if w.strip("!"))[:120] or "the run of exclamation marks"
            yield RawFinding(unit_id=p.id, category=rule.category, confidence=0.8 if dim == "hostile" else 0.7,
                             title=f"Tone turns {_SAY[dim]} partway through", checker="deterministic",
                             rule_code=rule.code, quote=ctx.body[s:e], span_start=s, span_end=e,
                             explanation=f"The opening reads in the brand's voice, then this paragraph turns "
                                         f"{_SAY[dim]} ({words}). {_brand_says(profile)}")
    for dim, found in whole.items():
        if dim in seen:
            continue
        p = next((p for p in paras if tone_hits(p.text)[dim]), paras[0])
        s, e = _span(p.text, p.start, found)
        words = ", ".join(f"'{w}'" for w in found if w.strip("!"))[:120] or "exclamation after exclamation"
        yield RawFinding(unit_id=p.id, category=rule.category, confidence=0.8 if dim == "hostile" else 0.65,
                         title=f"Off the brand's voice: {_SAY[dim]}", checker="deterministic", rule_code=rule.code,
                         quote=ctx.body[s:e], span_start=s, span_end=e,
                         explanation=f"This reads {_SAY[dim]} ({words}). {_brand_says(profile)}")


def topic_drift(ctx: CheckContext, rule: RuleView, profile: BrandProfile | None) -> Iterator[RawFinding]:
    covered = set(rule.pattern.get("allow") or ()) | (set(profile.domains) if profile else set())
    paras = _paragraphs(ctx)
    if not paras:
        return
    about = {i: {d: w for d, w in domains_in(p.text).items() if d not in covered} for i, p in enumerate(paras)}
    on_brand = [i for i, p in enumerate(paras) if not about[i]]
    reported: set[str] = set()
    for i, p in enumerate(paras):
        for domain, words in about[i].items():
            if domain in reported:
                continue
            reported.add(domain)
            s, e = _span(p.text, p.start, words)
            listed = ", ".join(f"'{w}'" for w in words[:4])
            partway = bool(on_brand) and on_brand[0] < i
            title = f"Drifts off topic into {domain}" if partway else f"Off the brand's topics: {domain}"
            lead = ("The piece starts on its subject, then this paragraph moves to " if partway
                    else "This is about ")
            known = (f" The brand's published work is about {', '.join(profile.sample[:4])}, and never {domain}."
                     if profile and profile.learned and profile.sample else
                     f" Nothing the brand has published covers {domain}.")
            yield RawFinding(unit_id=p.id, category=rule.category, confidence=0.85 if partway else 0.75,
                             title=title, checker="deterministic", rule_code=rule.code,
                             quote=ctx.body[s:e], span_start=s, span_end=e,
                             explanation=f"{lead}{domain} ({listed}).{known} Off-topic posts dilute the message "
                                         f"and can pull the brand into debates it never chose.")
    # Without a named domain, wandering is only reported when it is stark: a long paragraph sharing almost no words
    # with the rest of the piece or with anything the brand has said, while the rest of the piece does.
    if not (profile and profile.learned) or len(paras) < 2:
        return
    for i, p in enumerate(paras[1:], start=1):
        if about[i]:
            continue
        # A paragraph in another language shares no words with the rest by nature; a bilingual post is not
        # a wandering one. Only compare like with like.
        if detect(p.text).code not in (profile.language, "und"):
            continue
        words = set(content_words(p.text))
        if len(words) < 12:
            continue
        rest = set().union(*(set(content_words(q.text)) for j, q in enumerate(paras) if j != i))
        overlap = len(words & (profile.vocab | rest)) / len(words)
        rest_overlap = (len(rest & profile.vocab) / len(rest)) if rest else 0.0
        if overlap <= 0.1 and rest_overlap >= 0.3:
            s, e = _span(p.text, p.start, [])
            yield RawFinding(unit_id=p.id, category=rule.category, confidence=0.55,
                             title="This paragraph wanders from the piece", checker="deterministic",
                             rule_code=rule.code, quote=ctx.body[s:e], span_start=s, span_end=e,
                             explanation="It shares almost no words with the rest of the piece or with anything "
                                         "the brand has published. Check it still serves the post's purpose.")
            return
