"""Phonetic phrase spotting: wrong script and wrong spelling still hit, a different number or name does not."""

from verytas.checks import phonetic as ph


def test_keys_ignore_script_vowels_and_aspiration():
    assert ph.word_key("Zestora") == ph.word_key("ज़ेस्टोरा") == ph.word_key("जेस्तोरा") == ph.word_key("zastura")
    assert ph.word_key("kharido") == ph.word_key("करीदो")


def test_brand_found_in_other_script_and_spelling():
    assert ph.spot("Zestora", "आज जेस्तोरा पर सब कुछ सस्ता")
    assert ph.spot("NovaBrew", "आज ही नोवब्रू की फ्रेश कोफी")
    assert ph.spot("Bluefin Mobiles", "sales bluefin mobiles far")


def test_claim_numbers_cross_languages():
    assert ph.spot("40 percent", "flat 40% off")
    assert ph.spot("40 percent", "चालिस्प्रतिषत की छूट")  # glued number and unit
    assert ph.spot("25 percent", "पच्चीस प्रतिशत तक की बचत")
    assert ph.spot("499 rupees", "कीमत सिर्फ चार सौ निन्यानवे रुपये")
    assert ph.spot("9876543210", "call 976-543-210")  # one digit lost


def test_other_numbers_and_names_do_not_hit():
    assert ph.spot("40 percent", "flat 50% off") is None
    assert ph.spot("1499 rupees", "now only 499 rupees") is None
    assert ph.spot("Zestora", "सिर्फ हमारे स्टोर पर") is None
    assert ph.spot("Project Falcon", "visit our store this weekend") is None


def test_short_keys_need_a_whole_token():
    # "Zestora" is four consonants: it must be a token of its own, not a stretch inside other words
    assert ph.spot("Zestora", "ज़ेस्टोरा") is not None
    assert ph.spot("Zestora", "कसर तो रहने दो") is None


def test_empty_inputs():
    assert ph.spot("Zestora", "") is None
    assert ph.spot("", "anything") is None


def test_locate_points_at_the_words_heard():
    text = "आज की खबर: प्रोजेक्ट फाल्कन अगले हफ्ते आ रहा है।"
    a, b, s = ph.locate("Project Falcon", text)
    assert text[a:b] == "प्रोजेक्ट फाल्कन" and s.score > 0.5
    assert ph.locate("Project Falcon", "visit our store this weekend") is None


def test_spoken_codename_is_flagged_by_sound_only_in_speech():
    from datetime import date

    from verytas.checks.base import CheckContext, RuleView, TermView
    from verytas.checks.deterministic import confidential_terms
    from verytas.ingest.segment import segment

    rule = RuleView(id=1, code="CONF-LEAK", category="confidentiality", kind="deterministic", severity="blocker",
                    title="No confidential terms", text="No confidential terms.",
                    pattern={"type": "confidential_terms"})
    text = "Big news, project falkan launches next week"
    term = TermView(id=1, term="Project Falcon", embargo_until=None)

    def found(spoken: bool):
        ctx = CheckContext(body=text, units=segment(text), rules=[rule], terms=[term], spoken=spoken,
                           today=date(2026, 10, 24))
        return list(confidential_terms(ctx, rule))

    assert found(False) == []  # written text: only an exact (folded) match counts
    hit = found(True)
    assert len(hit) == 1 and hit[0].quote == "project falkan" and hit[0].confidence < 0.85
    # The speaker said something else: the finding must not hand them the codename.
    assert "Falcon" not in hit[0].title + hit[0].explanation


def test_short_or_unit_like_terms_are_not_looked_for_by_sound():
    # K-T, N-V and a key equal to a unit word would turn up in ordinary speech ("get", "new", "a day").
    for term in ("Kite", "Nova", "Atlas", "Apex", "Titan", "Mint", "Dino"):
        assert not ph.soundable(term), term
    assert ph.soundable("Project Falcon") and ph.soundable("Zestora Prime")
