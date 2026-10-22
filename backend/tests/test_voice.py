"""Tone and topic drift, measured against the brand's own published work, and each creator's track record."""

from __future__ import annotations

from tests.test_api_flow import _auth
from tests.test_api_flow import world as world  # noqa: F401, the fixture is used by name
from verytas.checks.base import CheckContext, RuleView
from verytas.checks.voice import BrandProfile, build_profile, domains_in, tone_hits, tone_shift, topic_drift
from verytas.ingest.segment import segment

PUBLISHED = [
    "Learn Python in six weeks, one evening at a time. Real exercises and friendly mentors.",
    "Twenty new courses landed this month, from Excel to Kannada for beginners.",
    "Meet Ananya, who mentors 40 learners a week in our design track.",
    "Thank you for rating us 4.7 out of 5. Every review helps us teach better.",
]
TONE = RuleView(1, "TONE-SHIFT", "tone", "deterministic", "should", "Voice", "Stay in the brand's voice.")
TOPIC = RuleView(2, "MSG-OFF-TOPIC", "messaging", "deterministic", "should", "Topics", "Stay on topic.")


def _run(check, rule, body, profile: BrandProfile | None):
    ctx = CheckContext(body=body, units=segment(body), rules=[rule], profile=profile)
    return list(check(ctx, rule, profile))


def test_a_tone_that_turns_partway_is_named_and_quoted():
    profile = build_profile(PUBLISHED)
    body = ("Our SQL course starts Monday, with real projects and mentors.\n\n"
            "Honestly, people still stuck on spreadsheets are idiots and losers.")
    [f] = _run(tone_shift, TONE, body, profile)
    assert f.title == "Tone turns hostile partway through"
    assert f.quote == "idiots and losers" and f.unit_id == "p2"
    assert "4 approved or published pieces" in f.explanation and "'idiots', 'losers'" in f.explanation


def test_each_tone_dimension_and_the_calm_controls():
    profile = build_profile(PUBLISHED)
    cases = {
        "lol ngl this course is lowkey great bro": "slangy",
        "Yeah right, as if other apps teach anything.": "sarcastic",
        "Please be advised that, pursuant to the aforementioned plan, stakeholders shall leverage it.": "stiff",
        "Hurry, offer ends soon!!! Cheapest courses! Join now!": "hyped",
    }
    for body, dim in cases.items():
        found = _run(tone_shift, TONE, body, profile)
        assert [f.title for f in found] == [f"Off the brand's voice: {_say(dim)}"], body
    # Stems quote whole words as written, not "aforemention".
    stiff = _run(tone_shift, TONE, "Please be advised that the aforementioned stakeholders agree.", profile)[0]
    assert stiff.quote.startswith("Please be advised") and stiff.quote.endswith("stakeholders")
    for calm in ["This festive season, learn something you'll keep. Pick any of 340 courses tonight.",
                 "We hate to see learners stuck, so mentors reply within a day. Wake up early and practise!"]:
        assert _run(tone_shift, TONE, calm, profile) == [], calm


def _say(dim):
    return {"slangy": "slangy and casual", "stiff": "stiff and corporate"}.get(dim, dim)


def test_a_brand_that_writes_casually_may_keep_doing_so():
    casual = build_profile([p + " lol, gonna be fun bro" for p in PUBLISHED])
    assert "slangy" in casual.tones
    assert _run(tone_shift, TONE, "lol ngl this course is gonna be great bro", casual) == []
    # And an admin can allow a dimension outright.
    allowed = RuleView(1, "TONE-SHIFT", "tone", "deterministic", "should", "Voice", "x", pattern={"allow": ["hyped"]})
    assert _run(tone_shift, allowed, "Epic! Insane! The ultimate course!", None) == []


def test_drifting_into_a_domain_the_brand_never_covers():
    profile = build_profile(PUBLISHED)
    body = ("Join our design track this week: real briefs and weekly critiques.\n\n"
            "Also, the election was rigged and the minister must resign.")
    [f] = _run(topic_drift, TOPIC, body, profile)
    assert f.title == "Drifts off topic into politics" and f.quote.startswith("election")
    assert "covers politics" in f.explanation and "'election'" in f.explanation
    [whole] = _run(topic_drift, TOPIC, "Bitcoin is going to the moon, buy crypto now.", profile)
    assert whole.title == "Off the brand's topics: trading tips"


def test_innocent_words_are_not_a_topic():
    # The words an education brand uses that live next to risky domains.
    for body in ["Invest an hour a day and the returns compound. Build a portfolio you can show.",
                 "Prep for government exams against the odds, with a launch party on Friday.",
                 "Festive greetings from all of us. Happy learning this Diwali!"]:
        assert domains_in(body) == {}, body
        assert _run(topic_drift, TOPIC, body, build_profile(PUBLISHED)) == [], body


