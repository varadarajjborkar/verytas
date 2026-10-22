"""Regressions for gaps the black-box simulator found from the outside."""

from __future__ import annotations

from datetime import date

import pytest

from tests.helpers import make_ctx, rule, system_rule_views
from verytas.checks.base import TermView
from verytas.checks.claims import _PROMO, parse_numbers
from verytas.checks.deterministic import run_deterministic
from verytas.security.redaction import Redactor
from verytas.security.terms import fold

BANNED = rule("TERM-02", {"type": "banned_terms", "terms": ["fat-burning"]})


@pytest.mark.parametrize("written", [
    "f\u0430t-burning",  # Cyrillic a
    "fat\u200b-burning",  # zero-width space
    "\uff46\uff41\uff54\uff0d\uff42\uff55\uff52\uff4e\uff49\uff4e\uff47",  # full-width
])
def test_banned_terms_see_through_lookalikes_and_invisible_characters(written):
    body = f"Honestly this one is {written} for athletes."
    [f] = run_deterministic(make_ctx(body, [BANNED]))
    # The span and quote still point at exactly what the writer typed.
    assert f.quote == written and body[f.span_start:f.span_end] == written


def test_folding_keeps_a_map_back_to_the_original():
    folded, index = fold("a\u200bb\uff43")
    assert folded == "abc" and index == (0, 2, 3, 4)


def test_hidden_codename_is_flagged_and_redacted():
    terms = [TermView(1, "Project Lumen", date(2099, 1, 1))]
    body = "Psst, Proj\u200bect Lum\u0435n is coming."  # zero-width space, Cyrillic "\u0435"
    findings = run_deterministic(make_ctx(body, system_rule_views(), terms=terms))
    assert any(f.rule_code == "CONF-LEAK" for f in findings)
    assert "men" not in Redactor(["Project Lumen"]).redact(body)


def test_preferred_terms_suggest_on_folded_match():
    r = rule("TERM-01", {"type": "preferred_terms", "map": {"e-mail": "email"}})
    body = "\u0415-mail us."  # Cyrillic capital E
    [f] = run_deterministic(make_ctx(body, [r]))
    assert f.suggestion.original == body[:6] and f.suggestion.proposed == "Email"


def test_indian_digit_grouping_is_one_number():
    assert [n.value for n in parse_numbers("1,40,000 students and 12,34,567 views")] == [140000, 1234567]
    assert [n.value for n in parse_numbers("1,000,000 users")] == [1_000_000]


def test_rank_superlatives_are_seen():
    assert _PROMO.search("We are the #1 sports drink")
    assert _PROMO.search("the only brand that gets it")


def test_file_name_alt_text_is_flagged():
    images = [{"id": "hero", "alt": "IMG_20260412_0931.png"}, {"id": "ok", "alt": "A runner after a race"}]
    findings = run_deterministic(make_ctx("Body text here.", system_rule_views(), attachments={"images": images}))
    alt = [f for f in findings if f.rule_code == "A11Y-ALT"]
    assert [f.unit_id for f in alt] == ["img:hero"]


def test_dash_variants_match_in_both_rule_and_text():
    # The LLM-generated brand wrote its banned phrase with a non-breaking
    # hyphen; writers will type a plain one, and pasted copy brings en dashes.
    r = rule("TERM-02", {"type": "banned_terms", "terms": ["world\u2011class care"]})
    body = "We offer world-class care and world\u2013class care."
    assert [f.quote for f in run_deterministic(make_ctx(body, [r]))] == ["world-class care", "world\u2013class care"]



def test_em_dash_still_ends_a_word():
    r = rule("TERM-02", {"type": "banned_terms", "terms": ["cheap"]})
    body = "It is cheap\u2014really. A\u2014cheap\u2014b."
    assert [f.quote for f in run_deterministic(make_ctx(body, [r]))] == ["cheap", "cheap"]


@pytest.mark.parametrize("hidden", ["\u200e", "\u200f", "\u202a", "\u2063", "\u034f", "\ufe0f", "\u3164"])
def test_every_kind_of_invisible_character_is_ignored(hidden):
    terms = [TermView(1, "Project Lumen", date(2099, 1, 1))]
    body = f"Psst, Proj{hidden}ect Lumen is coming."
    assert any(f.rule_code == "CONF-LEAK" for f in run_deterministic(make_ctx(body, system_rule_views(), terms=terms)))
    assert "Lumen" not in Redactor(["Project Lumen"]).redact(body)


