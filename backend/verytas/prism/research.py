"""Claim research: for a claim with no approved fact behind it, what the public web says.

An unsupported claim ("rated the best app by students across India") is raised because nothing in the
fact library backs it. A reviewer's next question is whether anything could. So for a few such claims
per review the claim is searched on the web (prism's only open-web step besides public portraits), and
the judge says, for each result, whether its text actually states what the claim says.

What it is, and is not:
- evidence for the reviewer, shown as "found on the web, not approved": it never raises, lowers or
  clears a finding, and the fact library stays the only thing a claim is checked against; a brand
  admin can turn a good source into an approved fact, which is the only way a web page becomes proof;
- never for confidential content, and confidential terms and personal data are masked out of the query;
- bounded: at most `per_review` searches per review and `per_day` per process, and every search is
  listed under "How it was checked"; a failed search says so and changes nothing else.

Page text is untrusted: it goes to the judge as escaped content (providers/ollama_judge.py), it is only
ever shown as text, and only http(s) links are kept.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from verytas.checks.base import RawFinding
from verytas.providers.base import JudgeProvider, Question
from verytas.providers.websearch import WebResult

RULE = "CLAIM-UNSUPPORTED"
SUPPORTS = 0.6  # the judge's p(yes) at which a source is shown as likely backing the claim
_QUERY_CHARS = 200
_DAY_S = 86_400.0


@dataclass
class DailyCap:
    """Searches left today for this process. Shared by every review, so a busy demo can't run up a bill."""
    per_day: int
    used: int = 0
    since: float = field(default_factory=time.monotonic)

    def take(self) -> bool:
        if time.monotonic() - self.since > _DAY_S:
            self.used, self.since = 0, time.monotonic()
        if self.used >= self.per_day:
            return False
        self.used += 1
        return True


def _question() -> Question:
    return Question(
        "noul",
        "Does the source text state what the claim says, about the same subject, with the same figure, ranking "
        "or award? The source is a web page and may be about something else.",
        {"true": "The source states the claim, or the same figure or ranking for the same subject.",
         "false": "The source is about something else, states a different figure, or does not say it."},
        hints={"yes": [], "no": []})


def query_for(f: RawFinding, mask: Callable[[str], str], brand: str | None) -> str | None:
    """What to search: the claim as written, masked, with the brand's name so results are about it."""
    text = " ".join(mask(f.quote or "").split())[:_QUERY_CHARS]
    if len(text) < 8 or "[confidential]" in text:
        return None  # a claim about a codename is not searched at all, even masked
    return f"{brand} {text}" if brand and brand.lower() not in text.lower() else text


async def research(findings: list[RawFinding], search: Any, judge: JudgeProvider, mask: Callable[[str], str],
                   brand: str | None, cap: DailyCap, per_review: int = 3) -> dict[str, Any]:
    """Attach web results to the first unsupported claims; returns the record for "How it was checked"."""
    todo = [f for f in findings if f.rule_code == RULE and f.quote][:per_review]
    log: dict[str, Any] = {"provider": search.name, "searched": [], "skipped": 0}

    async def one(f: RawFinding) -> None:
        q = query_for(f, mask, brand)
        if q is None:
            log["skipped"] += 1
            return
        if not cap.take():
            log["searched"].append({"query": q, "outcome": "daily limit reached"})
            return
        try:
            found: list[WebResult] = await search.search(q)
        except Exception as exc:  # noqa: BLE001, a failed search is reported and changes nothing else
            log["searched"].append({"query": q, "outcome": f"search failed: {str(exc)[:120]}"})
            return
        scores: list[float | None] = [None] * len(found)
        if found:
            try:
                answers = await asyncio.gather(*(judge.ask({"claim": f.quote or "", "source": r.snippet},
                                                           {"supports": _question()}) for r in found))
                scores = [a["supports"].p_yes if a.get("supports") and a["supports"].type == "noul" else None
                          for a in answers]
            except Exception:  # noqa: BLE001, unjudged results are still shown, marked as unread
                pass
        f.research = [{"title": r.title, "url": r.url, "site": r.site, "snippet": r.snippet[:300],
                       "supports": None if s is None else round(s, 3)} for r, s in zip(found, scores, strict=True)]
        log["searched"].append({"query": q, "outcome": f"{len(found)} result{'s' if len(found) != 1 else ''}",
                                "likely_support": sum(1 for s in scores if s is not None and s >= SUPPORTS)})

    await asyncio.gather(*(one(f) for f in todo))
    return log
