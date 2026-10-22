"""Grading a review from the outside.

Two kinds of judgement, both made only from what the API returned:

* plant verdicts: was each planted violation caught (finding in an acceptable
  category overlapping the planted span), and did any control draw a finding?
* contract invariants that hold for any input: spans point at the text they
  quote, every finding cites something, signatures verify, a suggested fix
  edits text that exists and doesn't re-introduce what it was meant to fix.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from blackbox.plants import Plant


@dataclass
class Grade:
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    invariant_failures: list[tuple[str, str]] = field(default_factory=list)
    unplanned: list[dict[str, Any]] = field(default_factory=list)


def _overlaps(f: dict[str, Any], start: int, end: int) -> bool:
    s, e = f.get("span_start"), f.get("span_end")
    return s is not None and e is not None and s < end and start < e


def _matches(f: dict[str, Any], p: Plant) -> bool:
    if f.get("category") not in p.categories:
        return False
    if p.attachment == "colors":
        return f.get("span_start") is None and "contrast" in (f.get("title") or "").lower()
    if p.attachment:
        return p.attachment in (f.get("unit_id") or "") or p.attachment in (f.get("quote") or "")
    if _overlaps(f, p.start, p.end):
        return True
    return f.get("span_start") is None and bool(p.text) and p.text in (f.get("quote") or "")


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold()


def grade(body: str, plants: list[Plant], review: dict[str, Any], *, codename: str,
          banned: list[str]) -> Grade:
    g = Grade()
    if review.get("status") != "done":
        g.invariant_failures.append(("review_not_done", f"status={review.get('status')} error={review.get('error')}"))
        return g
    findings = review.get("findings") or []

    used: set[int] = set()
    for p in plants:
        hits = [f for f in findings if _matches(f, p)]
        used.update(id(f) for f in hits)
        verdict = ("caught" if hits else "missed") if p.expect == "flag" else ("false_positive" if hits else "ok")
        g.verdicts.append({"arm": p.arm, "tier": p.tier, "expect": p.expect, "text": p.text, "verdict": verdict,
                           "span": [p.start, p.end],
                           "hits": [{"title": f.get("title"), "level": f.get("level")} for f in hits]})

    for f in findings:
        fid = f.get("id")
        s, e, quote = f.get("span_start"), f.get("span_end"), f.get("quote")
        if s is not None and e is not None:
            if not (0 <= s < e <= len(body)):
                g.invariant_failures.append(("span_out_of_range", f"finding {fid}: [{s},{e}) on {len(body)} chars"))
            elif quote is not None and body[s:e] != quote:
                g.invariant_failures.append(("span_quote_mismatch",
                                             f"finding {fid}: body[{s}:{e}]={body[s:e]!r} quote={quote!r}"))
        if not f.get("citations"):
            g.invariant_failures.append(("uncited_finding", f"finding {fid}: {f.get('title')}"))
        if not f.get("signature_valid", False):
            g.invariant_failures.append(("bad_signature", f"finding {fid}"))
        for sug in f.get("suggestions") or []:
            original, proposed = sug.get("original") or "", sug.get("proposed") or ""
            if original and quote is not None and original not in quote:
                g.invariant_failures.append(("fix_edits_missing_text", f"finding {fid}: {original!r} not in quote"))
            folded = _fold(proposed)
            if _fold(codename) in folded:
                g.invariant_failures.append(("fix_keeps_codename", f"finding {fid}: {proposed!r}"))
            for term in banned:
                if _fold(term) in folded and _fold(term) not in _fold(original):
                    g.invariant_failures.append(("fix_adds_banned_term", f"finding {fid}: {proposed!r}"))
        if id(f) not in used:
            g.unplanned.append({"title": f.get("title"), "category": f.get("category"), "level": f.get("level"),
                                "quote": (quote or "")[:120], "checker": f.get("checker")})
    return g
