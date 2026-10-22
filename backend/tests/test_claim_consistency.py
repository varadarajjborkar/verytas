"""Claims must be judged the same way every time, and a claim fix must actually settle the claim.

Bugs seen on the Review page: "Sign-in takes seconds." was only flagged when fact
retrieval happened to match something, and its fix "Sign-in is fast." was itself
flagged by the next review, so the creator could never finish.
"""

from __future__ import annotations

from datetime import date

from tests.helpers import make_ctx
from verytas.checks.base import FactView, RawFinding, SuggestedEdit
from verytas.checks.claims import ClaimList, ExtractedClaim, check_claims, drop_fixes_that_keep_claims
from verytas.providers.offline import OfflineJudge

TEAMS = FactView(2, "Verytas is used by 800+ teams", 800, "teams", "teams using Verytas", "Board deck Q3",
                 date(2026, 7, 1), None)


class ExtractsAsSpeedClaim:
    """Stand-in extractor: every sentence is a speed boast, which the live model labels superlative."""

    name = "stub/llm"

    async def run(self, task):
        return ClaimList(claims=[ExtractedClaim(quote=s.text, kind="superlative", subject="sign-in process")
                                 for s in task.sentences])


class ExtractsNothing:
    name = "stub/llm"

    async def run(self, task):
        return ClaimList(claims=[])


class ExtractsAs:
    """Stand-in extractor that labels every sentence with one fixed kind and subject."""

    name = "stub/llm"

    def __init__(self, kind: str, subject: str | None = None) -> None:
        self.kind, self.subject = kind, subject

    async def run(self, task):
        return ClaimList(claims=[ExtractedClaim(quote=s.text, kind=self.kind, subject=self.subject)
                                 for s in task.sentences])


async def test_the_text_not_the_model_label_decides_a_claims_kind():
    # Live models label "the #1 tool" factual in one review and superlative in the
    # next; the result must not depend on which.
    ctx = make_ctx("Verytas is the #1 review tool.", [], facts=[TEAMS])
    for label in ("factual", "superlative", "numeric"):
        [f] = await check_claims(ctx, ExtractsAs(label), OfflineJudge())
        assert f.rule_code == "CLAIM-UNSUPPORTED" and f.title == "Unsupported superlative claim"


async def test_factual_claims_do_not_depend_on_the_models_subject_line():
    # Whether a plain factual claim is reported is decided on its quote, so a
    # subject line that happens to match a fact can't flip the result.
    ctx = make_ctx("Our office opens at nine.", [], facts=[TEAMS])
    for subject in (None, "teams using Verytas"):
        assert await check_claims(ctx, ExtractsAs("factual", subject), OfflineJudge()) == []


def _claim_finding(quote: str, proposed: str, model: str | None = "stub/llm",
                   code: str = "CLAIM-CONTRADICTED") -> RawFinding:
    return RawFinding(unit_id="p1.s2", category="claims", title="Claim conflicts with an approved fact",
                      explanation="x", confidence=0.9, checker="claims", rule_code=code, quote=quote,
                      span_start=0, span_end=len(quote),
                      suggestion=SuggestedEdit(quote, proposed, "soften", model=model))


async def test_fix_taken_from_an_approved_fact_is_not_second_guessed():
    # "1,000+" -> "800+" comes straight from the fact library; only AI-written fixes are re-checked.
    # No facts in this context, so a re-check *would* flag the figure: only the policy can keep it.
    ctx = make_ctx("Verytas is trusted by 1,000+ teams.", [], facts=[])
    f = _claim_finding("Verytas is trusted by 1,000+ teams.", "Verytas is trusted by 800+ teams.", model=None)
    await drop_fixes_that_keep_claims([f], ctx, ExtractsAsSpeedClaim(), OfflineJudge())
    assert f.suggestion is not None


async def test_fix_that_still_makes_an_unbacked_claim_is_dropped():
    ctx = make_ctx("Sign-in takes seconds.", [], facts=[TEAMS])
    f = _claim_finding("Sign-in takes seconds.", "Sign-in is fast.")
    await drop_fixes_that_keep_claims([f], ctx, ExtractsAsSpeedClaim(), OfflineJudge())
    assert f.suggestion is None


async def test_fix_that_removes_the_claim_is_kept():
    ctx = make_ctx("Sign-in takes seconds.", [], facts=[TEAMS])
    f = _claim_finding("Sign-in takes seconds.", "Sign in with your work account.")
    await drop_fixes_that_keep_claims([f], ctx, ExtractsNothing(), OfflineJudge())
    assert f.suggestion is not None and f.suggestion.proposed == "Sign in with your work account."


