"""One issue, one finding: the overlap passes in prism/dedupe.py."""

from __future__ import annotations

from verytas.checks.base import RawFinding
from verytas.prism.dedupe import collapse, restated

BODY = ("Unlike other apps that just sell you videos, KiteLearn actually teaches. We are the best coding "
        "school in India and we guarantee results in 30 days!")


def finding(quote: str, *, rule: str, category: str, checker: str, confidence: float = 0.9,
            whole: bool = False) -> RawFinding:
    start = 0 if whole else BODY.index(quote)
    end = len(BODY) if whole else start + len(quote)
    return RawFinding(unit_id="p1", category=category, title=quote, explanation="", confidence=confidence,
                      checker=checker, rule_code=rule, quote=BODY[start:end], span_start=start, span_end=end)


def span(quote: str) -> tuple[int, int]:
    start = BODY.index(quote)
    return start, start + len(quote)


def test_a_context_reading_that_restates_a_claim_is_skipped():
    claim = finding("We are the best coding school in India", rule="CLAIM-UNSUPPORTED", category="claims",
                    checker="claims")
    assert restated("body", *span("the best coding school in India"), "misleading_implication", [claim]) is claim


def test_a_different_kind_of_reading_on_the_same_words_stays():
    # A stereotype or double meaning is its own problem, even on words a claim check flagged.
    claim = finding("We are the best coding school in India", rule="CLAIM-UNSUPPORTED", category="claims",
                    checker="claims")
    assert restated("body", *span("the best coding school in India"), "stereotype", [claim]) is None


def test_a_paragraph_wide_finding_does_not_swallow_a_phrase_inside_it():
    rivals = finding("", rule="MSG-RIVALS", category="messaging", checker="semantic", whole=True)
    assert restated("body", *span("we guarantee results in 30 days!"), "misleading_implication", [rivals]) is None


def test_a_reading_in_another_source_is_not_matched_against_the_body():
    claim = finding("We are the best coding school in India", rule="CLAIM-UNSUPPORTED", category="claims",
                    checker="claims")
    assert restated("img:1", *span("We are the best coding school in India"), "misleading_implication",
                    [claim]) is None


def test_overlapping_findings_for_one_rule_collapse_to_the_strongest():
    weak = finding("the best coding school", rule="CLAIM-UNSUPPORTED", category="claims", checker="claims",
                   confidence=0.7)
    strong = finding("We are the best coding school in India", rule="CLAIM-UNSUPPORTED", category="claims",
                     checker="claims", confidence=0.95)
    other = finding("we guarantee results in 30 days!", rule="CLAIM-UNSUPPORTED", category="claims",
                    checker="claims")
    tone = finding("the best coding school", rule="TONE-PLAIN", category="tone", checker="semantic")
    assert collapse([weak, other, strong, tone]) == [strong, other, tone]
