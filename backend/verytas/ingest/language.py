"""Which language a piece is written in, so each check knows whether it can read it.

Creators write from anywhere, and many mix languages in one post (Hinglish above all). Nothing here
translates or judges: it only tells word-based checks when they are out of their depth, so they stay
quiet instead of guessing, and the review says so. The model judge reads every language regardless.

Non-Latin scripts are decided by the script itself. Latin-script text is decided by votes from each
language's commonest short words, which is reliable from a sentence or two and costs nothing.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

# Script ranges, checked per letter. Devanagari covers Hindi and Marathi alike; the label says Hindi
# because that is by far the commonest here, and nothing downstream depends on the difference.
_SCRIPTS: tuple[tuple[str, str, int, int], ...] = (
    ("hi", "Hindi", 0x0900, 0x097F), ("bn", "Bengali", 0x0980, 0x09FF), ("pa", "Punjabi", 0x0A00, 0x0A7F),
    ("gu", "Gujarati", 0x0A80, 0x0AFF), ("or", "Odia", 0x0B00, 0x0B7F), ("ta", "Tamil", 0x0B80, 0x0BFF),
    ("te", "Telugu", 0x0C00, 0x0C7F), ("kn", "Kannada", 0x0C80, 0x0CFF), ("ml", "Malayalam", 0x0D00, 0x0D7F),
    ("ar", "Arabic or Urdu", 0x0600, 0x06FF), ("ru", "Russian", 0x0400, 0x04FF), ("el", "Greek", 0x0370, 0x03FF),
    ("he", "Hebrew", 0x0590, 0x05FF), ("th", "Thai", 0x0E00, 0x0E7F), ("ko", "Korean", 0xAC00, 0xD7AF),
    ("ja", "Japanese", 0x3040, 0x30FF), ("zh", "Chinese", 0x4E00, 0x9FFF),
)

# The commonest short words of each Latin-script language. "hi-Latn" is Hindi typed in Latin letters.
_COMMON_TEXT: dict[str, str] = {
    "en": "the and is are was to of in for with on this that you your our it be at from by we not have has will"
          " can an or but so just if all they he she what who how now about more",
    "hi-Latn": "hai hain ka ki ke ko se mein me aur bhi kya ye yeh wo woh ho hum aap tum nahi nahin karo kar karna"
               " raha rahe tha thi apna apni sab abhi bas toh to ek liye",
    # Tamil typed in Latin letters ("da" and "di" left out: Portuguese and Italian use them too).
    "ta-Latn": "indha enna illa semma romba nalla naan vaa irukku pannu sollu inga anga epdi seri",
    "es": "el la los las de que y en un una es por con para del al lo como más pero sus su muy",
    "fr": "le la les de des et en un une est pour que qui dans du au avec sur pas plus nous vous ce",
    "de": "der die das und ist nicht mit den dem ein eine zu auf für von sie wir ich es im auch",
    "pt": "o a os as de que e em um uma é para com não do da dos das por mais seu sua você",
    "it": "il lo la gli le di che e è un una per con non del della dei sono più anche",
    "id": "yang dan di ini itu dengan untuk tidak dari ke ada akan kami kita anda",
}
_COMMON = {lang: frozenset(words.split()) for lang, words in _COMMON_TEXT.items()}
COMMON_WORDS = frozenset().union(*_COMMON.values())
NAMES = {"en": "English", "hi-Latn": "Hindi (Latin letters)", "hinglish": "Hinglish",
         "ta-Latn": "Tamil (Latin letters)", "tanglish": "Tanglish", "es": "Spanish", "fr": "French", "de": "German",
         "pt": "Portuguese", "it": "Italian", "id": "Indonesian", **{code: name for code, name, _, _ in _SCRIPTS}}
# Languages the word-based tone and topic lists are written for (checks/voice.py).
WORD_LISTS = frozenset({"en", "hi", "hi-Latn", "hinglish", "es", "fr", "de", "pt"})
_LATIN_WORD = re.compile(r"[a-zà-öø-ÿ']+")


@dataclass(frozen=True)
class Language:
    code: str  # "en", "hi", "hinglish", ... or "und" when there is too little text to tell
    name: str
    confidence: float
    mixed: tuple[str, ...] = field(default=())  # other languages with a real share of the text

    @property
    def english(self) -> bool:
        return self.code == "en"


UNKNOWN = Language("und", "Unknown", 0.0)


def detect(text: str) -> Language:
    text = unicodedata.normalize("NFC", text or "")
    scripts: Counter[str] = Counter()
    latin = 0
    for ch in text:
        if not ch.isalpha():
            continue
        cp = ord(ch)
        if cp < 0x250:
            latin += 1
            continue
        for code, _, lo, hi in _SCRIPTS:
            if lo <= cp <= hi:
                scripts[code] += 1
                break
    letters = latin + sum(scripts.values())
    if letters < 12:
        return UNKNOWN
    if scripts:
        top, n = scripts.most_common(1)[0]
        if top == "zh" and scripts["ja"]:
            top, n = "ja", scripts["ja"] + scripts["zh"]  # kanji with kana is Japanese
        if n / letters >= 0.3:
            others = tuple(c for c, m in scripts.items()
                           if c != top and m / letters >= 0.15 and not (top == "ja" and c == "zh"))
            return Language(top, NAMES[top], round(n / letters, 2), others + (("en",) if latin / letters >= 0.2
                                                                              else ()))
    words = _LATIN_WORD.findall(text.lower())
    if not words:
        return UNKNOWN
    votes = {lang: sum(w in common for w in words) / len(words) for lang, common in _COMMON.items()}
    best, share = max(votes.items(), key=lambda kv: kv[1])
    if share == 0:
        return Language("und", "Unknown", 0.0)
    # A second language is part of the mix when it brings words of its own: Spanish "pero" in an English post
    # counts, the "de" and "la" that Spanish, French and Portuguese all share do not.
    # One- and two-letter words ("a", "o", "de") are too shared to tell anyone apart.
    own = {lang: sum(1 for w in words if len(w) > 2 and w in common and w not in _COMMON[best])
           for lang, common in _COMMON.items() if lang != best}
    mixed = tuple(lang for lang, n in sorted(own.items(), key=lambda kv: -kv[1]) if n >= 2 and n / len(words) >= 0.06)
    # Romanised Indian languages are almost always written into English: Hinglish, Tanglish.
    for romanised, blend in (("hi-Latn", "hinglish"), ("ta-Latn", "tanglish")):
        parts = {best, *mixed}
        if romanised in parts and ("en" in parts or votes["en"] >= 0.04):
            return Language(blend, NAMES[blend], round(share + votes["en"], 2),
                            ("en", romanised, *[m for m in mixed if m not in ("en", romanised)]))
    name = NAMES[best] + (" with " + " and ".join(NAMES[m] for m in mixed) if mixed else "")
    return Language(best, name, round(min(1.0, share * 3), 2), mixed)
