"""Grading a review from the outside.

Two kinds of judgement, both made only from what the API returned:

* plant verdicts: was each planted violation caught (finding in an acceptable
  category overlapping the planted span), and did any control draw a finding?
* contract invariants that hold for any input: spans point at the text they
  quote, every finding cites something, signatures verify, a suggested fix
  edits text that exists and doesn't re-introduce what it was meant to fix.
"""

from __future__ import annotations

import re
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


_CODE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+")


def rule_code(f: dict[str, Any]) -> str:
    """The rule a finding cites, read from its public citation label ("CONF-LEAK: ...")."""
    for c in f.get("citations") or []:
        m = _CODE.match(c.get("label") or "")
        if m:
            return m.group(0)
    return ""


def _matches(f: dict[str, Any], p: Plant) -> bool:
    if f.get("category") not in p.categories:
        return False
    if p.codes and not rule_code(f).startswith(p.codes):
        return False
    if p.attachment == "colors":
        return f.get("span_start") is None and "contrast" in (f.get("title") or "").lower()
    if p.attachment:
        where = f"{f.get('unit_id') or ''} {f.get('source') or ''}"
        return p.attachment in where or p.attachment in (f.get("quote") or "")
    if _overlaps(f, p.start, p.end):
        return True
    return f.get("span_start") is None and bool(p.text) and p.text in (f.get("quote") or "")


def _fold(s: str) -> str:
    """A loose comparison form: compatibility forms, invisible characters,
    case and every separator gone, so "game\u2011changer", "Game Changer" and
    "gamechanger" compare equal, as they do for a reader."""
    s = "".join(c for c in unicodedata.normalize("NFKC", s) if unicodedata.category(c) != "Cf")
    return re.sub(r"[\W_]+", "", s.casefold())


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
        # Spans of findings inside images, pages or video point into that source's
        # text, not the caption; only body spans can be checked against the body.
        if s is not None and e is not None and (f.get("source") or "body") == "body":
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
                if _fold(term) not in folded:
                    continue
                if _fold(term) not in _fold(original):
                    g.invariant_failures.append(("fix_adds_banned_term", f"finding {fid}: {proposed!r}"))
                elif _fold(term) in _fold(quote or ""):
                    # The flagged text has the term and the fix keeps it.
                    g.invariant_failures.append(("fix_keeps_banned_term", f"finding {fid}: {proposed!r}"))
        if id(f) not in used:
            g.unplanned.append({"title": f.get("title"), "category": f.get("category"), "level": f.get("level"),
                                "quote": (quote or "")[:120], "checker": f.get("checker")})
    return g


def rejected_grade(plants: list[Plant], why: str) -> Grade:
    """Verdicts for a case the API refused outright. Flag plants count as
    missed (no review caught them) and controls as false positives (clean
    content was turned away), so a system can't score well by refusing
    exactly the hard inputs. The refusal itself is listed too."""
    g = Grade()
    g.invariant_failures.append(("case_rejected", why))
    for p in plants:
        g.verdicts.append({"arm": p.arm, "tier": p.tier, "expect": p.expect, "text": p.text,
                           "verdict": "missed" if p.expect == "flag" else "false_positive",
                           "span": [p.start, p.end], "hits": [], "rejected": True})
    return g
