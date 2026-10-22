from verytas.ingest.segment import segment


def test_offsets_index_the_original_body():
    body = "Hello world. This is Verytas!\n\n  Second para, e.g. with an abbreviation. Done?"
    for u in segment(body):
        assert body[u.start:u.end] == u.text


def test_paragraphs_and_sentences():
    body = "One. Two!\n\nThree? \"Four.\" Five"
    units = segment(body)
    paras = [u.text for u in units if u.kind == "paragraph"]
    sents = [u.text for u in units if u.kind == "sentence"]
    assert paras == ["One. Two!", "Three? \"Four.\" Five"]
    assert sents == ["One.", "Two!", "Three?", "\"Four.\"", "Five"]


def test_abbreviations_do_not_split():
    sents = [u.text for u in segment("Use tools e.g. Vale for linting. Then ship.") if u.kind == "sentence"]
    assert sents == ["Use tools e.g. Vale for linting.", "Then ship."]


def test_empty_body_has_no_units():
    assert segment("   \n\n ") == []
