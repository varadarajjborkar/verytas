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
- kept to what a page could confirm, from sources people know: only a claim with a figure, a ranking, a
  superlative or an award is searched (a teaser like "Something big is coming" brings back anything at all),
  the brand's name is quoted in the query, and a result is shown only if it is in English, comes from a
  known publication, public body or university (KNOWN_SITES), and names the brand. Measured on the demo's
  claims before this: 84% of the results came from unknown sites and 63% never named the brand;
- bounded: at most `per_review` searches per review, `per_workspace` per workspace and `per_day` in all,
  and every search is listed under "How it was checked", including one cut short by the time limit; a
  failed search says so and changes nothing else.

Page text is untrusted: it goes to the judge as escaped content (providers/ollama_judge.py), it is only
ever shown as text, and only http(s) links are kept.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from verytas.checks.base import RawFinding
from verytas.providers.base import JudgeProvider, Question
from verytas.providers.websearch import WebResult

RULE = "CLAIM-UNSUPPORTED"
SUPPORTS = 0.6  # the judge's p(yes) at which a source is shown as likely backing the claim
SHOWN = 3  # results shown per claim
FETCHED = 8  # results asked for, so the filters below still leave a few to show
_QUERY_CHARS = 200
_DAY_S = 86_400.0
_LATIN = 0.9  # share of a result's letters in the Latin script for it to count as English

# What a search could find a page confirming: a figure, a rank, a superlative, an award, a scale.
# Any digit counts ("98%", "#1", "No.1", "500 cities"); a few digit-only lines ("24/7") get searched too, and the
# source filters below decide what is shown.
_CHECKABLE = re.compile(
    r"\d|\bnumber[\s-]one\b|\b(best|best[\s-]?selling|top|leading|largest|biggest|fastest|cheapest|most|first|only|"
    r"world[\s-]class|favou?rite|popular|award\w*|winning|rated|ranked|ranking|trusted|millions?|lakhs?|crores?)\b",
    re.I)
# Words that make up a good part of any English sentence and few in other Latin-script languages.
_ENGLISH_WORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by", "from", "at", "is", "are", "was",
    "were", "be", "has", "have", "it", "this", "that", "its", "as", "not", "but", "our", "your", "their", "more",
    "than"})
# What follows a brand in a company's registered name and never in how people write about it.
_LEGAL_SUFFIX = re.compile(r"[\s,.]+(private|pvt|limited|ltd|llp|llc|inc|plc|corp|corporation|gmbh|co)\.?$", re.I)

# Sources a reviewer would recognise and could weigh: wire services and major papers (global and Indian),
# business and startup press, data and company registries, app stores and review sites, rankings and public
# bodies. A host matches itself and its subdomains; the suffixes cover government and universities anywhere.
# Not LinkedIn or social sites: anyone can make a page there in a brand's name (a control run found two
# lookalike company pages for a real food delivery brand).
KNOWN_SITES = frozenset({
    "wikipedia.org", "britannica.com",
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "theguardian.com", "nytimes.com", "washingtonpost.com",
    "wsj.com", "ft.com", "bloomberg.com", "economist.com", "forbes.com", "cnbc.com", "cnn.com", "techcrunch.com",
    "theverge.com", "wired.com",
    "thehindu.com", "thehindubusinessline.com", "indianexpress.com", "hindustantimes.com", "indiatimes.com",
    "livemint.com", "business-standard.com", "moneycontrol.com", "financialexpress.com", "ndtv.com", "news18.com",
    "indiatoday.in", "deccanherald.com", "scroll.in", "theprint.in", "yourstory.com", "inc42.com", "entrackr.com",
    "the-ken.com",
    "statista.com", "crunchbase.com", "tracxn.com", "ibef.org", "nasscom.in",
    "play.google.com", "apps.apple.com", "trustpilot.com", "g2.com", "capterra.com",
    "nirfindia.org", "topuniversities.com", "timeshighereducation.com", "aicte-india.org",
    "worldbank.org", "oecd.org", "unesco.org", "un.org",
})
_PUBLIC_SUFFIXES = (".gov", ".gov.in", ".nic.in", ".gov.uk", ".int", ".edu", ".edu.in", ".ac.in", ".ac.uk")