def test_a_brand_whose_business_is_the_domain_is_not_off_topic():
    trading = build_profile(["Learn intraday trading basics with our forex course.",
                             "Our crypto course explains bitcoin wallets safely.", *PUBLISHED])
    assert "trading tips" in trading.domains
    assert _run(topic_drift, TOPIC, "Bitcoin and crypto basics, in our new course.", trading) == []


def test_tone_hits_count_shouted_punctuation():
    # Two runs of "!!", and every sentence shouting on top.
    assert tone_hits("Now!!! Today!!")["hyped"] == ["!!!", "!", "!!", "!"]
    # One exclamation in two sentences is enthusiasm, not hype: below the three hits that make the dimension.
    assert len(tone_hits("Join today. It starts Monday!")["hyped"]) < 3
    assert len(tone_hits("The cheapest courses! We have 2 million learners. Hurry, ends soon!!! #Sale")["hyped"]) >= 3


def test_reviews_flag_drift_and_the_brand_team_sees_each_creators_line(client, world):
    creator, reviewer, approver = _auth(world["creator"]), _auth(world["reviewer"]), _auth(world["approver"])

    def post(body, title):
        made = client.post("/contents?wait=true", headers=creator,
                           json={"title": title, "channel": "linkedin", "body": body})
        assert made.status_code == 201, made.text
        return made.json()

    post("Our SQL course starts Monday, with real projects and friendly mentors.", "Calm")
    drift = post("Our SQL course starts Monday.\n\nAlso, the election was rigged and the minister must resign.",
                 "Drift")
    rant = post("Our SQL course starts Monday.\n\nAnyone still on spreadsheets is an idiot, honestly.", "Rant")
    drift_findings = client.get(f"/reviews/{drift['review_id']}", headers=creator).json()["findings"]
    off = next(f for f in drift_findings if f["title"] == "Drifts off topic into politics")
    assert off["citations"][0]["label"].startswith("MSG-OFF-TOPIC") and off["level"] == "warning"
    rant_findings = client.get(f"/reviews/{rant['review_id']}", headers=creator).json()["findings"]
    assert any(f["title"] == "Tone turns hostile partway through" for f in rant_findings)

    # A dismissed finding is the creator being right, so it doesn't count against them.
    tone = next(f for f in rant_findings if f["title"] == "Tone turns hostile partway through")
    assert client.post(f"/findings/{tone['id']}/decision", headers=approver,
                       json={"action": "rejected", "reason_code": "false_positive",
                             "reason_text": "Quoting a learner"}).status_code in (200, 201)

    me = client.get("/me", headers=creator).json()
    roster = client.get("/insights/creators", headers=reviewer).json()
    assert [r["name"] for r in roster] == ["Creator"] and roster[0]["pieces"] == 3
    line = client.get(f"/insights/creators/{me['id']}", headers=reviewer).json()
    assert [p["title"] for p in line["points"]] == ["Calm", "Drift", "Rant"]
    by_title = {p["title"]: p for p in line["points"]}
    assert by_title["Calm"]["distance"] == 0 and by_title["Calm"]["summary"].startswith("On brand as sent")
    assert by_title["Drift"]["distance"] > 0 and by_title["Drift"]["drift"] == ["messaging"]
    assert "Drifts off topic into politics" in by_title["Drift"]["summary"]
    assert "tone" not in by_title["Rant"]["drift"]
    assert line["stats"]["reviewed"] == 3 and line["stats"]["on_brand_as_sent"] >= 1

    # Creators don't see each other's lines, or the roster; staff aren't creators.
    assert client.get("/insights/creators", headers=creator).status_code == 403
    assert client.get(f"/insights/creators/{me['id']}", headers=creator).status_code == 403
    staff = client.get("/me", headers=reviewer).json()
    assert client.get(f"/insights/creators/{staff['id']}", headers=reviewer).status_code == 404


# --- any language -----------------------------------------------------------------------------------