def test_genuine_cyrillic_words_are_not_read_as_latin():
    r = rule("TERM-02", {"type": "banned_terms", "terms": ["cop", "pop"]})
    assert run_deterministic(make_ctx("\u0441\u043e\u0440 \u0440\u043e\u0440", [r])) == []
    # Mixed script is still caught, even with an invisible split in the middle.
    [f] = run_deterministic(make_ctx("a \u0441\u200bop here", [r]))
    assert f.quote == "\u0441\u200bop"


def test_redaction_round_trips_when_matches_share_an_expanded_character():
    red = Redactor(["f"])
    text = "\ufb00 x"  # one ligature character that folds to "ff"
    out = red.redact(text)
    assert out.count("[[TERM_") == 1 and red.restore(out) == text


async def test_existing_workspaces_get_public_built_in_rules(client, tmp_path):
    from sqlalchemy import select

    from verytas.models import Rule, Tier
    from verytas.services.workspace import backfill_system_rule_tiers

    client.post("/bootstrap", json={"workspace_name": "Old", "admin_email": "a@old.io", "admin_name": "A"})
    db = client.app.state.db
    async with db.sessionmaker() as s:
        for r in (await s.scalars(select(Rule).where(Rule.system.is_(True)))).all():
            r.tier = Tier.internal  # what an older database holds
        await s.commit()
        assert await backfill_system_rule_tiers(s) > 0
        tiers = {r.tier for r in (await s.scalars(select(Rule).where(Rule.system.is_(True)))).all()}
    assert tiers == {Tier.public}


def test_a_suggested_fix_that_restores_a_codename_is_dropped():
    # Live black-box finding: the model saw [[TERM_1]], restoring it put the
    # codename back into the proposed fix.
    from verytas.prism.suggest import _leaks

    assert _leaks("Silver Quill is hinting at a new upgrade.", ["Silver Quill"])
    assert _leaks("Silver\u200bQuill soon", ["Silver Quill"])
    assert not _leaks("A new upgrade is on the way.", ["Silver Quill"])


def test_letter_spaced_terms_and_codenames_are_caught_and_redacted():
    r = rule("TERM-03", {"type": "banned_terms", "terms": ["synergy"]})
    assert [f.quote for f in run_deterministic(make_ctx("They call it s y n e r g y now", [r]))] == ["s y n e r g y"]
    terms = [TermView(1, "Project Glacier", date(2099, 1, 1))]
    body = "Psst, P.r.o.j.e.c.t G l a c i e r is near"
    assert any(f.rule_code == "CONF-LEAK" for f in run_deterministic(make_ctx(body, system_rule_views(), terms=terms)))
    assert "G l a c" not in Redactor(["Project Glacier"]).redact(body)
    # Ordinary short words and spaced numbers are left alone.
    assert run_deterministic(make_ctx("I a m fine, a b c. Rated 4 . 5 stars", [r])) == []


def test_banned_terms_catch_plurals():
    banned = rule("TERM-04", {"type": "banned_terms", "terms": ["game-changer"]})
    found = run_deterministic(make_ctx("Two game-changers in one week", [banned]))
    assert [f.quote for f in found] == ["game-changers"]


@pytest.mark.parametrize("written", [
    "we guarantee results", "it guarantees results", "guaranteeing results", "a guaranteed result",
])
def test_banned_phrases_catch_other_forms_of_their_words(written):
    # Seen live: "we guarantee results" walked past a ban on "guaranteed results".
    r = rule("CLAIM-PROMISE", {"type": "banned_terms", "terms": ["guaranteed results"]})
    [f] = run_deterministic(make_ctx(f"Join now and {written} in a month.", [r]))
    assert "guarantee" in f.quote.lower()


@pytest.mark.parametrize(("term", "text"), [
    ("fast", "Try intermittent fasting with us."),  # short words stay literal
    ("guaranteed results", "Results are never guaranteed."),  # word order still matters
])
def test_word_forms_do_not_widen_short_words_or_reorder_phrases(term, text):
    r = rule("TERM-06", {"type": "banned_terms", "terms": [term]})
    assert run_deterministic(make_ctx(text, [r])) == []


@pytest.mark.parametrize(("written", "proposed"), [
    ("secret formulas", "methods"),
    ("secretformula", "method"),
    ("s e c r e t f o r m u l a", "method"),
    ("SECRET FORMULA", "METHOD"),
])
def test_preferred_terms_see_through_spacing_and_plurals(written, proposed):
    r = rule("TERM-05", {"type": "preferred_terms", "map": {"secret formula": "method"}})
    [f] = run_deterministic(make_ctx(f"They call it {written} now", [r]))
    assert f.quote == written and f.suggestion.proposed == proposed


