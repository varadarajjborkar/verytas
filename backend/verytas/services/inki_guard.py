"""Hard limits on Inki in conversations, enforced in code rather than asked of the model.

Inki speaks into a private conversation between two people, so the bar is higher than for Ask Inki. The
limits stack, and each holds even if the ones before it are talked round:

  1. What it can see. Only the last messages of this conversation, the pieces both people may open, and
     the files shared in it (api/messages.py builds that, nothing else of the workspace). Confidential
     terms are replaced before anything leaves (the redacting providers).
  2. What it is asked. A request for its instructions or set-up gets a fixed answer and the model is not
     called. Typed text has already passed the conversation guard, which refuses instructions aimed at
     the system along with personal numbers and bribes.
  3. How it is asked. Everything people wrote, and everything read out of files, goes in as quoted data
     with its own tags neutralised, so a message or a PDF can't close the data block and speak as the
     system.
  4. What comes back. A reply that recites its instructions is replaced. Contact details that aren't the
     company's public ones, and links of any kind, are taken out: Inki never sends people anywhere.
  5. How often. A per-person limit per hour, on top of the self-serve workspace budget.
"""

from __future__ import annotations

import re
import time
from collections import deque

from verytas.checks.base import ContactView
from verytas.security.guard import emails_in, phones_in

REFUSAL = ("I can't share how I'm set up. I can help with the pieces linked here, the files shared in this "
           "conversation and what was said in it.")
LIMITED = "I've answered a lot in the last hour. Try again a little later."

# Questions about Inki's own set-up, not instructions in general ("the logo usage instructions" is a
# question about the brand). Kept in step with web/src/lib/guard.ts.
_ASKS = [re.compile(p, re.IGNORECASE) for p in (
    r"\bsystem\s+(prompt|message|instructions?)\b",
    r"\b(initial|hidden|developer|secret|full|original)\s+(system\s+)?prompt\b",
    r"\bdeveloper\s+(message|instructions?)\b",
    r"\byour\s+(own\s+)?(prompt|instructions?|directives|configuration|system message|setup text|guidance|rules)\b",
    r"\b(repeat|print|show|reveal|output|dump|display|copy|recite|translate|encode|spell out|write out|type out|paste)"
    r"\b[^.?!\n]{0,60}\b(everything|text|words|all)( that)?( came| comes| come| is| was| you were given| you got)? "
    r"(before|above) (my|this|our|the) (first |opening )?(message|question|conversation|chat)\b",
    r"\bword for word\b[^.?!\n]{0,60}\b(before my|before this|above my|you were (told|given))\b",
    r"\bignore\s+(all\s+)?(of\s+)?(your|the|my|any)?\s*(previous|prior|above|earlier|preceding|system)\s+"
    r"(instructions?|rules|prompts?|directions)\b",
    r"\b(what|how)\s+(were|are|have)\s+you\s+(been\s+)?(told|instructed|programmed|prompted|configured)\b",
    r"\beverything\s+you\s+(were|have been|got)\s+(given|told|sent)\b",
    r"\b(pretend|act)\s+(to be|as|you are)\b[^.?!\n]{0,40}\b(unrestricted|jailbroken|no rules|developer mode|dan)\b",
    r"\b(other|all)\s+(creators?|workspaces?|brands?|clients?|users?)('s)?\s+(data|pieces|posts|content|messages)\b",
)]

_SHINGLE = 8
_LEAK_WORDS = 30
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_TAG = re.compile(r"</?\s*(pieces|files|conversation|system|instructions?)\b[^>]*>", re.IGNORECASE)


def asks_for_instructions(text: str) -> bool:
    return any(p.search(text) for p in _ASKS)


def inert(text: str) -> str:
    """People's text as data: our block tags inside it are broken so it can't end a block early."""
    return _TAG.sub(lambda m: m.group(0).replace("<", "(").replace(">", ")"), text)


def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def recites(reply: str, instructions: str) -> bool:
    """Whether the reply quotes the instructions at length: words covered by 8-word runs they share."""
    ref = _words(instructions)
    shingles = {" ".join(ref[i:i + _SHINGLE]) for i in range(len(ref) - _SHINGLE + 1)}
    words = _words(reply)
    covered: set[int] = set()
    for i in range(len(words) - _SHINGLE + 1):
        if " ".join(words[i:i + _SHINGLE]) in shingles:
            covered.update(range(i, i + _SHINGLE))
    return len(covered) >= _LEAK_WORDS


def scrub(reply: str, public: list[ContactView]) -> str:
    """Links out, and contact details that aren't the company's own public ones."""
    allowed = {c.normalized for c in public}
    out = _URL.sub("[link removed]", reply)
    for start, end, norm in sorted(phones_in(out, trust_labels=False) + emails_in(out), reverse=True):
        if norm not in allowed:
            out = out[:start] + "[contact removed]" + out[end:]
    return out


def checked(reply: str, instructions: str, public: list[ContactView]) -> str:
    if recites(reply, instructions):
        return REFUSAL
    return scrub(reply, public).strip()


class RateLimit:
    """At most `per_hour` Inki answers per person per rolling hour, held in this process."""

    def __init__(self, per_hour: int = 20) -> None:
        self.per_hour = per_hour
        self._seen: dict[object, deque[float]] = {}

    def take(self, who: object, now: float | None = None) -> bool:
        """`who` is a person's id, or anything finer (a person on one browser) where one id is many people."""
        now = time.monotonic() if now is None else now
        if len(self._seen) > 10_000:  # keys can be per browser: drop the ones idle for an hour
            self._seen = {k: v for k, v in self._seen.items() if v and now - v[-1] <= 3600}
        q = self._seen.setdefault(who, deque())
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= self.per_hour:
            return False
        q.append(now)
        return True
