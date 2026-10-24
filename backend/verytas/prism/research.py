"""Claim research: for a claim with no approved fact behind it, what the public web says.

An unsupported claim ("rated the best app by students across India") is raised because nothing in the
fact library backs it. A reviewer's next question is whether anything could. So for a few such claims
per review the claim is searched on the web (prism's only open-web step besides public portraits), and
the judge says, for each result, whether its text actually states what the claim says.

What it is, and is not:
- evidence for the reviewer, shown as "found on the web, not approved": it never raises, lowers or
  clears a finding, and the fact library stays the only thing a claim is checked against; a brand
  admin can turn a good source into an approved fact, which is the only way a web page becomes proof;
- only for public-tier content: a claim in a post that is going out is no secret, while an internal or
  confidential one must not be handed to a third-party search API at all. Confidential terms and personal
  data are masked out of the query as well;
- bounded: at most `per_review` searches per review, `per_workspace` per workspace and `per_day` in all,
  and every search is listed under "How it was checked", including one cut short by the time limit; a
  failed search says so and changes nothing else.

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
    """Searches left today for this process. `per_day` is the ceiling for everyone, so a busy demo can't run up
    a bill; `per_workspace` is each workspace's share of it, so one tenant resubmitting pieces cannot leave
    the others with nothing. A share of 0 or less means no share, only the ceiling."""
    per_day: int
    per_workspace: int = 0
    used: int = 0
    by_workspace: dict[int, int] = field(default_factory=dict)
    since: float = field(default_factory=time.monotonic)

    def take(self, workspace: int = 0) -> str | None:
        """None when a search may go ahead, else why it may not."""
        if time.monotonic() - self.since > _DAY_S:
            self.used, self.by_workspace, self.since = 0, {}, time.monotonic()
        if self.used >= self.per_day:
            return "daily limit reached"
        if self.per_workspace > 0 and self.by_workspace.get(workspace, 0) >= self.per_workspace:
            return "this workspace's daily limit reached"
        self.used += 1
        self.by_workspace[workspace] = self.by_workspace.get(workspace, 0) + 1
        return None


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
                   brand: str | None, cap: DailyCap, per_review: int = 3, *, workspace: int = 0,
                   log: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach web results to the first unsupported claims; returns the record for "How it was checked".

    The caller may pass `log` to keep what was done if this is cancelled by a time limit: every search is
    listed before it starts, as timed out, and its outcome is filled in when it ends.
    """
    todo = [f for f in findings if f.rule_code == RULE and f.quote][:per_review]
    if log is None:
        log = {}
    log.update({"provider": search.name, "searched": [], "skipped": 0})

    async def one(f: RawFinding) -> None:
        q = query_for(f, mask, brand)
        if q is None:
            log["skipped"] += 1
            return
        if (refused := cap.take(workspace)) is not None:
            log["searched"].append({"query": q, "outcome": refused})
            return
        entry: dict[str, Any] = {"query": q, "outcome": "timed out"}
        log["searched"].append(entry)
        try:
            found: list[WebResult] = await search.search(q)
        except Exception as exc:  # noqa: BLE001, a failed search is reported and changes nothing else
            entry["outcome"] = f"search failed: {str(exc)[:120]}"
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
        entry.update(outcome=f"{len(found)} result{'s' if len(found) != 1 else ''}",
                     likely_support=sum(1 for s in scores if s is not None and s >= SUPPORTS))

    await asyncio.gather(*(one(f) for f in todo))
    return log
