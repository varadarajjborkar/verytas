"""Script-blind phonetic keys and phrase spotting for transcripts of Hindi, Hinglish and English speech.

Whisper answers Hindi speech in Devanagari, Latin or Urdu script depending on the clip, spells English
brand names by ear ("Zestora" -> "जेस्तोरा", "Zestor", "zastura"), and writes numbers as digits or words.
A watch list entry such as "Zestora", "40 percent" or a confidential codename is written once, in Latin.
Exact string search therefore misses most spoken mentions. This module reduces both sides to the same
coarse sound key and looks for the watched phrase as an approximate substring of the transcript key.

Nothing here needs a model or a network call, and it has no dependencies beyond the standard library.

    spot("Zestora", transcript)           -> Spot(score=0.86, ...) or None
    spot_all(["Zestora", "40 percent"], transcript)

The key is deliberately lossy (a consonant skeleton): it keeps what ASR gets right in noisy Hindi (the
consonant frame) and drops what it gets wrong (vowel length, schwa, aspiration, voicing, z/j/s mix-ups).
The price is false hits on short phrases, so keys under `MIN_KEY` characters need an exact key match and the
allowed edit distance grows only with length.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

# ------------------------------------------------------------------------------------------ sound classes
# One capital letter per class. Classes merge sounds that Whisper or a romaniser swaps freely.
#   K velar (k kh g gh q c)   J palatal (ch j jh z)   T coronal stop (t d th dh, retroflex too)
#   P labial stop (p b f ph bh)   V v w   S s sh   N n m (and the Devanagari nasals)   R r   L l   H h   Y y
_DEVA_CONS = {
    "क": "K", "ख": "K", "ग": "K", "घ": "K", "ङ": "N",
    "च": "J", "छ": "J", "ज": "J", "झ": "J", "ञ": "N",
    "ट": "T", "ठ": "T", "ड": "T", "ढ": "T", "ण": "N",
    "त": "T", "थ": "T", "द": "T", "ध": "T", "न": "N",
    "प": "P", "फ": "P", "ब": "P", "भ": "P", "म": "N",
    "य": "Y", "र": "R", "ल": "L", "व": "V",
    "श": "S", "ष": "S", "स": "S", "ह": "H",
    "क़": "K", "ख़": "K", "ग़": "K", "ज़": "J", "ड़": "R", "ढ़": "R", "फ़": "P", "य़": "Y",
    "ळ": "L",
}
_NUKTA_FORMS = {"क": "क़", "ख": "ख़", "ग": "ग़", "ज": "ज़", "ड": "ड़", "ढ": "ढ़", "फ": "फ़"}
_DEVA_INDEPENDENT_VOWELS = "अआइईउऊऋएऐओऔऑ"
_DEVA_MATRAS = "ािीुूृेैोौॉॅ"
_VIRAMA = "्"
_DROPPED = "ंँःऽ़‌‍"  # anusvara, chandrabindu, visarga, avagraha, nukta (folded above), joiners

# Latin digraphs first, longest first. "sh" and "ch" are single sounds in every romanisation Whisper uses.
_LATIN_DIGRAPHS = [
    ("tch", "J"), ("ksh", "KS"), ("chh", "J"), ("shh", "S"), ("sch", "S"),
    ("ch", "J"), ("sh", "S"), ("kh", "K"), ("gh", "K"), ("th", "T"), ("dh", "T"), ("ph", "P"), ("bh", "P"),
    ("jh", "J"), ("ck", "K"), ("qu", "K"), ("ng", "N"), ("wh", "V"),
]
_LATIN_SINGLE = {
    "k": "K", "g": "K", "q": "K", "j": "J", "z": "J", "t": "T", "d": "T", "p": "P", "b": "P", "f": "P",
    "v": "V", "w": "V", "s": "S", "n": "N", "m": "N", "r": "R", "l": "L", "h": "H", "y": "Y", "x": "KS",
}
_LATIN_VOWELS = set("aeiou")

MIN_KEY = 5  # shorter keys must match exactly: a 3 or 4 consonant frame is too common to fuzz


def _deva_key(word: str) -> str:
    """Skeleton of one Devanagari word: consonant classes only. Vowels, anusvara and the schwa vanish."""
    out: list[str] = []
    chars = unicodedata.normalize("NFC", word)
    # Precomposed nukta letters decompose under NFC only partly; fold the pair forms back first.
    for base, joined in _NUKTA_FORMS.items():
        chars = chars.replace(base + "़", joined)
    for ch in chars:
        if ch in _DEVA_CONS:
            out.append(_DEVA_CONS[ch])
    return "".join(out)


def _latin_key(word: str) -> str:
    w = word.lower()
    out: list[str] = []
    i = 0
    while i < len(w):
        for dg, cls in _LATIN_DIGRAPHS:
            if w.startswith(dg, i):
                out.append(cls)
                i += len(dg)
                break
        else:
            ch = w[i]
            if ch == "c":  # soft before e, i, y ("percent", "cinema"), hard otherwise ("coffee")
                out.append("S" if w[i + 1:i + 2] in ("e", "i", "y") else "K")
            elif ch in _LATIN_SINGLE:
                out.append(_LATIN_SINGLE[ch])
            elif ch.isdigit():
                out.append(ch)
            i += 1
    return "".join(out)


def _collapse(key: str) -> str:
    """Geminates are one sound ("pakka" = "paka"), and digits are kept verbatim."""
    return re.sub(r"([A-Z])\1+", r"\1", key)


def word_key(word: str) -> str:
    """Skeleton key of a single token in any of the scripts Whisper may use. Digits pass through."""
    deva = "".join(c for c in word if "ऀ" <= c <= "ॿ")
    latin = "".join(c for c in word if c.isascii() and c.isalnum())
    digits = "".join(str(unicodedata.digit(c)) for c in word if c.isdigit() and not c.isascii())
    return _collapse(_deva_key(deva) + _latin_key(latin) + digits)


# --------------------------------------------------------------------------------------- numbers and units
_HINDI_0_99 = (  # noqa: SIM905
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस "
    "इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस "
    "सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास "
    "पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ "
    "सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी "
    "इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे "
    "पंचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()
assert len(_HINDI_0_99) == 100

_EN_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "  # noqa: SIM905
            "sixteen seventeen eighteen nineteen").split()
_EN_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()  # noqa: SIM905


def _en_words(n: int) -> str:
    if n < 20:
        return _EN_ONES[n]
    if n < 100:
        return _EN_TENS[n // 10] + (f" {_EN_ONES[n % 10]}" if n % 10 else "")
    if n < 1000:
        return f"{_EN_ONES[n // 100]} hundred" + (f" {_en_words(n % 100)}" if n % 100 else "")
    if n < 100000:
        return f"{_en_words(n // 1000)} thousand" + (f" {_en_words(n % 1000)}" if n % 1000 else "")
    return str(n)


def _hi_words(n: int) -> str:
    if n < 100:
        return _HINDI_0_99[n]
    if n < 1000:
        return f"{_HINDI_0_99[n // 100]} सौ" + (f" {_HINDI_0_99[n % 100]}" if n % 100 else "")
    if n < 100000:
        return f"{_HINDI_0_99[n // 1000]} हज़ार" + (f" {_hi_words(n % 1000)}" if n % 1000 else "")
    return str(n)


def number_variants(digits: str) -> list[str]:
    """How a number may reach the transcript: digits, English words, Hindi words (and digit by digit for
    long strings such as phone numbers, which are read out one digit at a time in either language)."""
    if len(digits) >= 7 or (len(digits) > 1 and digits[0] == "0"):
        spoken_en = " ".join(_EN_ONES[int(d)] for d in digits)
        spoken_hi = " ".join(_HINDI_0_99[int(d)] for d in digits)
        return [digits, spoken_en, spoken_hi]
    n = int(digits)
    return [digits, _en_words(n), _hi_words(n)]



# Units that carry a claim ("40 percent", "499 rupees", "30 minutes"). Each set is written in whatever script
# is easy; the keys make them meet. Every unit becomes one "strict" symbol, so the matcher never edits it.
_ALIASES = {
    "%": ["percent", "per cent", "persent", "प्रतिशत", "पर्सेंट", "प्रतिषत", "pratishat", "pratishath"],
    "$": ["rupees", "rupee", "rupaye", "rupay", "रुपये", "रुपए", "रुपया", "रूपये"],
    "&": ["minutes", "minute", "mins", "मिनट", "minat"],
    "@": ["days", "day", "दिन", "din"],
}
STRICT = set("0123456789%$&@")  # digits and unit symbols: never fuzzed, except in long digit strings
_ALIAS_OF_KEY: dict[str, str] = {}
for _code, _forms in _ALIASES.items():
    for _f in _forms:
        _k = word_key(_f)
        if _k:
            _ALIAS_OF_KEY.setdefault(_k, _code)
_SYMBOL_ALIASES = {"%": "%", "₹": "$"}
# The unit's own sounds, as an extra spelling of the watched phrase: ASR often glues it to the number
# ("चालिस्प्रतिषत"), where no token equals the unit. Short sounds are left out; they match anything.
_UNIT_SOUNDS = {c: sorted({word_key(f) for f in forms if len(word_key(f)) >= 4}) for c, forms in _ALIASES.items()}


# --------------------------------------------------------------------------------------- transcript to key
_DEVA_DIGITS = str.maketrans({chr(0x0966 + i): str(i) for i in range(10)})


def _prepare(text: str) -> str:
    """Make digits ASCII, join split numbers ("976-543-210", "1,499") and separate symbols from digits."""
    t = unicodedata.normalize("NFKC", text).translate(_DEVA_DIGITS)
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    # 7+ digits split by spaces or hyphens are one phone number
    t = re.sub(r"\+?\d+(?:[ \-]\d+)+", lambda m: re.sub(r"\D", "", m.group()) if len(re.sub(r"\D", "", m.group())) >= 7
               else m.group(), t)
    t = re.sub(r"(\d)(%|₹)", r"\1 \2", t)
    t = re.sub(r"(₹)(\d)", r"\1 \2", t)
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t, flags=re.I)  # "31st"
    return t


def _tokens(text: str) -> list[str]:
    """Words, keeping Devanagari vowel signs (category M, which `\\w` does not cover) and the % and rupee signs."""
    t = "".join(" " if unicodedata.category(c)[0] in "PSZC" and c not in "%₹" else c for c in _prepare(text))
    return t.split()


def _canonical_token_key(tok: str) -> str:
    if tok in _SYMBOL_ALIASES:
        return _SYMBOL_ALIASES[tok]
    k = word_key(tok)
    if k.isdigit():
        return k
    return _ALIAS_OF_KEY.get(k, k)


@lru_cache(maxsize=512)
def transcript_key(text: str) -> str:
    """The searchable form of a transcript: one key per token, space separated and padded. Word boundaries
    in Hindi ASR are unreliable ("चालिस्प्रतिषत" is two words), so the matcher treats a space as cheap to add
    or drop; it still lets short keys demand a whole-token match."""
    keys = [k for t in _tokens(text) if (k := _canonical_token_key(t))]
    return " " + " ".join(keys) + " " if keys else ""


# -------------------------------------------------------------------------------------------- the phrase
_NUM_WORD_KEYS: dict[str, int] = {}
for _n in range(100):
    for _w in (_en_words(_n), _HINDI_0_99[_n]):
        _NUM_WORD_KEYS.setdefault(word_key(_w), _n)


def _words_key(spoken: str) -> str:
    return " ".join(k for w in spoken.split() if (k := word_key(w)))


@lru_cache(maxsize=512)
def phrase_variants(phrase: str) -> tuple[str, ...]:
    """Every key a watched phrase may take: digits vs English vs Hindi number words, unit aliases.
    A number in the watch list ("40 percent" or "forty percent") yields all three number spellings."""
    parts: list[list[str]] = []
    for tok in _tokens(phrase):
        tok = _SYMBOL_ALIASES.get(tok, tok)
        k = word_key(tok)
        if tok.isdigit():
            parts.append(sorted({tok} | {_words_key(v) for v in number_variants(tok)[1:]}))
        elif tok in _ALIASES:  # the code itself, from a symbol
            parts.append([tok])
        elif k in _ALIAS_OF_KEY:
            parts.append([_ALIAS_OF_KEY[k]] + _UNIT_SOUNDS[_ALIAS_OF_KEY[k]])
        elif len(k) >= 3 and k in _NUM_WORD_KEYS:
            n = _NUM_WORD_KEYS[k]
            parts.append(sorted({str(n)} | {_words_key(v) for v in number_variants(str(n))[1:]}))
        else:
            parts.append([k] if k else [])
    out = [""]
    for opts in parts:
        if opts:
            out = [(a + " " + b).strip() for a in out for b in opts]
    return tuple(sorted({o for o in out if o}))


# ----------------------------------------------------------------------------------------- approximate find
BIG = 100.0  # the price of editing a digit, a unit symbol or a short token: effectively "not allowed"
SPACE = 0.25  # a word boundary the recogniser added or dropped is a small error, not a sound error


def _pattern(variant: str, phone: bool) -> tuple[str, list[float]]:
    """The variant as a search pattern, with the price of changing each character.

    Letters of a token shorter than MIN_KEY (a number word like "ST" for sixty) and all digits and unit
    symbols cannot be edited: a 2 or 3 letter frame matches half the language once it may bend. A short token
    at either end of the pattern is also pinned to a word edge, so "ST" cannot match inside another word.
    Spaces between tokens stay cheap, because ASR glues number and unit together ("चालिस्प्रतिषत")."""
    tokens = variant.split(" ")
    pattern, weights = "", []
    if len(tokens) and _core(tokens[0]) < MIN_KEY and not phone:
        pattern, weights = " ", [BIG]
    for n, tok in enumerate(tokens):
        if n:
            pattern, weights = pattern + " ", weights + [SPACE]
        short = _core(tok) < MIN_KEY
        for ch in tok:
            pattern += ch
            weights.append(1.0 if phone else BIG if short or ch in STRICT else 1.0)
    if tokens and _core(tokens[-1]) < MIN_KEY and not phone:
        pattern, weights = pattern + " ", weights + [BIG]
    return pattern, weights


def _core(token: str) -> int:
    return sum(1 for c in token if c not in STRICT)


def best_distance(pattern: str, weights: list[float], text: str, strict: float = BIG) -> float:
    """Least weighted edit distance between `pattern` and any substring of `text` (Sellers' algorithm).
    O(len(pattern) * len(text)); transcripts are a few thousand characters and watch lists are short."""
    if pattern in text:
        return 0.0
    m = len(pattern)
    prev = [0.0]
    for w in weights:
        prev.append(prev[-1] + w)
    best = prev[m]
    for t in text:
        ins = strict if t in STRICT else SPACE if t == " " else 1.0
        cur = [0.0]
        for i in range(1, m + 1):
            p = pattern[i - 1]
            w = weights[i - 1]
            sub = 0.0 if p == t else max(w, strict if t in STRICT else 1.0)
            cur.append(min(prev[i] + ins, cur[i - 1] + w, prev[i - 1] + sub))
        if cur[m] < best:
            best = cur[m]
        prev = cur
    return best


def edit_budget(core: int) -> int:
    """Sound edits allowed for a variant with `core` letters: none when short, about three tenths when long."""
    return 0 if core < MIN_KEY else max(1, (core * 3) // 10)


@dataclass(frozen=True)
class Spot:
    phrase: str
    score: float  # 1.0 is an exact key match
    distance: float
    variant: str


def spot(phrase: str, transcript: str, *, scale: float = 1.0) -> Spot | None:
    """Was `phrase` said? `scale` stretches (>1) or tightens (<1) the edit budget; 0 means exact keys only."""
    tkey = transcript_key(transcript)
    if not tkey:
        return None
    best: Spot | None = None
    for v in phrase_variants(phrase):
        phone = v.isdigit() and len(v) >= 9  # heard with one digit lost or wrong
        budget = (1.0 if phone else edit_budget(_core(v.replace(" ", "")))) * scale
        pattern, weights = _pattern(v, phone)
        d = best_distance(pattern, weights, tkey, 1.0 if phone else BIG) if budget else \
            (0.0 if pattern in tkey else BIG)
        if d <= budget + 1e-9:
            s = Spot(phrase, round(1 - d / max(1, len(v)), 3), d, v)
            if best is None or (s.distance, -len(s.variant)) < (best.distance, -len(best.variant)):
                best = s
    return best


def spot_all(phrases: list[str], transcript: str, *, scale: float = 1.0) -> dict[str, Spot]:
    return {p: s for p in phrases if (s := spot(p, transcript, scale=scale))}


# ------------------------------------------------------------------------------------------ where it was said
_WORD = re.compile(r"[^\s]+")


def _word_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the words in `text`, split the way `_tokens` splits them (punctuation is a gap)."""
    gaps = "".join(" " if unicodedata.category(c)[0] in "PSZC" and c not in "%₹" else c for c in text)
    return [m.span() for m in _WORD.finditer(gaps)]


def soundable(phrase: str) -> bool:
    """Whether `phrase` is distinctive enough to look for by sound alone. A short consonant frame ("Kite" is
    K-T, "Nova" N-V) or one that reads as a unit ("Titan" and "day" share a key) turns up in everyday speech."""
    variants = phrase_variants(phrase)
    return bool(variants) and all(len(v.replace(" ", "")) >= MIN_KEY and not set(v) & STRICT for v in variants)


def locate(phrase: str, transcript: str, *, scale: float = 1.0) -> tuple[int, int, Spot] | None:
    """The shortest run of words in `transcript` where `phrase` is heard, as character offsets, and the spot.
    A finding needs a span to point at (and, in a video, a time); the whole transcript is never quoted."""
    if not phrase.strip() or spot(phrase, transcript, scale=scale) is None:
        return None
    words = _word_spans(transcript)
    # A phrase may be heard as more words than it is written in ("नोवब्रू" is one, "Nova Brew" two), or fewer.
    widest = len(phrase.split()) + 3
    for size in range(1, widest + 1):
        for i in range(len(words) - size + 1):
            a, b = words[i][0], words[i + size - 1][1]
            if (s := spot(phrase, transcript[a:b], scale=scale)) is not None:
                return a, b, s
    return None


# ----------------------------------------------------------------------------------- spoken figures to digits
# Every price and percentage check reads digits ("40%", "₹499"). Hindi speech comes back as words, in either
# script and spelt by ear: "चालिस प्रतिषवत", "charso ninyanwe rupe", "400 Ninjaanwe Rupé". `write_figures` is the
# inverse text normalisation an ASR service would do, limited to the one thing the checks need: a number said
# right before "percent" or "rupees". A number with no unit after it is left alone, because without the unit
# "for", "this" and "on" read as Hindi or English numbers. The consonant key is too coarse here (25, 50 and 85
# share one), so number words get a finer spelling that keeps the vowels after the schwa is dropped.

_SPELL_MATRAS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "e", "ो": "o",
                 "ौ": "o", "ॉ": "o", "ॅ": "e"}
