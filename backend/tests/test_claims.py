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


def test_a_rating_scale_is_not_a_second_quantity():
    from verytas.checks.claims import parse_numbers

    # "4.7 out of 5" once read as two claims, and the 5 "contradicted" a 4.7 rating fact.
    assert [n.value for n in parse_numbers("Rated 4.7 out of 5 by learners")] == [4.7]
    assert [n.value for n in parse_numbers("Learners give us 9/10")] == [9]


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


# A fact can store its scale in the unit ("1.2" + "million"), the way the showcase brand does.
LEARNERS = FactView(6, "Verytas has 1.2 million learners", 1.2, "million", "learners on Verytas",
                    "Annual report 2026", date(2026, 1, 1), None)


async def test_fact_with_a_multiplier_unit_supports_the_same_figure():
    assert await _run("Verytas has 1.2 million learners.", [LEARNERS]) == []


async def test_fix_keeps_the_claims_own_multiplier():
    # The fix once read "Verytas has 1.2 learners.": the number was swapped and the word dropped.
    [f] = await _run("Verytas has 2 million learners.", [LEARNERS])
    assert f.rule_code == "CLAIM-CONTRADICTED"
    assert f.suggestion.proposed == "Verytas has 1.2 million learners."
    [f] = await _run("Verytas has 2M learners.", [LEARNERS])
    assert f.suggestion.proposed == "Verytas has 1.2M learners."


def test_indian_multipliers_parse():
    assert parse_number("12 lakh learners").value == pytest.approx(1_200_000)
    assert parse_number("1.5 crore views").value == pytest.approx(15_000_000)


def test_fix_numbers_are_written_plainly():
    from verytas.checks.claims import _format_like

    # errcheck 214: float noise once printed "2.01e+06"; 215: a small fact once read "0.0008 million".
    assert _format_like("1800000", 2.01 * 1e6) == "2010000"
    assert _format_like("1,800,000", 2.01 * 1e6) == "2,010,000"
    assert _format_like("2 million", 2.01 * 1e6) == "2.01 million"
    assert _format_like("2 million", 800) == "800"
    assert _format_like("2M", 12_345_678) == "12.345678M"
    assert _format_like("800+", 1200) == "1200"
    assert _format_like("12 lakh", 1_500_000) == "15 lakh"


COURSES = FactView(7, "Kitepath offers 340 courses", 340, "courses", "courses", "Catalogue, October 2026",
                   date(2026, 10, 1), None)
LANGUAGES = FactView(8, "Kitepath courses are taught in 9 languages", 9, "languages", "languages",
                     "Catalogue, October 2026", date(2026, 10, 1), None)


@pytest.mark.parametrize("facts", [[COURSES, LANGUAGES], [LANGUAGES, COURSES]])
async def test_two_figures_are_each_compared_with_the_fact_about_their_own_unit(facts):
    # "taught in 9 languages" also contains the word "courses", so it is as relevant to "340" as the
    # courses fact is; the figure must not be called contradicted by the fact that is about languages.
    assert await _run("340 courses in 9 languages, short lessons and real mentors.", facts) == []


async def test_a_wrong_figure_is_still_caught_against_its_own_unit():
    [f] = await _run("340 courses in 12 languages.", [LANGUAGES, COURSES])
    assert f.rule_code == "CLAIM-CONTRADICTED" and f.fact_id == 8 and '"12"' in f.explanation
    [g] = await _run("400 courses in 9 languages.", [LANGUAGES, COURSES])
    assert g.rule_code == "CLAIM-CONTRADICTED" and g.fact_id == 7 and '"400"' in g.explanation


async def test_a_figure_one_equally_relevant_fact_states_is_not_contradicted_by_another():
    # Same relevance and no unit to tell them apart: the fact that states the figure supports it.
    a = FactView(9, "Kitepath serves learners in 9 states", 9, "states", "reach", "Annual report",
                 date(2026, 1, 1), None)
    b = FactView(10, "Kitepath serves learners in 28 cities", 28, "cities", "reach", "Annual report",
                 date(2026, 1, 1), None)
    assert await _run("Kitepath serves learners in 28 places.", [a, b]) == []


