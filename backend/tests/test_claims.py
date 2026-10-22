from datetime import date

import pytest

from tests.helpers import make_ctx, rule, system_rule_views
from verytas.checks.base import FactView
from verytas.checks.claims import check_claims, compare_numbers, parse_number, retrieve
from verytas.checks.semantic import check_semantic
from verytas.providers.base import Answer
from verytas.providers.offline import OfflineJudge, OfflineLLM

TODAY = date(2026, 10, 20)

TEAMS_OLD = FactView(1, "Verytas is used by 500+ teams", 500, "teams", "teams using Verytas",
                     "Board deck Q1", date(2025, 1, 1), date(2026, 7, 1))
TEAMS_NOW = FactView(2, "Verytas is used by 800+ teams", 800, "teams", "teams using Verytas",
                     "Board deck Q3", date(2026, 7, 1), None)
UPTIME = FactView(3, "Verytas uptime was 99.9% over the last 12 months", 99.9, "%", "uptime",
                  "Status page", date(2026, 1, 1), None)
SOC2 = FactView(4, "Verytas is SOC 2 Type II certified", None, None, "security certification",
                "Audit report", date(2026, 3, 1), None)
LAUNCH = FactView(5, "Verytas supports video review", None, None, "video review",
                  "Roadmap", date(2027, 1, 15), None)


@pytest.mark.parametrize(("text", "value", "at_least", "pct"), [
    ("Trusted by 800+ teams", 800, True, False),
    ("more than 1,200 brands", 1200, True, False),
    ("99.9% uptime", 99.9, False, True),
    ("2.5M posts reviewed", 2_500_000, False, False),
    ("Since 2019 we served 40 teams", 40, False, False),
])
def test_parse_number(text, value, at_least, pct):
    n = parse_number(text)
    assert n.value == pytest.approx(value) and n.at_least is at_least and n.percent is pct


def test_compare_numbers_allows_understatement_only_with_at_least():
    assert compare_numbers(parse_number("500+ teams"), 800) == "supported"
    assert compare_numbers(parse_number("500 teams"), 800) == "contradicted"
    assert compare_numbers(parse_number("1,000+ teams"), 800) == "contradicted"
    assert compare_numbers(parse_number("99.9%"), 99.9) == "supported"


def test_retrieval_prefers_relevant_facts():
    hits = retrieve("Trusted by 1,000+ teams worldwide", [UPTIME, TEAMS_NOW, SOC2])
    assert hits[0] is TEAMS_NOW and UPTIME not in hits


async def _run(body, facts, judge=None):
    ctx = make_ctx(body, system_rule_views(), facts=facts, today=TODAY)
    return await check_claims(ctx, OfflineLLM(), judge or OfflineJudge())


async def test_overstated_number_is_contradicted_with_fix():
    findings = await _run("Verytas is trusted by 1,000+ teams.", [TEAMS_OLD, TEAMS_NOW])
    [f] = findings
    assert f.rule_code == "CLAIM-CONTRADICTED" and f.fact_id == 2
    assert f.suggestion.proposed == "Verytas is trusted by 800+ teams."


async def test_claim_matching_only_expired_fact_is_outdated_and_suggests_current():
    findings = await _run("Verytas is used by 500+ teams.", [TEAMS_OLD])
    [f] = findings
    assert f.rule_code == "CLAIM-OUTDATED" and f.fact_id == 1
    assert "2026-07-01" in f.explanation
    assert f.suggestion is None  # no current fact in the library to suggest


async def test_stale_number_is_outdated_and_suggests_current_value():
    [f] = await _run("Verytas is used by 500 teams.", [TEAMS_OLD, TEAMS_NOW])
    assert f.rule_code == "CLAIM-OUTDATED" and f.fact_id == 1
    assert f.suggestion.proposed == "Verytas is used by 800 teams."


async def test_understatement_with_plus_is_fine_even_with_newer_fact():
    assert await _run("Verytas is used by 500+ teams.", [TEAMS_OLD, TEAMS_NOW]) == []


async def test_supported_claims_produce_no_findings():
    assert await _run("Verytas uptime was 99.9% last year.", [UPTIME]) == []