_SPELL_VOWELS = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "e",
                 "ओ": "o", "औ": "o", "ऑ": "o"}
# Romanisers spell one vowel many ways; fold the long and the diphthong forms first.
_SPELL_LATIN_VOWELS = [("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("ai", "e"), ("ay", "e"),
                       ("ei", "e"), ("au", "o"), ("aw", "o"), ("ou", "o")]


@lru_cache(maxsize=4096)
def spelling(word: str) -> str:
    """Consonant classes plus vowels, with the schwa between consonants and at the end dropped, as Hindi says
    it: "chalice", "chalis", "चालीस" and "जालिस" all become JLiS, while 25 (PJiS) and 50 (PJS) stay apart."""
    w = unicodedata.normalize("NFC", word)
    for base, joined in _NUKTA_FORMS.items():
        w = w.replace(base + "़", joined)
    out: list[str] = []
    deva = [c for c in w if "ऀ" <= c <= "ॿ"]
    if deva:
        for i, c in enumerate(deva):
            nxt = deva[i + 1] if i + 1 < len(deva) else ""
            if c in _DEVA_CONS:
                out.append(_DEVA_CONS[c])
                if nxt not in _SPELL_MATRAS and nxt != _VIRAMA:
                    out.append("a")
            elif c in _SPELL_MATRAS:
                out.append(_SPELL_MATRAS[c])
            elif c in _SPELL_VOWELS:
                out.append(_SPELL_VOWELS[c])
            elif c in "ंँ":
                out.append("N")
    else:
        s = "".join(c for c in unicodedata.normalize("NFKD", w.lower()) if c.isascii() and c.isalpha())
        for long, short in _SPELL_LATIN_VOWELS:
            s = s.replace(long, short)
        i = 0
        while i < len(s):
            for dg, cls in _LATIN_DIGRAPHS:
                if s.startswith(dg, i):
                    out.append(cls)
                    i += len(dg)
                    break
            else:
                ch = s[i]
                if ch == "c":
                    out.append("S" if s[i + 1:i + 2] in ("e", "i", "y") else "K")
                elif ch in _LATIN_VOWELS:
                    out.append(ch)
                elif ch in _LATIN_SINGLE:
                    out.append(_LATIN_SINGLE[ch])
                i += 1
    t = re.sub(r"([A-Za-z])\1+", r"\1", "".join(out))
    t = t[:1] + t[1:].replace("H", "")  # aspiration is spelt or dropped at will after the first sound
    t = re.sub(r"(?<=[A-Z])a(?=[A-Z])", "", t)
    t = re.sub(r"(?<=[A-Z])[ae]$", "", t)  # the final schwa, and the final e romanisers add or drop
    return re.sub(r"([A-Z])\1+", r"\1", t)


_SPELT_NUMBERS: dict[str, set[int]] = {}
_HINDI_SPELLINGS: set[str] = set()
for _n in range(100):
    _SPELT_NUMBERS.setdefault(spelling(_HINDI_0_99[_n]), set()).add(_n)
    _HINDI_SPELLINGS.add(spelling(_HINDI_0_99[_n]))
for _n in range(20):
    _SPELT_NUMBERS.setdefault(spelling(_EN_ONES[_n]), set()).add(_n)
for _n in range(2, 10):
    _SPELT_NUMBERS.setdefault(spelling(_EN_TENS[_n]), set()).add(_n * 10)
_DEVA_NUMBERS = {unicodedata.normalize("NFC", w): n for n, w in enumerate(_HINDI_0_99)}
_SPELT_MULTIPLIERS = {spelling(w): m for w, m in (
    ("सौ", 100), ("hundred", 100), ("हज़ार", 1000), ("हजार", 1000), ("thousand", 1000), ("लाख", 100000),
    ("lakh", 100000))}
_HINDI_SPELLINGS |= {spelling(w) for w in ("सौ", "हज़ार", "लाख")}
# Everyday English words that spell like a Hindi or English number ("for" is char, "this" is tees). Speech is
# Hinglish, so they are said all the time; they never start a figure.
_NOT_NUMBERS = frozenset({
    "for", "this", "to", "too", "the", "these", "those", "then", "than", "that", "there", "tea", "saw", "won",
    "tin", "ate", "eat", "sat", "set", "say", "see", "sea", "shy", "she", "no", "know", "now", "new", "net"})
# A number right after one of these is part of a figure this reader does not write: a range ("five to ten",
# "paanch se das"), a sum ("one hundred and five", "do sau aur paanch") or a fraction ("साढ़े तीन सौ" is 350,
# "one point five" is 1.5). Leaving it as words is safe; writing the tail alone would invent a smaller figure.
_JOINERS = frozenset({"and", "aur", "और", "se", "से", "to", "or", "ya", "या"})
_FRACTIONS = frozenset({"साढ़े", "साढे", "sadhe", "saadhe", "sade", "saade", "सवा", "sawa", "sava", "पौने",
                        "paune", "डेढ़", "डेढ", "dedh", "ढाई", "dhai", "point", "दशमलव", "dashamlav", "half"})
# Units in Latin script are taken only as spelt here: by sound, "reps", "roofs", "forest" and "present" are
# rupees and percent. Devanagari units, and units after a number said in Hindi, may be matched by sound.
_LATIN_UNITS = {
    "%": frozenset({"percent", "per cent", "persent", "pratishat", "pratishath", "pratisat", "parsent"}),
    "$": frozenset({"rupees", "rupee", "rupaye", "rupay", "rupe", "rupai", "rupaiya", "rupiya", "rupia", "rupis",
                    "rupies", "rupaie", "rupye", "rupaee"}),
}
_FIGURE_UNITS = {c: sorted(set(_UNIT_SOUNDS[c]) | {k for f in _ALIASES[c] if len(k := word_key(f)) >= 2})
                 for c in ("%", "$")}
_PLAIN_UNITS = frozenset({"percent", "rupees", "rs"})  # already read by the checks; nothing to rewrite
_MAX_DIGITS = 9  # a figure longer than this is a phone number or a transcription glitch, not a price


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@lru_cache(maxsize=4096)
def _spelt_value(sp: str) -> tuple[str, int] | None:
    """("n", value) for an exact number word, ("f", value) for a near one, ("m", factor) for a multiplier.
    A near spelling counts only when it is long and one edit from exactly one number."""
    if sp in _SPELT_MULTIPLIERS:
        return "m", _SPELT_MULTIPLIERS[sp]
    if sp in _SPELT_NUMBERS:
        values = _SPELT_NUMBERS[sp]
        return ("n", next(iter(values))) if len(values) == 1 else None  # 7 and 60 spell alike: refuse
    if len(sp) >= 4:
        near = {n for k, vs in _SPELT_NUMBERS.items() if abs(len(k) - len(sp)) <= 1 and edit_distance(sp, k) == 1
                for n in vs}
        if len(near) == 1:
            return "f", near.pop()
    return None


@lru_cache(maxsize=4096)
def _number_parts(token: str) -> tuple[tuple[str, int, bool], ...] | None:
    """The number parts in one token, each (kind, value, said in Hindi): kind "d" digits, "n" a number word,
    "f" a near one, "m" a multiplier."""
    digits = unicodedata.normalize("NFKC", token).translate(_DEVA_DIGITS)
    if digits.isdigit():
        return (("d", int(digits), False),) if len(digits) <= _MAX_DIGITS else None
    word = unicodedata.normalize("NFC", token)
    if word in _DEVA_NUMBERS:  # written in Devanagari the 7/60 pair is distinct (सात, साठ)
        return (("n", _DEVA_NUMBERS[word], True),)
    if token.lower() in _NOT_NUMBERS or not (sp := spelling(token)):
        return None
    hindi = any("ऀ" <= c <= "ॿ" for c in token)
    if (v := _spelt_value(sp)) is not None:
        return ((v[0], v[1], hindi or sp in _HINDI_SPELLINGS),)
    for i in range(2, len(sp) - 1):  # a number glued to its multiplier: "charso", "चार्सो"
        head, tail = _spelt_value(sp[:i]), sp[i:]
        if head and head[0] != "m" and tail in _SPELT_MULTIPLIERS:
            return (head + (True,), ("m", _SPELT_MULTIPLIERS[tail], True))
    return None


def _figure_unit(tokens: list[str], hindi: bool) -> tuple[str, bool] | None:
    """The unit `tokens` (one word, or two heard apart) name, and whether it matched exactly."""
    latin = all(t.isascii() for t in tokens)
    if latin:
        said = " ".join(unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower() for t in tokens)
        for code, forms in _LATIN_UNITS.items():
            if said in forms:
                return code, True
        if not hindi:
            return None
    keys = [word_key(t) for t in tokens]
    if len(keys) == 2 and min(map(len, keys)) < 2:
        return None
    key = "".join(keys)
    for code, unit_keys in _FIGURE_UNITS.items():
        if key in unit_keys:
            return code, True
    # A near miss counts only as one long word that starts like the unit: "place and" is not "percent".
    if len(tokens) == 1 and len(key) >= MIN_KEY:
        for code, unit_keys in _FIGURE_UNITS.items():
            if any(len(k) >= MIN_KEY and k[0] == key[0] and edit_distance(key, k) <= 1 for k in unit_keys):
                return code, False
    return None


def _joined(text: str, spans: list[tuple[int, int]], j: int) -> bool:
    """Whether word j touches the word before it with no space ("200.99", "5-25"): one written figure."""
    return j > 0 and not any(c.isspace() for c in text[spans[j - 1][1]:spans[j][0]])


def _may_start(text: str, spans: list[tuple[int, int]], tokens: list[str], i: int) -> bool:
    if i == 0:
        return True
    prev = tokens[i - 1].lower()
    if prev in _FRACTIONS or _number_parts(tokens[i - 1]) or _joined(text, spans, i):
        return False
    return not (prev in _JOINERS and i > 1 and _number_parts(tokens[i - 2]))


def _read_number(text: str, spans: list[tuple[int, int]], tokens: list[str], i: int
                 ) -> tuple[int, int, bool, bool, bool] | None:
    """The number said from tokens[i]: (value, index after it, any word read, any word near-matched, said in
    Hindi). None when no number starts there; value -1 when the words do not compose ("4100 ninyanve" is a
    mishearing)."""
    total = cur = 0
    seen = words = fuzzy = hindi = False
    j = i
    while j < len(tokens) and j - i < 6:
        parts = _number_parts(tokens[j])
        if not parts:
            break
        if j > i and _joined(text, spans, j):
            return -1, j + 1, words, fuzzy, hindi
        for kind, v, in_hindi in parts:
            if kind == "m":
                if not seen or (v == 100 and not 0 < cur < 100):
                    return -1, j + 1, words, fuzzy, hindi
                if v == 100:
                    cur *= 100
                else:
                    total, cur = total + max(cur, 1) * v, 0
            # The first number, one after a thousand, one after a round hundred ("char sau ninyanve",
            # "400 Ninyanwe"), or a unit after a tens word ("(one hundred) twenty five").
            elif (not seen or (cur == 0 and total) or (cur % 100 == 0 and cur < 1000 and v < 100)
                  or (cur % 100 >= 20 and cur % 10 == 0 and v < 10 and kind != "d")):
                cur += v
            else:
                return -1, j + 1, words, fuzzy, hindi
            seen = True
            words |= kind != "d"
            fuzzy |= kind == "f"
            hindi |= in_hindi
        j += 1
    return (total + cur, j, words, fuzzy, hindi) if seen else None


def write_figures(text: str) -> str:
    """`text` with each spoken price or percentage written the way the claim checks read it: "चालिस प्रतिषवत" ->
    "40%", "charso ninyanwe rupe" -> "₹499". Everything else is left exactly as transcribed."""
    spans = _word_spans(text)
    tokens = [text[a:b] for a, b in spans]
    out: list[str] = []
    i = cursor = 0
    while i < len(tokens):
        read = _read_number(text, spans, tokens, i) if _may_start(text, spans, tokens, i) else None
        if read is None:
            i += 1
            continue
        value, j, words, fuzzy, hindi = read
        if value < 0:
            i = j
            continue
        unit = None
        for width in (1, 2):  # a unit heard as two words: "पर संथ" is "per cent"
            if j + width <= len(tokens) and (u := _figure_unit(tokens[j:j + width], hindi)) is not None:
                unit, exact, k = u[0], u[1], j + width
                break
        # A near number and a near unit together are too much guessing.
        if unit is None or (fuzzy and not exact):
            i = j
            continue
        plain = not words and " ".join(tokens[j:k]).lower() in _PLAIN_UNITS
        if plain or value <= 0 or (unit == "%" and value > 100):
            i = k
            continue
        before = text[cursor:spans[i][0]]
        out.append(before)
        # "₹ 1 lakh rupees" names the currency twice; the sign is already there.
        signed = unit == "$" and re.search(r"(?:₹|\brs\.?)\s*$", before, re.IGNORECASE)
        out.append(f"{value}%" if unit == "%" else str(value) if signed else f"₹{value}")
        cursor = spans[k - 1][1]
        i = k
    out.append(text[cursor:])
    return "".join(out)