@pytest.mark.parametrize(("wrong", "right", "flagged", "clean"), [
    ("e-mail", "email", "Check your e-mails", "Check your email"),
    ("log in", "login", "Two log ins", "Use the login page"),
])
def test_preferred_terms_never_flag_their_own_fix(wrong, right, flagged, clean):
    r = rule("TERM-05", {"type": "preferred_terms", "map": {wrong: right}})
    assert len(run_deterministic(make_ctx(flagged, [r]))) == 1
    assert run_deterministic(make_ctx(clean, [r])) == []


def test_leetspeak_and_glued_terms_are_caught_but_real_numbers_are_not():
    terms = [TermView(1, "Project Lantern", date(2099, 1, 1))]
    body = "Psst, Pr0j3c7 L4n73rn lands soon"
    assert any(f.rule_code == "CONF-LEAK" for f in run_deterministic(make_ctx(body, system_rule_views(), terms=terms)))
    assert "L4n73rn" not in Redactor(["Project Lantern"]).redact(body)
    banned = rule("TERM-06", {"type": "banned_terms", "terms": ["insane deals"]})
    assert [f.quote for f in run_deterministic(make_ctx("Tag it #insanedeals", [banned]))] == ["insanedeals"]
    # A term that really contains digits still matches when the rest is leet.
    tenx = rule("TERM-07", {"type": "preferred_terms", "map": {"10x engineer": "engineer"}})
    for written in ("10x 3ng1n33r", "1 0 x e n g i n e e r", "#10xengineer"):
        found = run_deterministic(make_ctx(f"Hiring our {written} today", [tenx]))
        assert [f.quote for f in found] == [written.lstrip("#")]
    # Digits that are plainly numbers stay numbers.
    plain = "4G and 5G plans for B2B in 2026, rated 4.5 by 10k teams"
    assert run_deterministic(make_ctx(plain, system_rule_views(), terms=terms)) == []
    assert Redactor(["Project Lantern"]).redact(plain) == plain


@pytest.mark.parametrize(("term", "body", "quote"), [
    ("next-gen", "Our word for it was n e x t - g e n.", "n e x t - g e n"),
    ("risk-free", "Honestly this one is a r i s k - f r e e plan", "r i s k - f r e e"),
    ("amazing", "Honestly this one is a m a z i n g today", "a m a z i n g"),
    ("insane", "I think I n s a n e is the word", "I n s a n e"),
])
def test_spaced_terms_with_hyphens_or_after_a_lone_article(term, body, quote):
    r = rule("TERM-08", {"type": "banned_terms", "terms": [term]})
    assert [f.quote for f in run_deterministic(make_ctx(body, [r]))] == [quote]


def test_underscore_letter_spacing_is_still_closed_up():
    r = rule("TERM-09", {"type": "banned_terms", "terms": ["synergy"]})
    assert [f.quote for f in run_deterministic(make_ctx("pure s_y_n_e_r_g_y here", [r]))] == ["s_y_n_e_r_g_y"]


def test_a_stray_letter_before_a_spaced_term_does_not_hide_it():
    r = rule("TERM-10", {"type": "banned_terms", "terms": ["synergy"]})
    assert [f.quote for f in run_deterministic(make_ctx("so x s y n e r g y", [r]))] == ["s y n e r g y"]


@pytest.mark.parametrize(("wrong", "right", "written", "proposed"), [
    ("box", "crate", "boxes", "crates"),
    ("tax", "levy", "taxes", "levies"),
    ("glass", "cup", "glasses", "cups"),
    ("cup", "glass", "cups", "glasses"),
])
def test_plural_fixes_are_inflected_for_the_replacement(wrong, right, written, proposed):
    r = rule("TERM-11", {"type": "preferred_terms", "map": {wrong: right}})
    [f] = run_deterministic(make_ctx(f"Two {written} please", [r]))
    assert f.quote == written and f.suggestion.proposed == proposed


@pytest.mark.parametrize(("term", "prose"), [
    ("Project 3", "the project e-mail"),
    ("Apollo 11", "Apollo ii was a film"),
    ("3x", "ex colleagues"),
])
def test_terms_with_digits_do_not_match_plain_letters(term, prose):
    terms = [TermView(1, term, date(2099, 1, 1))]
    found = run_deterministic(make_ctx(prose, system_rule_views(), terms=terms))
    assert not any(f.rule_code == "CONF-LEAK" for f in found)