PRICE = FactView(11, "The Kitepath annual plan costs 4,999 rupees", 4999, "rupees", "annual plan price",
                 "Pricing page, Aug 2026", date(2026, 8, 1), None)
MENTORS = FactView(12, "Kitepath has 1,200 verified mentors", 1200, "mentors", "mentors", "Mentor desk report",
                   date(2026, 8, 1), None)


@pytest.mark.parametrize("facts", [[PRICE, MENTORS], [MENTORS, PRICE]])
async def test_a_figure_on_its_own_line_is_not_about_the_next_line(facts):
    # Text read off a picture: the words that follow 4,999 are the next line's, not what it counts.
    card = "Annual plan\nRs 4,999\nAsk a mentor anything\n1,200 verified mentors"
    assert await _run(card, facts) == []
    [f] = await _run(card.replace("4,999", "5,999"), facts)
    assert f.rule_code == "CLAIM-CONTRADICTED" and '"5,999"' in f.explanation and f.fact_id == 11


def test_a_wrong_total_is_not_excused_by_another_facts_value():
    # "12 teams per workspace" is a different quantity from the total; 12 is still the wrong total.
    from tests.helpers import make_ctx
    from verytas.checks.base import FactView
    from verytas.checks.claims import _verify_numbers, parse_numbers

    facts = [FactView(1, "Kitepath has 800 active teams", 800, "teams", "teams", "r", date(2026, 1, 1), None),
             FactView(2, "Each workspace holds up to 12 teams", 12, "teams per workspace", "workspace", "r",
                      date(2026, 1, 1), None)]
    ctx = make_ctx("", [], facts=facts)
    quote = "Kitepath has 12 teams."
    [r] = _verify_numbers(quote, parse_numbers(quote), facts, ctx)
    assert r.verdict == "contradicted"


def test_a_figure_judged_on_its_own_line_first():
    from tests.helpers import make_ctx
    from verytas.checks.base import FactView
    from verytas.checks.claims import _verify_numbers, parse_numbers

    facts = [FactView(1, "Kitepath offers 340 courses", 340, "courses", "courses", "r", date(2026, 1, 1), None),
             FactView(2, "Kitepath has 1,200 mentors", 1200, "mentors", "mentors", "r", date(2026, 1, 1), None)]
    ctx = make_ctx("", [], facts=facts)
    quote = "1,200 courses\n1,200 mentors"
    first, second = _verify_numbers(quote, parse_numbers(quote), facts, ctx)
    assert first.verdict == "contradicted" and second.verdict == "supported"


def test_phone_numbers_clock_times_and_opening_hours_are_not_quantities():
    from verytas.checks.claims import parse_numbers

    # Seeded demo regression: the support line was a blocker, "4567" and "9" against "open 7 days a week".
    assert parse_numbers("Our support team is on +91 80 4567 8900, every day 9 to 9.") == []
    assert parse_numbers("Call 1800-123-4567, open 10 am to 6 pm") == []
    assert [n.value for n in parse_numbers("Class at 9:30 for 45 minutes")] == [45]
    # A range with a unit is a quantity; so is a range of percentages.
    assert [n.value for n in parse_numbers("Delivery in 5 to 7 days")] == [5, 7]
    assert [n.value for n in parse_numbers("Save 10-20% today")] == [10, 20]


