"""Guardrails on what people type into the workflow.

Escalation messages, dispute claims, comments and creator notes are written
by people with a stake in the outcome, and some of them reach a model. Before
anything is stored or forwarded, it is screened here:

  refused   an offer of money, gifts or favours for a decision; an attempt to
            move the conversation off the record (personal phone numbers,
            private email, "WhatsApp me"); instructions aimed at the AI.
  flagged   accepted, but shown to the brand team with a marker: pressure or
            threats, links, and contact details that are the company's own
            public ones (looked up in the public-contacts register).

The screen is deterministic and cheap, so it runs on every write and its
verdict can be explained word for word. It errs on the side of refusing an
off-the-record contact: a creator who needs a call can ask for one in plain
words, and the brand team will reach out through the company's own channels.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from verytas.checks.base import ContactView
from verytas.security.terms import fold

__all__ = ["ContactView", "Flag", "GuardResult", "emails_in", "normalize_contact", "phones_in", "screen"]


@dataclass(frozen=True)
class Flag:
    code: str
    label: str
    quote: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "label": self.label, "quote": self.quote}


@dataclass
class GuardResult:
    refused: list[Flag] = field(default_factory=list)
    flagged: list[Flag] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refused

    def reason(self) -> str:
        """One sentence for the person whose text was refused. Names the problem, never the rule internals."""
        labels = sorted({f.label for f in self.refused})
        return ("This can't be sent: " + "; ".join(labels) + ". Keep it to what the content means and why "
                "the finding is wrong. The brand team will contact you through the company's own channels.")

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        return {"refused": [f.as_dict() for f in self.refused], "flagged": [f.as_dict() for f in self.flagged]}


# --- contact details ---------------------------------------------------------------

# Seven to fifteen digits with the usual separators, optionally with a country code.
# Years, prices and percentages are excluded below by digit count and context.
_PHONE = re.compile(r"(?<![\w.])(?:\+|00)?\d(?:[\s().\-/]{0,3}\d){6,14}(?![\w])")
_EMAIL = re.compile(r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b")
_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"]+", re.IGNORECASE)
_HANDLE_APPS = r"whats\s*app|telegram|signal|wechat|viber|snap(?:chat)?|insta(?:gram)?\s*dm|dm\s+me|imessage"
_OFF_RECORD = re.compile(
    rf"\b(?:{_HANDLE_APPS})\b|\b(?:call|ring|text|ping|message|contact)\s+me\b|\bmy\s+(?:number|cell|mobile|phone)\b"
    r"|\b(?:mera|mujhe)\s+(?:number|call)\b|\bnumber\s+(?:de|bhej)",
    re.IGNORECASE)
_DIGIT_WORDS = re.compile(r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)\b", re.IGNORECASE)
_PERSONAL_MAIL = re.compile(r"@(?:gmail|yahoo|outlook|hotmail|icloud|proton(?:mail)?|rediffmail|aol|gmx|yandex)\.",
                            re.IGNORECASE)


def normalize_phone(raw: str) -> str:
    """Digits only, compared on the last ten so "+91 98200 12345" equals "098200-12345"."""
    digits = re.sub(r"\D", "", raw)
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_contact(kind: str, value: str) -> str:
    v = unicodedata.normalize("NFKC", value).strip()
    if kind == "phone":
        return normalize_phone(v)
    if kind == "url":
        return re.sub(r"^(?:https?://)?(?:www\.)?", "", v.lower()).rstrip("/")
    if kind == "handle":
        return v.lower().lstrip("@")
    return v.lower()


def phones_in(text: str) -> list[tuple[int, int, str]]:
    """Phone-like runs as (start, end, normalized), skipping dates, years and amounts."""
    out = []
    for m in _PHONE.finditer(text):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if not 7 <= len(digits) <= 15:
            continue
        before = text[max(0, m.start() - 3):m.start()]
        after = text[m.end():m.end() + 2]
        # "Rs 1,20,00,000", "$1.5", "20%" and "2024-2025" are amounts and ranges, not numbers to call.
        if re.search(r"(?:rs\.?|inr|usd|eur|[$€£₹])\s*$", before, re.IGNORECASE) or after.startswith("%"):
            continue
        if re.fullmatch(r"(?:19|20)\d\d\s*[-/]\s*(?:19|20)?\d\d", raw.strip()):
            continue
        out.append((m.start(), m.end(), normalize_phone(raw)))
    return out


def emails_in(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(0).lower()) for m in _EMAIL.finditer(text)]


def _public(kind: str, normalized: str, contacts: list[ContactView]) -> ContactView | None:
    for c in contacts:
        if c.kind == kind and c.normalized == normalized:
            return c
    if kind == "email":
        # A listed domain ("press@kitepath.example" listed) covers the whole company domain.
        domain = normalized.rsplit("@", 1)[-1]
        for c in contacts:
            if c.kind == "email" and c.normalized.startswith("*@") and c.normalized[2:] == domain:
                return c
    return None


# --- inducements, pressure, instructions -------------------------------------------

_MONEY = r"(?:rs\.?|inr|₹|\$|usd|€|£|rupees?|dollars?|bucks|paise|paisa|cash|money|amount)"
_INDUCEMENT = re.compile(
    r"\b(?:bribe|kickback|backhander|under\s+the\s+table|grease|hush\s+money|commission\s+for\s+you)\b"
    rf"|\b(?:i(?:'ll| will| can| would)?|we(?:'ll| will| can)?|let me)\s+(?:pay|give|send|transfer|tip|treat|gift|"
    rf"buy\s+you|sponsor)\b[^.\n]{{0,40}}(?:{_MONEY}|\d|gift|card|voucher|coupon|dinner|trip|phone|iphone|favou?r)"
    r"|\bgift\s*cards?\b|\bamazon\s+voucher\b|\bpaytm\b|\bupi\b|\bgpay\b|\bphonepe\b|\bvenmo\b|\bpaypal\s+you\b"
    r"|\b(?:make\s+it\s+worth\s+your\s+while|something\s+in\s+return|return\s+the\s+favou?r|i\s+owe\s+you\s+one)\b"
    r"|\b(?:kuch|thoda)\s+(?:paise|le\s+lo|de\s+dunga|de\s+denge)\b|\b(?:chai\s*pani|kharcha\s*pani)\b"
    r"|\bpaise\s+(?:de|dunga|denge|bhej)",
    re.IGNORECASE)
_INSTRUCTION = re.compile(
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+|your\s+|previous\s+|prior\s+|above\s+)*"
    r"(?:instructions?|rules?|guidelines?|prompts?|checks?|findings?|policy|policies)\b"
    r"|\b(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are)|from\s+now\s+on\s+you)\b"
    r"|\b(?:system\s+prompt|developer\s+message|jailbreak|do\s+anything\s+now)\b"
    r"|\b(?:mark|set|flag)\s+(?:this|it|the\s+finding)\s+(?:as\s+)?(?:approved|passed|cleared|resolved|safe)\b"
    r"|\b(?:approve|clear|pass)\s+(?:this|it)\s+(?:now|immediately|automatically|without)\b"
    r"|<\s*/?\s*(?:system|instructions?|assistant)\s*>|\[\[\s*system",
    re.IGNORECASE)
_PRESSURE = re.compile(
    r"\b(?:or\s+else|you(?:'ll| will)\s+regret|i(?:'ll| will)\s+(?:complain|report|escalate)\s+(?:you|this)\s+to"
    r"|my\s+(?:uncle|father|friend)\s+is|i\s+know\s+(?:your|the)\s+(?:boss|ceo|manager)|last\s+warning"
    r"|legal\s+action|sue\s+you|get\s+you\s+fired)\b"
    r"|\b(?:urgent(?:ly)?|asap|right\s+now|immediately)\b.{0,30}\b(?:approve|clear|pass|publish)\b",
    re.IGNORECASE)


def _clip(text: str, start: int, end: int) -> str:
    return text[max(0, start - 20):min(len(text), end + 20)].strip()


def screen(text: str, contacts: list[ContactView] | None = None) -> GuardResult:
    """Screen one piece of user-written text. Pure: the caller stores and audits the verdict."""
    contacts = contacts or []
    result = GuardResult()
    # Folded copy catches look-alike letters and spacing tricks ("w h a t s a p p"); spans are not needed here.
    folded = fold(text, "space")[0]
    squashed = re.sub(r"(?<=\b\w) (?=\w\b)", "", folded)
    probes = (text, folded, squashed)

    def first(pattern: re.Pattern[str]) -> str | None:
        for p in probes:
            m = pattern.search(p)
            if m:
                return _clip(p, m.start(), m.end())
        return None

    if (q := first(_INDUCEMENT)) is not None:
        result.refused.append(Flag("inducement", "it offers money, gifts or favours in return for a decision", q))
    if (q := first(_INSTRUCTION)) is not None:
        result.refused.append(Flag("instruction", "it gives instructions to the system instead of explaining", q))

    off_record = first(_OFF_RECORD)
    for start, end, norm in phones_in(text):
        hit = _public("phone", norm, contacts)
        if hit:
            label = f"names the company's public number ({hit.label or hit.value})"
            result.flagged.append(Flag("public_contact", label, text[start:end]))
        else:
            result.refused.append(Flag("contact_exchange", "it shares a phone number that is not one of the "
                                       "company's public numbers", text[start:end]))
    # Numbers spelled out ("nine eight two zero...") are a common way around a digit filter.
    if len(_DIGIT_WORDS.findall(folded)) >= 7:
        result.refused.append(Flag("contact_exchange", "it spells out a phone number", _clip(folded, 0, 40)))
    for _start, _end, addr in emails_in(text):
        hit = _public("email", addr, contacts)
        if hit:
            result.flagged.append(Flag("public_contact", f"names a company address ({hit.label or hit.value})", addr))
        elif _PERSONAL_MAIL.search(addr) or off_record:
            result.refused.append(Flag("contact_exchange", "it shares a personal email address", addr))
        else:
            result.flagged.append(Flag("unlisted_contact", "names an email address that is not in the public register",
                                       addr))
    if off_record is not None and not any(f.code == "contact_exchange" for f in result.refused):
        result.refused.append(Flag("contact_exchange", "it asks to move the conversation off the record", off_record))
    if (q := first(_PRESSURE)) is not None:
        result.flagged.append(Flag("pressure", "uses pressure or threats", q))
    for m in _URL.finditer(text):
        norm = normalize_contact("url", m.group(0))
        if not any(c.kind == "url" and norm.startswith(c.normalized) for c in contacts):
            result.flagged.append(Flag("link", "contains a link outside the company's own sites", m.group(0)[:120]))
    return result
