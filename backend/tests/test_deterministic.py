import base64
import io
from datetime import date

from PIL import Image

from tests.helpers import make_ctx, rule, system_rule_views
from verytas.checks.base import TermView
from verytas.checks.deterministic import run_deterministic


def _codes(findings):
    return [f.rule_code for f in findings]


def test_preferred_terms_suggest_replacement_and_keep_case():
    r = rule("TERM-01", {"type": "preferred_terms", "map": {"e-mail": "email", "sign-in": "sign in"}})
    body = "E-mail us to sign-in today."
    findings = run_deterministic(make_ctx(body, [r]))
    assert [f.suggestion.proposed for f in findings] == ["Email", "sign in"]
    for f in findings:
        assert body[f.span_start:f.span_end] == f.quote


def test_banned_terms_respect_word_boundaries():
    r = rule("TERM-02", {"type": "banned_terms", "terms": ["synergy"]})
    findings = run_deterministic(make_ctx("Synergy matters. Synergyst is fine. synergy-driven too.", [r]))
    assert [f.quote for f in findings] == ["Synergy"]


def test_casing_flags_only_wrong_case():
    r = rule("TERM-03", {"type": "casing", "terms": ["GitHub", "Verytas"]})
    findings = run_deterministic(make_ctx("Push to github, then open Verytas and VERYTAS.", [r]))
    assert [(f.quote, f.suggestion.proposed) for f in findings] == [("github", "GitHub"), ("VERYTAS", "Verytas")]


def test_casing_leaves_handles_urls_and_addresses_alone():
    r = rule("TERM-03", {"type": "casing", "terms": ["Kitepath"]})
    for fine in ("Follow @kitepath for more.", "Join at kitepath.in/learn today.", "Visit www.kitepath.com.",
                 "Write to hello@kitepath.in.", "See https://kitepath.in", "Find us: @kitepath"):
        assert run_deterministic(make_ctx(fine, [r])) == [], fine
    # The brand name in running text is still held to its casing, including at the end of a sentence.
    assert [f.quote for f in run_deterministic(make_ctx("We love kitepath. KITEPATH.Join now.", [r]))] \
        == ["kitepath", "KITEPATH"]


def test_confidential_terms_respect_embargo():
    rules = system_rule_views()
    terms = [TermView(1, "Project Lumen", date(2026, 12, 1)), TermView(2, "Old Codename", date(2026, 1, 1))]
    findings = run_deterministic(make_ctx("Project Lumen ships soon. Old Codename is public.", rules, terms=terms))
    conf = [f for f in findings if f.rule_code == "CONF-LEAK"]
    assert [f.quote for f in conf] == ["Project Lumen"]
    assert "2026-12-01" in conf[0].explanation


def test_alt_text_missing_and_placeholder():
    attachments = {"images": [
        {"id": "cover", "alt": ""},
        {"id": "inline", "alt": "photo"},
        {"id": "ok", "alt": "Team celebrating the launch on stage"},
        {"id": "divider", "decorative": True},
    ]}
    findings = [f for f in run_deterministic(make_ctx("Body.", system_rule_views(), attachments=attachments))
                if f.rule_code == "A11Y-ALT"]
    assert [f.unit_id for f in findings] == ["img:cover", "img:inline"]


def test_contrast_uses_large_text_threshold():
    attachments = {"colors": [
        {"fg": "#777777", "bg": "#ffffff", "where": "body copy"},
        {"fg": "#777777", "bg": "#ffffff", "where": "headline", "large": True},
    ]}
    findings = [f for f in run_deterministic(make_ctx("x", system_rule_views(), attachments=attachments))
                if f.rule_code == "A11Y-CONTRAST"]
    assert len(findings) == 1 and "body copy" in findings[0].title