def test_a_rate_is_not_judged_against_a_total_or_a_fact_about_something_else():
    from tests.helpers import make_ctx
    from verytas.checks.base import FactView
    from verytas.checks.claims import _verify_numbers, parse_numbers

    facts = [FactView(1, "Kitepath has 1.2 million learners", 1.2, "million", "learners", "r", date(2026, 1, 1), None),
             FactView(2, "Learner support is open 7 days a week", 7, "days", "support days", "r", date(2026, 1, 1),
                      None)]
    ctx = make_ctx("", [], facts=facts)

    def verdicts(quote):
        return [r.verdict for r in _verify_numbers(quote, parse_numbers(quote), facts, ctx)]

    # Seeded demo regression: one mentor's weekly group was a blocker against the support-days fact.
    assert verdicts("Meet Ananya, who mentors 40 learners a week in our design track.") == ["unmatched"]
    assert verdicts("Kitepath has 2 million learners") == ["contradicted"]
    assert verdicts("Support is open 6 days a week") == ["contradicted"]
    # A span of time is about whatever the sentence is about: a recording's 30 days are not support's 7.
    assert verdicts("The recording stays up for 30 days.") == ["unmatched"]
    assert verdicts("Our support team is open 6 days.") == ["contradicted"]
    # Through retrieval, which ranks by shared words and hands over only the support fact.
    quote = "Meet Ananya, who mentors 40 learners a week in our design track."
    assert [r.verdict for r in _verify_numbers(quote, parse_numbers(quote), facts[1:], ctx)] == ["unmatched"]


def test_ranges_and_quantities_that_look_like_phones_or_hours_are_still_read():
    from verytas.checks.claims import parse_numbers

    def vals(t):
        return [n.value for n in parse_numbers(t)]

    # errcheck 360: a rising pair is a range, not a phone number.
    assert vals("12000-15000 users") == [12000, 15000] and vals("5000 - 6000 students") == [5000, 6000]
    assert vals("Call 98765 43210") == [] and vals("Call 9876543210") == [] and vals("1800-123-4567") == []
    # errcheck 362: hours need words that say so, wherever the unit is.
    assert vals("Open 9 to 9 daily") == [] and vals("Open 9-6 on weekdays") == []
    assert vals("Class 8 to 10.") == [8, 10] and vals("Ages 18-24") == [18, 24] and vals("Pay ₹5-10") == [5, 10]


def test_a_period_on_one_side_only_still_lets_a_contradiction_through():
    # errcheck 361: the rate rule skips totals for a rate of counts, nothing else.
    from tests.helpers import make_ctx
    from verytas.checks.base import FactView
    from verytas.checks.claims import _verify_numbers, parse_numbers

    for fact, quote in (
            (FactView(1, "Support is open 7 days a week", 7, "days", "support days", "r", date(2026, 1, 1), None),
             "Support is open 6 days."),
            (FactView(2, "The annual plan costs 4999 rupees", 4999, "rupees", "annual plan price", "r",
                      date(2026, 1, 1), None), "Pay 999 rupees a year for the annual plan")):
        ctx = make_ctx("", [], facts=[fact])
        assert [r.verdict for r in _verify_numbers(quote, parse_numbers(quote), [fact], ctx)] == ["contradicted"]


def test_errcheck_369_to_371_totals_rates_hours_and_spaced_thousands():
    from tests.helpers import make_ctx
    from verytas.checks.base import FactView
    from verytas.checks.claims import _verify_numbers, parse_numbers

    # 369: a total is not judged against a rate fact either.
    rate = FactView(1, "Ananya mentors 40 learners a week", 40, "learners", "learners a week", "r",
                    date(2026, 1, 1), None)
    quote = "Kitepath has 2 million learners"
    ctx = make_ctx("", [], facts=[rate])
    assert [r.verdict for r in _verify_numbers(quote, parse_numbers(quote), [rate], ctx)] == ["unmatched"]

    def vals(t):
        return [n.value for n in parse_numbers(t)]

    # 370: an amount after "open" is still an amount.
    assert vals("Open to all, 5 to 10 seats") == [5, 10] and vals("Open for 8 to 12 hours") == [8, 12]
    assert vals("open 10-6, Mon-Sat") == []
    # 371: spaced thousands are one number; a 5 + 5 mobile number is a phone.
    assert vals("10 000 000 learners") == [10_000_000] and vals("Join 10 000 learners") == [10_000]
    assert vals("Call 90000 98765") == [] and vals("12000-15000 users") == [12000, 15000]
