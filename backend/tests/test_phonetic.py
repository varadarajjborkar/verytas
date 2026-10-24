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


def test_spoken_figures_are_written_as_digits():
    # Real Whisper output from evals/speech, Devanagari and romanised, misheard as it came back.
    assert ph.write_figures("सभी उत्पादों पर चालिस प्रतिषवत की छूट") == "सभी उत्पादों पर 40% की छूट"
    assert ph.write_figures("ki madh sirf charso ninyanwe rupe.") == "ki madh sirf ₹499."
    assert ph.write_figures("कोफी सिर्फ चार्सो निन्यानवे रुपे.") == "कोफी सिर्फ ₹499."
    assert ph.write_figures("Madhsir 400 Ninyanwe Rupe.") == "Madhsir ₹499."
    assert ph.write_figures("Zestora par Chalice Pratishat ki chhoot") == "Zestora par 40% ki chhoot"
    assert ph.write_figures("मान्सुन सेल में 25 प्रतिषत तक") == "मान्सुन सेल में 25% तक"
    assert ph.write_figures("four thousand one hundred ninety nine rupees") == "₹4199"
    assert ph.write_figures("₹ 1 lakh rupees") == "₹ 100000"


def test_spoken_figures_leave_everything_else_alone():
    # A number needs its unit right after it, and a guess on both sides is refused.
    for text in ("buy two saris and get one free", "stay on brand at all times", "this offer without limits",
                 "for Chharsha and Nyanve", "team approved the copy", "Flat 40% off", "499 rupees", "Rs 500"):
        assert ph.write_figures(text) == text
    # Words that do not compose are a mishearing: none of them is read ("4100 ninyanve" is not 4199 or 99).
    assert ph.write_figures("madhsir 4100 ninyanve rupe") == "madhsir 4100 ninyanve rupe"
    # Romanised "saat" is 7 or 60 by ear; only the Devanagari spelling tells them apart.
    assert ph.write_figures("saat percent") == "saat percent"
    assert ph.write_figures("सात प्रतिशत") == "7%" and ph.write_figures("साठ प्रतिशत") == "60%"
    assert ph.write_figures("एक सौ पचास प्रतिशत") == "एक सौ पचास प्रतिशत"  # not a percentage


def test_evidence_board_reads_a_figure_said_in_hindi():
    from verytas.checks.crosscheck import figures

    heard = "दिवाली सेल में चालिस परसेंट की बचत"
    assert not figures("s", heard, kind="speech")
    [fig] = figures("s", ph.write_figures(heard), kind="speech")
    assert (fig.key.split(":")[0], fig.value) == ("percent", 40.0)


def test_part_of_a_figure_is_never_written_as_a_smaller_one():
    # Sums, ranges, fractions and decimals are left as said: writing only the tail invents a figure.
    for text in ("nineteen ninety nine rupees", "one hundred and five rupees", "do sau aur paanch rupaye",
                 "twenty twenty five percent", "साढ़े तीन सौ रुपये", "sawa do sau rupaye", "साढ़े सात प्रतिशत",
                 "one point five percent", "200.99 रुपये", "100.5 रुपये", "five to ten percent",
                 "paanch se das percent", "5-25 Pradeshak"):
        assert ph.write_figures(text) == text
    assert ph.write_figures("up to forty percent") == "up to 40%"
    assert ph.write_figures("1" * 5000 + " percent") == "1" * 5000 + " percent"


def test_english_words_that_sound_like_a_unit_are_not_one():
    for text in ("ten reps", "50 reps", "four roofs", "ten ribs", "ten forest", "nine burst", "5 present",
                 "20 percentile"):
        assert ph.write_figures(text) == text
    assert ph.write_figures("In just 99 Rupis") == "In just ₹99"


def test_a_misheard_discount_is_read_only_after_a_hindi_particle():
    from verytas.checks.crosscheck import figures

    def keys(text, kind="speech"):
        return [f.key for f in figures("s", text, kind=kind)]

    for heard in ("40% की बच्चत", "40% की बाचवत", "40% की चुड", "40% tak ki chhoot"):
        assert keys(heard) == ["percent:off"]
    for other in ("30% ke baad", "20% ki baat", "15% ka pata", "40% ka bazaar", "40% ki chat", "40% of the budget"):
        assert keys(other) != ["percent:off"]
    # Devanagari words around a written figure do not hide the English topic after them.
    assert keys("20% पर discount on shoes", "ocr") == ["percent:off"]
    assert keys("40% की छूट।", "ocr") == ["percent:off"]
