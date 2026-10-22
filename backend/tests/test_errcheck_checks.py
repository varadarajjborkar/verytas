"""Regressions for rule matching, folding, emoji and presentation findings."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from tests.helpers import make_ctx, rule, system_rule_views
from verytas.checks.base import TermView
from verytas.checks.deterministic import run_deterministic
from verytas.checks.emoji import count
from verytas.checks.patterns import validate_pattern
from verytas.checks.semantic import check_semantic
from verytas.prism.presentation import _VERTICAL_CHANNELS, _key
from verytas.providers.base import Answer
from verytas.schemas import TermIn
from verytas.security.redaction import Redactor
from verytas.security.terms import fold, term_pattern


async def test_a_voice_rule_saved_without_min_level_uses_the_midpoint():
    pattern = {"type": "voice_score", "levels": ["cold", "neutral", "warm"], "question": "How warm?",
               "min_level": None}
    r = rule("TONE-01", pattern, category="tone", kind="semantic")

    class Judge:
        name = "test/judge"

        async def ask(self, state, questions):
            return {k: Answer(type="score", value=0, probabilities={"0": 0.9, "1": 0.1}) for k in questions}

    findings = await check_semantic(make_ctx("A cold reply.", [r]), Judge(), threshold=0.6)
    assert [f.rule_code for f in findings] == ["TONE-01"]


@pytest.mark.parametrize("junk", ["--", "__", "\U0001f525\U0001f525", "\u200b\u200b"])
def test_terms_that_fold_to_nothing_are_refused_and_never_crash(junk):
    with pytest.raises(ValidationError):
        TermIn(term=junk)
    assert term_pattern(junk).search("anything at all") is None
    assert Redactor(["Lumen", junk]).redact("Lumen ships") != "Lumen ships"


def test_codenames_spelled_in_letter_symbols_are_still_seen():
    terms = [TermView(1, "Lumen", date(2099, 1, 1))]
    for body in ("New: \U0001f13b\U0001f144\U0001f13c\U0001f134\U0001f13d",  # squared letters
                 "New: \U0001f1f1\U0001f1fa\U0001f1f2\U0001f1ea\U0001f1f3"):  # regional indicators
        assert any(f.rule_code == "CONF-LEAK" for f in run_deterministic(make_ctx(body, system_rule_views(),
                                                                                   terms=terms)))


def test_long_texts_are_not_cached_by_the_folder():
    from verytas.security import terms

    terms._fold_cached.cache_clear()
    fold("x" * 10_000)
    assert terms._fold_cached.cache_info().currsize == 0


def test_emoji_in_a_term_never_matches_a_plain_space():
    with pytest.raises(ValueError):
        validate_pattern("deterministic", {"type": "banned_terms", "terms": ["\U0001f351"]})
    r = rule("TERM-09", {"type": "banned_terms", "terms": ["\U0001f351 deal"]})
    assert [f.quote for f in run_deterministic(make_ctx("Great. Big deal. A deal here.", [r]))] == ["deal", "deal"]


def test_text_symbols_count_as_emoji_only_with_emoji_presentation():
    assert count("\u00a9\ufe0f \u25b6\ufe0f 1\ufe0f\u20e3 \u2122\ufe0f") == 4
    assert count("\u2605 \u2714 \u00a9 \u2122 5 stars") == 0


def test_channel_names_are_normalised_for_the_safe_zone_check():
    assert _key("YouTube Shorts") in _VERTICAL_CHANNELS and _key(" Instagram ") in _VERTICAL_CHANNELS