def test_hashtags_caps_and_links():
    body = "Big news #brandgovernance and #BrandGovernance. THIS IS VERY LOUD. Read [click here](https://x.y)."
    codes = _codes(run_deterministic(make_ctx(body, system_rule_views())))
    assert codes.count("A11Y-HASHTAG") == 1
    assert codes.count("A11Y-CAPS") == 1
    assert codes.count("A11Y-LINKTEXT") == 1


def test_readability_flags_dense_paragraph_only():
    dense = ("Notwithstanding the aforementioned considerations, organisational stakeholders "
             "must systematically operationalise comprehensive governance methodologies, thereby "
             "institutionalising multidimensional accountability frameworks across interdependent "
             "departmental hierarchies and heterogeneous communication infrastructures.")
    simple = "We help teams ship posts that sound like them. It is quick. It is clear. You will like it a lot."
    findings = [f for f in run_deterministic(make_ctx(dense + "\n\n" + simple, system_rule_views()))
                if f.rule_code == "A11Y-READ"]
    assert [f.unit_id for f in findings] == ["p1"]


def _png(colour_a, colour_b) -> str:
    im = Image.new("RGB", (40, 40), colour_a)
    im.paste(Image.new("RGB", (40, 16), colour_b), (0, 24))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_palette_flags_off_brand_colour_but_allows_neutrals():
    r = rule("VIS-01", {"type": "palette", "colors": ["#0A84FF"], "max_delta_e": 12}, category="visual")
    off_brand = {"images": [{"id": "cover", "alt": "x", "data_base64": _png((10, 132, 255), (230, 40, 40))}]}
    on_brand = {"images": [{"id": "cover", "alt": "x", "data_base64": _png((10, 132, 255), (255, 255, 255))}]}
    assert len(run_deterministic(make_ctx("x", [r], attachments=off_brand))) == 1
    assert run_deterministic(make_ctx("x", [r], attachments=on_brand)) == []


def test_bad_image_data_is_reported_not_fatal_and_not_passed():
    r = rule("VIS-01", {"type": "palette", "colors": ["#0A84FF"]}, category="visual")
    att = {"images": [{"id": "x", "alt": "x", "data_base64": "not-base64!!"}]}
    [f] = run_deterministic(make_ctx("x", [r], attachments=att))
    assert f.title.startswith("Could not analyse image x")


def test_decompression_bomb_is_refused():
    im = Image.new("1", (12_000, 12_000))  # 144M pixels, tiny once compressed
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    r = rule("VIS-01", {"type": "palette", "colors": ["#0A84FF"]}, category="visual")
    att = {"images": [{"id": "bomb", "alt": "x", "data_base64": base64.b64encode(buf.getvalue()).decode()}]}
    [f] = run_deterministic(make_ctx("x", [r], attachments=att))
    assert "Could not analyse" in f.title


def test_unparseable_colours_are_reported():
    att = {"colors": [{"fg": "red", "bg": "#ffffff", "where": "hero"}]}
    findings = [f for f in run_deterministic(make_ctx("x", system_rule_views(), attachments=att))
                if f.rule_code == "A11Y-CONTRAST"]
    assert findings and findings[0].title == "Could not check contrast in hero"


def test_one_broken_rule_does_not_sink_the_others():
    broken = rule("TERM-X", {"type": "preferred_terms", "map": ["not", "a", "dict"]})
    good = rule("TERM-01", {"type": "banned_terms", "terms": ["synergy"]}, rid=101)
    problems = []
    findings = run_deterministic(make_ctx("Synergy wins.", [broken, good]), problems)
    assert [f.rule_code for f in findings] == ["TERM-01"]
    assert problems == [("TERM-X", "terminology", "AttributeError")]


def test_syllable_heuristic_on_common_words():
    from verytas.checks.readability import count_syllables

    cases = {"cat": 1, "make": 1, "table": 2, "governance": 3, "named": 1, "organisation": 5, "readability": 5}
    assert {w: count_syllables(w) for w in cases} == cases