def test_the_language_of_a_piece_is_recognised_including_mixes():
    from verytas.ingest.language import detect

    cases = {
        "This festive season, learn something you'll keep. Pick any of 340 courses tonight.": "en",
        "Is festive season, padhai bhi celebrate karo! Naya course shuru karo aaj raat.": "hinglish",
        "इस त्योहार पर कुछ नया सीखें। आज रात से शुरू करें।": "hi",
        "Aprende Python en seis semanas, una tarde a la vez. Ejercicios reales y mentores.": "es",
        "Apprenez Python en six semaines, un soir à la fois. Des exercices concrets.": "fr",
        "Lerne Python in sechs Wochen, einen Abend nach dem anderen. Echte Übungen mit Mentoren.": "de",
        "Aprenda Python em seis semanas, uma noite de cada vez. Exercícios reais e mentores.": "pt",
        "学习编程很有趣，每天进步一点点。": "zh",
        "Thank you!": "und",
    }
    for text, code in cases.items():
        assert detect(text).code == code, text
    assert "en" in detect("Learn Python in six weeks. இது ஒரு நல்ல பாடநெறி மற்றும் நீங்கள் கற்றுக்கொள்ளலாம்").mixed
    # Hybrids: named as the blend, or as the main language with the other alongside.
    assert detect("Ye course mast hai, but jo nahi samjha woh idiot hai yaar").code == "hinglish"
    assert detect("Indha course semma, but those who skip it are idiots, romba nalla mentors irukku").code == "tanglish"
    spanglish = detect("This course is so good, pero no lo entiendo, the mentors son increíbles y muy amables")
    assert spanglish.code == "en" and spanglish.mixed == ("es",) and spanglish.name == "English with Spanish"
    # Shared little words ("a", "de") don't make a mix.
    assert detect("Meet Ananya, who mentors 40 learners a week in our design track.").mixed == ()


def test_hybrid_posts_are_checked_in_every_language_they_use():
    profile = build_profile(PUBLISHED)
    for body in ["Ye course mast hai.\n\nBut jo nahi samjha woh idiot hai yaar.",
                 "Course बहुत अच्छा है।\n\nBut honestly जो नहीं समझा वह बेवकूफ है।",
                 "The course starts Monday.\n\nY el que no lo entienda es un idiota, honestly."]:
        assert [f.title for f in _run(tone_shift, TONE, body, profile)] == ["Tone turns hostile partway through"]
    body = "Our new curso starts Monday.\n\nPero the elecciones are rigged and the ministro lies."
    [f] = _run(topic_drift, TOPIC, body, profile)
    assert f.title == "Drifts off topic into politics"


def test_drift_is_caught_in_other_languages_and_scripts():
    profile = build_profile(PUBLISHED)
    hostile = {
        "Nuestro curso empieza el lunes.\n\nY quien no lo entienda es un idiota.": "idiota",
        "Naya course aaj se shuru.\n\nJo nahi samjha woh bewakoof hai.": "bewakoof",
        "नया कोर्स आज से शुरू।\n\nजो नहीं समझा वह बेवकूफ है।": "बेवकूफ",
        "Unser Kurs beginnt am Montag.\n\nWer das nicht versteht, ist ein Vollidiot.": "Vollidiot",
    }
    for body, quote in hostile.items():
        [f] = _run(tone_shift, TONE, body, profile)
        assert f.title == "Tone turns hostile partway through" and f.quote == quote, body
    off = {
        "Nuestro curso empieza el lunes.\n\nLas elecciones fueron un fraude y el ministro mintió.": "politics",
        "Naya course aaj se shuru.\n\nIs chunav mein sab neta jhoothe hain.": "politics",
        "नया कोर्स आज से शुरू।\n\nइस चुनाव में वोट ज़रूर दें।": "politics",
        "Notre cours commence lundi.\n\nAchetez des cryptomonnaies maintenant.": "trading tips",
        "O curso começa segunda.\n\nFaça suas apostas esportivas no jogo de hoje.": "betting",
    }
    for body, domain in off.items():
        [f] = _run(topic_drift, TOPIC, body, profile)
        assert f.title == f"Drifts off topic into {domain}", body
    # A bilingual post is not a wandering one, and German "Wahl" (choice) is not an election.
    bilingual = ("Learn Python in six weeks with real exercises, friendly mentors and a project you can show.\n\n"
                 "Aprende Python en seis semanas con ejercicios reales, mentores amables y un proyecto propio "
                 "que puedes mostrar a cualquiera.")
    assert _run(topic_drift, TOPIC, bilingual, build_profile(PUBLISHED * 2)) == []
    assert _run(topic_drift, TOPIC, "Ihre Wahl: Python oder Excel. Beides lernen Sie bei uns.", profile) == []


def test_english_only_checks_stay_quiet_on_other_languages_and_the_review_says_so(client, world):
    creator = _auth(world["creator"])
    spanish = ("Nuestro curso de ciencia de datos combina proyectos reales, revisiones de mentores, ejercicios "
               "semanales y un portafolio que puedes mostrar a cualquier empresa que quieras impresionar pronto.")
    made = client.post("/contents?wait=true", headers=creator,
                       json={"title": "ES", "channel": "linkedin", "body": spanish}).json()
    review = client.get(f"/reviews/{made['review_id']}", headers=creator).json()
    assert not [f for f in review["findings"] if f["title"].startswith("Reading grade")]
    assert review["coverage"]["language"]["code"] == "es"
    assert any(n.startswith("Written in Spanish") for n in review["coverage"]["notes"])