class RecordingExtractor:
    """Flags only sentences that still say 'quick'; records the text it was shown."""

    name = "stub/llm"

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def run(self, task):
        self.seen.append(" ".join(s.text for s in task.sentences))
        return ClaimList(claims=[ExtractedClaim(quote=s.text, kind="superlative", subject=None)
                                 for s in task.sentences if "quick" in s.text])


async def test_fixes_are_rechecked_inside_the_whole_revised_draft():
    # The next review reads the whole draft, so the re-check must too: judged alone, a
    # sentence can pass the re-check and still be flagged by the next review.
    body = "Verytas is trusted by 800+ teams. Sign-in takes seconds. Setup takes minutes."
    ctx = make_ctx(body, [], facts=[TEAMS])
    sign_in = RawFinding(unit_id="p1.s2", category="claims", title="t", explanation="x", confidence=0.9,
                         checker="claims", rule_code="CLAIM-CONTRADICTED", quote="Sign-in takes seconds.",
                         span_start=34, span_end=56,
                         suggestion=SuggestedEdit("takes seconds", "is quick", "soften", model="stub/llm"))
    setup = RawFinding(unit_id="p1.s3", category="claims", title="t", explanation="x", confidence=0.9,
                       checker="claims", rule_code="CLAIM-CONTRADICTED", quote="Setup takes minutes.",
                       span_start=57, span_end=77,
                       suggestion=SuggestedEdit("Setup takes minutes.", "Set up your workspace.", "rephrase",
                                                model="stub/llm"))
    llm = RecordingExtractor()
    await drop_fixes_that_keep_claims([sign_in, setup], ctx, llm, OfflineJudge())

    assert llm.seen == ["Verytas is trusted by 800+ teams. Sign-in is quick. Set up your workspace."]
    assert sign_in.suggestion is None  # still a claim in the revised draft
    assert setup.suggestion is not None  # the claim is gone


async def test_non_claim_findings_are_left_alone():
    ctx = make_ctx("Send us an e-mail.", [], facts=[TEAMS])
    f = RawFinding(unit_id="p1", category="terminology", title="t", explanation="x", confidence=1.0,
                   checker="deterministic", rule_code="TERM-01", quote="e-mail", span_start=11, span_end=17,
                   suggestion=SuggestedEdit("e-mail", "email", "house style"))
    await drop_fixes_that_keep_claims([f], ctx, ExtractsAsSpeedClaim(), OfflineJudge())
    assert f.suggestion is not None


async def test_unsupported_claims_get_no_ai_rewrite():
    # No rewording can back a claim that has no approved fact: "next month" -> "soon" is still the
    # same unannounced claim, and the next review flags it again. The creator adds a fact, edits
    # the text, or dismisses it with a reason; an AI fix here would only send them in circles.
    body = "Project Lumen brings video review next month!"
    ctx = make_ctx(body, [], facts=[TEAMS])
    f = _claim_finding(body, "Project Lumen brings video review soon!", code="CLAIM-UNSUPPORTED")
    await drop_fixes_that_keep_claims([f], ctx, ExtractsNothing(), OfflineJudge())
    assert f.suggestion is None


async def test_unsupported_claim_says_how_to_resolve_it():
    # With no rewrite offered, the finding must tell the creator what actually settles it,
    # rather than an AI hint like "replace it with a vague term" (which just loops).
    body = "Project Lumen brings video review next month!"
    ctx = make_ctx(body, [], facts=[TEAMS])
    f = _claim_finding(body, "Project Lumen brings video review soon!", code="CLAIM-UNSUPPORTED")
    f.explanation = "Unsupported timeframe; replace 'next month' with a vague term."
    await drop_fixes_that_keep_claims([f], ctx, ExtractsNothing(), OfflineJudge())
    assert f.explanation.endswith("To resolve it, add an approved fact that backs it, reword it so it no longer "
                                  "states a fact, or dismiss it with a reason.")


async def test_overlapping_ai_fixes_are_not_shown_unchecked():
    body = "Sign-in takes seconds."
    ctx = make_ctx(body, [], facts=[TEAMS])
    first = _claim_finding(body, "Sign in with your work account.")
    second = _claim_finding(body, "Sign-in is simple.")
    await drop_fixes_that_keep_claims([first, second], ctx, ExtractsNothing(), OfflineJudge())
    assert first.suggestion is not None and second.suggestion is None


async def test_unsupported_claim_text_never_suggests_softening():
    ctx = make_ctx("Verytas is the #1 review tool.", [], facts=[TEAMS])
    [f] = await check_claims(ctx, ExtractsAs("superlative"), OfflineJudge())
    assert "soften" not in f.explanation and f.explanation.endswith("or dismiss it with a reason.")