async def test_superlative_without_backing_is_unsupported():
    findings = await _run("Verytas is the best governance tool on the planet.", [UPTIME])
    [f] = findings
    assert f.rule_code == "CLAIM-UNSUPPORTED" and f.needs_explanation and f.fact_id is None


async def test_future_fact_is_flagged_as_not_yet_valid():
    class SupportsEverything(OfflineJudge):
        async def ask(self, state, questions):
            return {k: Answer("noul", 0.95 if k == "supported" else 0.05) for k in questions}

    findings = await _run("The best part: Verytas supports video review.", [LAUNCH], SupportsEverything())
    [f] = findings
    assert "not valid yet" in f.title and "2027-01-15" in f.explanation


async def test_spans_point_at_the_claim_text():
    body = "Hello there.\n\nVerytas is trusted by 1,000+ teams."
    [f] = await _run(body, [TEAMS_NOW])
    assert body[f.span_start:f.span_end] == f.quote


async def test_semantic_rules_flag_matching_paragraphs():
    jargon = rule("VOICE-01", {}, category="tone", kind="semantic", rid=7, text="Plain words, no buzzwords.",
                  bad_examples=("leverage synergies to unlock paradigm shifts",),
                  good_examples=("we help teams publish faster",))
    body = "We leverage synergies to unlock paradigm shifts.\n\nWe help teams publish faster."
    ctx = make_ctx(body, [jargon], today=TODAY)
    findings = await check_semantic(ctx, OfflineJudge(), threshold=0.6)
    assert [f.unit_id for f in findings] == ["p1"]
    assert findings[0].model == "offline/judge" and findings[0].rule_code == "VOICE-01"


async def test_voice_score_flags_below_floor():
    class LowScore(OfflineJudge):
        async def ask(self, state, questions):
            return {k: Answer("score", 0.4, 0.7, {"0": 0.6, "1": 0.3, "2": 0.1}) for k in questions}

    voice = rule("VOICE-SCORE", {"type": "voice_score", "levels": ["off-brand", "neutral", "on-brand"],
                                 "min_level": 1}, category="tone", kind="semantic")
    findings = await check_semantic(make_ctx("Some copy.", [voice]), LowScore(), threshold=0.6)
    [f] = findings
    assert f.confidence == pytest.approx(0.6) and "off-brand" in f.title


COUNTRIES = FactView(6, "Verytas is used in 40 countries", 40, "countries", "countries", "Board deck Q3",
                     date(2026, 7, 1), None)


async def test_each_number_is_checked_against_its_own_fact():
    assert await _run("Verytas is used by 800 teams in 40 countries.", [COUNTRIES, TEAMS_NOW]) == []
    assert await _run("Verytas is used by 800 teams in 40 countries.", [TEAMS_NOW, COUNTRIES]) == []


async def test_a_later_wrong_number_is_caught_and_fixed():
    [f] = await _run("Verytas is used by 800 teams in 90 countries.", [TEAMS_NOW, COUNTRIES])
    assert f.rule_code == "CLAIM-CONTRADICTED" and f.fact_id == 6
    assert f.suggestion.proposed == "Verytas is used by 800 teams in 40 countries."


async def test_unmatched_figure_is_unsupported():
    [f] = await _run("Verytas is used by 800 teams across 12 industries.", [TEAMS_NOW])
    assert f.rule_code == "CLAIM-UNSUPPORTED" and '"12"' in f.explanation


def test_rank_is_not_a_quantity():
    from verytas.checks.claims import parse_numbers

    assert [n.value for n in parse_numbers("The #1 tool, used by 800 teams")] == [800]


def test_a_true_figure_worded_unlike_the_fact_library_is_supported():
    # Black-box finding: "churn rate is 9%" against the fact "9% monthly churn"
    # came back "unsupported" because the words after the number didn't match.
    from datetime import date

    from tests.helpers import make_ctx
    from verytas.checks.base import FactView
    from verytas.checks.claims import _verify_numbers, parse_numbers

    fact = FactView(1, "9% monthly churn rate", 9, "%", "monthly churn rate", "Metrics", date(2026, 1, 1), None)
    quote = "Our current churn rate is 9%, a number we keep pushing down."
    [res] = _verify_numbers(quote, parse_numbers(quote), [], make_ctx(quote, facts=[fact]))
    assert res.verdict == "supported" and res.fact is fact