# --- errcheck gen 11 regressions ----------------------------------------------------------------------

def test_ordinary_copy_in_any_language_is_not_a_tone_or_a_topic():
    profile = build_profile([])  # a new workspace: nothing learned, the strictest case
    calm = [
        "Thanks a lot for joining! It feels as if the year flew by.",
        "Damn good coffee and garbage collection, explained. Take out the trash, then study.",
        "No dumb questions here. April fools aside, the value is ridiculous.",
        "Ya disponible. Disfruta sus beneficios con nuestro curso.",
        "Separe o lixo e a basura; o burro da fazenda e Johnny Depp.",
        "Vote for your favourite course. Voting closes Friday.",
        "La elección perfecta para aprender Python.",
        "We're betting big on mentors. A family affair, dating back to 1998.",
    ]
    for body in calm:
        assert _run(tone_shift, TONE, body, profile) == [], body
        assert _run(topic_drift, TOPIC, body, profile) == [], body


def test_quotes_are_whole_words_at_the_right_offsets():
    profile = build_profile([])
    # A short trigger never matches inside another word ("u" in "us"), and the quote runs first to last trigger.
    [f] = _run(tone_shift, TONE, "Join us today.\n\nomg ur gonna love it", profile)
    assert f.quote == "omg ur gonna"
    # Dotted capital I lowercases to two characters; offsets must not shift.
    body = "İstanbul learners welcome.\n\nAnyone who skips this is an idiot."
    [f] = _run(tone_shift, TONE, body, profile)
    assert body[f.span_start:f.span_end] == f.quote == "idiot"
    # NFD input (decomposed accents) matches like NFC and quotes what was typed.
    import unicodedata
    nfd = unicodedata.normalize("NFD", "Nuestro curso.\n\nQuien no lo entienda es estúpido.")
    [f] = _run(tone_shift, TONE, nfd, profile)
    assert nfd[f.span_start:f.span_end] == f.quote and unicodedata.normalize("NFC", f.quote) == "estúpido"
    # The danda ends a Devanagari word.
    assert domains_in("यह चुनाव। अगला") == {"politics": ["चुनाव"]}
    # Plural "-ies" words meet their lexicon entry, and explanations quote the writer's words, not stems.
    [g] = _run(topic_drift, TOPIC, "Our course starts Monday.\n\nCelebrity gossip and Bollywood scandals!", profile)
    assert "'gossip'" in g.explanation and "scandals" in g.explanation


def test_english_is_not_mistaken_for_portuguese_or_hinglish():
    from verytas.ingest.language import detect

    for text in ["As a learner, do as much as you can: a little a day adds up to a lot.",
                 "Send it to me and I will do it as soon as I can.",
                 "Do you want a mentor? Ask us, as we do this every day."]:
        assert detect(text).code == "en", text
    assert detect("Hoy empieza nuestro curso, a las siete.").code == "es"


def test_a_creators_own_rejection_does_not_clean_their_record(client, world):
    creator, reviewer = _auth(world["creator"]), _auth(world["reviewer"])
    made = client.post("/contents?wait=true", headers=creator, json={
        "title": "Rant", "channel": "linkedin",
        "body": "Our SQL course starts Monday.\n\nAnyone still on spreadsheets is an idiot, honestly."}).json()
    tone = next(f for f in client.get(f"/reviews/{made['review_id']}", headers=creator).json()["findings"]
                if f["title"] == "Tone turns hostile partway through")
    assert client.post(f"/findings/{tone['id']}/decision", headers=creator,
                       json={"action": "rejected", "reason_code": "false_positive",
                             "reason_text": "It's fine"}).status_code in (200, 201)
    me = client.get("/me", headers=creator).json()
    [point] = client.get(f"/insights/creators/{me['id']}", headers=reviewer).json()["points"]
    assert point["distance"] > 0 and point["drift"] == ["tone"]


def test_second_review_round_false_alarms():
    profile = build_profile([])
    for body in ["Nuestra apuesta por la calidad no cambia.", "A nossa aposta é na qualidade.",
                 "Read the artist's manifesto, then join the protest against boring slides.",
                 "Big news! Our design track opens Monday. Come see it! Bring a friend! It starts at nine."]:
        assert _run(tone_shift, TONE, body, profile) == [], body
        assert _run(topic_drift, TOPIC, body, profile) == [], body
    # Pressure plus shouting is hype; a curly apostrophe is the same word as a straight one.
    assert [f.title for f in _run(tone_shift, TONE, "Hurry, offer ends soon!!! Join now.", profile)] == [
        "Off the brand's voice: hyped"]
    assert len(tone_hits("y’all gonna love it")["slangy"]) == 2