def checkable(quote: str) -> bool:
    """Whether a page could confirm the claim: it states a figure, a rank, a superlative or an award."""
    return bool(_CHECKABLE.search(quote))


def known_site(host: str) -> bool:
    host = host.lower().rstrip(".")
    return (any(host == d or host.endswith("." + d) for d in KNOWN_SITES)
            or any(host.endswith(s) for s in _PUBLIC_SUFFIXES))


def english(text: str) -> bool:
    """Mostly Latin letters, and for a passage of any length, common English words among them. The search API
    takes no language, so a page in another script or language is dropped here."""
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c < "\u0250" for c in letters) / len(letters) < _LATIN:
        return False
    words = re.findall(r"[a-z]+", text.lower())
    return len(words) < 12 or sum(w in _ENGLISH_WORDS for w in words) / len(words) >= 0.12


def brand_name(name: str | None) -> str | None:
    """The brand as people write it: the workspace's name without "Pvt Ltd" and the like, apostrophes straight."""
    if not name:
        return None
    name = _plain(name).strip()
    while (cut := _LEGAL_SUFFIX.sub("", name)) != name:
        name = cut
    return name or None


def _plain(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'")


def keep(r: WebResult, brand: str | None) -> bool:
    """A result worth a reviewer's time: in English, from a source they know, and about this brand."""
    text = f"{r.title} {r.snippet}"
    about = brand is None or brand.lower() in _plain(f"{text} {r.url}").lower()
    return about and known_site(r.site) and english(text)


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
    """What to search: the claim as written, masked, with the brand's name in quotes so results are about it.
    None for a claim with nothing a page could confirm."""
    text = " ".join(mask(f.quote or "").split())[:_QUERY_CHARS]
    if len(text) < 8 or "[confidential]" in text:
        return None  # a claim about a codename is not searched at all, even masked
    if not checkable(text):
        return None
    if not brand:
        return text
    # Quoted where the claim names it as a word of its own; anywhere else ("Kitepaths", already in quotes) it
    # goes in front instead.
    if f'"{brand.lower()}"' in text.lower():
        return text
    whole = re.compile(rf'(?<![\w"]){re.escape(brand)}(?![\w"])', re.I)
    if whole.search(text):
        return whole.sub(lambda m: f'"{m.group(0)}"', text, count=1)
    return f'"{brand}" {text}'


async def research(findings: list[RawFinding], search: Any, judge: JudgeProvider, mask: Callable[[str], str],
                   brand: str | None, cap: DailyCap, per_review: int = 3, *, workspace: int = 0,
                   log: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach web results to the first unsupported claims; returns the record for "How it was checked".

    The caller may pass `log` to keep what was done if this is cancelled by a time limit: every search is
    listed before it starts, as timed out, and its outcome is filled in when it ends.
    """
    brand = brand_name(brand)
    claims = [f for f in findings if f.rule_code == RULE and f.quote]
    # A line with nothing a page could confirm doesn't use up one of the review's searches.
    todo = [f for f in claims if checkable(f.quote or "")][:per_review]
    if log is None:
        log = {}
    log.update({"provider": search.name, "searched": [], "skipped": len(claims) - len(todo)})

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
            fetched: list[WebResult] = await search.search(q, FETCHED)
        except Exception as exc:  # noqa: BLE001, a failed search is reported and changes nothing else
            entry["outcome"] = f"search failed: {str(exc)[:120]}"
            return
        found = [r for r in fetched if keep(r, brand)][:SHOWN]
        entry["dropped"] = len(fetched) - len(found)
        if not found:
            entry["outcome"] = (f"no result in English from a known source{f' naming {brand}' if brand else ''}"
                                f" ({len(fetched)} found)")
            return
        scores: list[float | None] = [None] * len(found)
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
