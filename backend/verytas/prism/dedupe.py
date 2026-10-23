"""One issue, one finding.

Several workers can land on the same words: the claims check and a semantic rule both read "the
best coding school in India", and the context layer, which is there for meaning that only shows up
around a phrase, proposes the same sentence again as a "misleading implication". Each copy costs a
reviewer a decision and a model call to explain and fix, and makes the review read as noisier than
the post is. Two passes, both span-based and deterministic:

- a context reading that restates a literal finding on the same words is not sent to the judge;
- findings for the same rule on overlapping words collapse into the strongest one.
"""

from __future__ import annotations

from verytas.checks.base import RawFinding

# What each kind of context reading means in the literal checks' terms. A reading of a kind not
# listed here (a stereotype, a double meaning, a taunt) stays even where a claim is flagged on the
# same words, since it is a different problem with the same quote.
_RESTATES = {
    "misleading_implication": {"claims", "messaging"},
    "competitor_dig": {"claims", "messaging"},
}
_MIN_SHARE = 0.5  # of the shorter span
_MAX_STRETCH = 3.0  # a paragraph-wide finding doesn't cover one phrase inside it


def _share(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = min(a[1], b[1]) - max(a[0], b[0])
    shortest = min(a[1] - a[0], b[1] - b[0])
    return inter / shortest if inter > 0 and shortest > 0 else 0.0


def _span(f: RawFinding) -> tuple[int, int] | None:
    if f.span_start is None or f.span_end is None or f.span_end <= f.span_start:
        return None
    return f.span_start, f.span_end


def restated(source: str, start: int, end: int, kind: str, findings: list[RawFinding]) -> RawFinding | None:
    """The literal finding a context reading of `kind` on source[start:end] would only repeat."""
    covers = _RESTATES.get(kind)
    if not covers or end <= start:
        return None
    for f in findings:
        span = _span(f)
        if (f.checker == "context" or f.source != source or f.category not in covers or span is None
                or span[1] - span[0] > _MAX_STRETCH * (end - start)):
            continue
        if _share(span, (start, end)) >= _MIN_SHARE:
            return f
    return None


def _comparable(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Spans of about the same size: one finding across a paragraph does not stand in for two phrases in it."""
    la, lb = a[1] - a[0], b[1] - b[0]
    return max(la, lb) <= _MAX_STRETCH * max(min(la, lb), 1)


def collapse(findings: list[RawFinding]) -> list[RawFinding]:
    """Findings for one rule on overlapping words in one source, reduced to the most confident.
    A deterministic finding wins a tie, since it quotes exactly what the rule names. Order is kept."""
    keep: list[RawFinding] = []
    for f in findings:
        span = _span(f)
        twin = next((k for k in keep if span is not None and k.rule_code and k.rule_code == f.rule_code
                     and k.fact_id == f.fact_id and k.source == f.source
                     and (ks := _span(k)) is not None and _share(ks, span) >= _MIN_SHARE
                     and _comparable(ks, span)), None)
        if twin is None:
            keep.append(f)
        elif (f.confidence, f.checker == "deterministic") > (twin.confidence, twin.checker == "deterministic"):
            keep[keep.index(twin)] = f
    return keep
