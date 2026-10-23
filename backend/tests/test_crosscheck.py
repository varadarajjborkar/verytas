"""The evidence board's cross-check: figures and names compared between the parts of one post."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from tests.helpers import make_ctx, system_rule_views
from tests.media_fixtures import b64, caption_video, png, text_image
from tests.test_media import _auth, _submit
from verytas.checks.crosscheck import agree, compare_pools, compare_timed, figures
from verytas.checks.likeness import PersonView
from verytas.prism.board import Board, Evidence, person_findings


def _keys(text: str) -> list[tuple[str, float, str | None]]:
    return [(f.key, f.value, f.bound) for f in figures("s", text)]


def test_figures_carry_what_they_are_about():
    assert _keys("Flat 50% off on all courses, now ₹499/month") == [("percent:off", 50, None),
                                                                  ("price:INR:month", 499, None)]
    assert _keys("Up to 30% OFF") == [("percent:off", 30, "max")]
    assert _keys("Save 20% today") == [("percent:off", 20, None)]
    assert _keys("Join 10,000+ students") == [("count:student", 10_000, "min")]
    assert _keys("999/- per year") == [("price:INR:year", 999, None)]
    assert _keys("₹2.5 lakh scholarship") == [("price:INR", 250_000, None)]
    # A time span is keyed by what it measures: a 7-day trial is not a 30-day guarantee.
    assert _keys("7-day free trial and 30 days money-back guarantee") == [
        ("count:day:trial", 7, None), ("count:day:guarantee", 30, None)]
    # Clock times, years and phone-length numbers are not figures to compare.
    assert _keys("Live at 10 am, since 2019, call 9876543210 now") == []


def test_bounds_decide_whether_two_figures_can_both_be_true():
    up_to, exact, other = (figures("s", t)[0] for t in ("up to 50% off", "30% off", "50% off"))
    assert agree(up_to, exact) and not agree(exact, other)
    plus, small = figures("s", "10,000+ learners")[0], figures("s", "12,000 learners")[0]
    assert agree(plus, small)
    assert agree(figures("s", "₹4,999")[0], figures("s", "Rs 4999.00")[0])


def test_what_a_price_is_for_keeps_discounts_prizes_and_thresholds_apart_from_the_price():
    # errcheck 351: each pair below was a conflict, at blocker strength on a clear poster.
    for caption, poster in (("Get Rs 500 off", "Course fee Rs 1,999"), ("Win a prize worth ₹10,000", "Entry ₹499"),
                            ("Free delivery above Rs 999", "Rs 499 only")):
        assert compare_pools(figures("body", caption), figures("i", poster, kind="ocr")) == [], caption
    assert len(compare_pools(figures("body", "Get Rs 500 off"), figures("i", "Rs 300 OFF", kind="ocr"))) == 1


def test_a_range_is_one_figure_spanning_its_ends():
    assert [(f.value, f.low) for f in figures("s", "Get 20-30% off")] == [(30, 20)]
    assert [(f.value, f.low) for f in figures("s", "Plans ₹499-999")] == [(999, 499)]
    assert compare_pools(figures("body", "Get 20-30% off"), figures("i", "25% OFF")) == []
    assert len(compare_pools(figures("body", "Get 20-30% off"), figures("i", "40% OFF"))) == 1


def test_a_full_stop_does_not_hide_what_a_figure_is_about():
    assert _keys("Get 30% off.") == [("percent:off", 30, None)]
    assert _keys("50% off. 12 months") == [("percent:off", 50, None)]


def test_several_figures_for_one_thing_are_a_price_list_not_a_contradiction():
    body = figures("body", "Plans from just ₹299/month")
    table = figures("img:p:ocr", "Basic ₹499/month\nPro ₹999/month")
    assert compare_pools(body, table) == []
    assert len(compare_pools(figures("body", "Only ₹299/month"), figures("img:p:ocr", "₹499/month"))) == 1


def test_timed_figures_are_compared_only_near_the_same_moment():
    shown = figures("vid:v:captions", "Only ₹999\nNew batch", [(0, 9, 0.0, 3.0), (10, 19, 20.0, 23.0)])
    said_now = figures("vid:v:speech", "just 499 rupees", [(0, 15, 1.0, 3.0)])
    said_later = figures("vid:v:speech", "just 499 rupees", [(0, 15, 30.0, 32.0)])
    [c] = compare_timed(shown, said_now)
    assert c.anchor.quote == "₹999" and c.other.quote == "499 rupees"
    assert compare_timed(shown, said_later) == []


def test_a_price_tag_that_lost_its_rupee_sign_is_read_as_the_captions_price():
    # Local OCR often drops the rupee sign: "₹3,499" on the poster comes back as "3,499".
    caption = figures("body", "Get the pass for ₹2,999.")
    [c] = compare_pools(caption, figures("i", "ANNUAL PASS\n3,499", kind="ocr"))
    assert c.other.inferred and c.other.quote == "3,499"
    assert compare_pools(caption, figures("i", "ANNUAL PASS\n2,999", kind="ocr")) == []
    # Only a lone amount on a line, only when the caption names one price, and never in typed text.
    assert compare_pools(figures("body", "Pass ₹2,999, kit ₹499."), figures("i", "3,499", kind="ocr")) == []
    assert figures("body", "3,499", kind="body") == []


def test_speech_that_hears_off_as_of_is_still_a_discount():
    assert _keys_of("Get 40% of today only.", "speech") == [("percent:off", 40)]
    assert _keys_of("50% of students passed", "speech") == [("percent:student", 50)]
    assert _keys_of("Get 40% of today only.", "body") == []  # typed "of" is taken as written: no topic
    # A share said aloud stays a share.
    assert _keys_of("60% of all customers renew", "speech") == [("percent:customer", 60)]


def _keys_of(text: str, kind: str) -> list[tuple[str, float]]:
    return [(f.key, f.value) for f in figures("s", text, kind=kind)]


# --- through a real review ------------------------------------------------------------------------

@pytest.fixture
def world(client):
    admin = client.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                            "admin_name": "Ada"}).json()["token"]
    creator = client.post("/users", headers=_auth(admin),
                          json={"email": "c@acme.io", "name": "c", "role": "creator"}).json()["token"]
    return {"admin": admin, "creator": creator}


def _mismatches(review):
    return [f for f in review["findings"] if f["checker"] == "crosscheck"]


def test_the_caption_and_the_poster_giving_different_discounts_is_one_finding_citing_both(client, world):
    poster = b64(png(text_image(["30% OFF ALL COURSES", "This week only"])))
    _, review = _submit(client, world, body="Flat 50% off all courses this week. Enrol now.",
                        attachments={"images": [{"id": "poster", "alt": "Sale poster with the discount",
                                                 "data_base64": poster}]})
    [f] = _mismatches(review)
    assert f["source"] == "body" and f["quote"] == "50% off" and f["level"] == "blocker"
    assert f["title"] == "The text says 50% off, the image says 30% OFF"
    [ev] = f["locator"]["evidence"]
    assert ev["source"] == "img:poster:ocr" and ev["quote"] == "30% OFF" and len(ev["box"]) == 4
    assert review["coverage"]["evidence"]["figure"] >= 2
    assert "crosscheck" in [a["role"] for a in review["coverage"]["agents"]]


def test_an_up_to_offer_and_a_matching_poster_raise_nothing(client, world):
    poster = b64(png(text_image(["30% OFF ALL COURSES"])))
    _, review = _submit(client, world, body="Up to 50% off courses this week.",
                        attachments={"images": [{"id": "poster", "alt": "Sale poster with the discount",
                                                 "data_base64": poster}]})
    assert _mismatches(review) == []


def test_the_voice_over_and_the_screen_giving_different_prices(client, world, monkeypatch):
    from verytas.media import video
    from verytas.media.video import Cue

    monkeypatch.setattr(video, "transcribe", lambda pcm, model, vocabulary=None: (
        [Cue(1.0, 3.0, "and the whole course is just 499 rupees")], "en", 0.95))
    clip = caption_video([(0, 3, "WHOLE COURSE RS 999"), (3, 6, "Link in bio")])
    blob = client.post("/media", headers=_auth(world["creator"]),
                       files={"file": ("reel.mp4", clip, "video/mp4")}).json()
    _, review = _submit(client, world, body="Our new course is out",
                        attachments={"videos": [{"id": "reel", "blob_id": blob["id"]}]},
                        notes={"brief": "A reel about the new course; I speak over it."})
    [f] = _mismatches(review)
    assert f["source"] == "vid:reel:captions" and f["locator"]["time"][0] < 3
    assert f["locator"]["evidence"][0]["source"] == "vid:reel:speech"
    # Heard, not read: speech recognition can mishear a number, so this asks for a look, not a block.
    assert f["level"] == "warning"


# --- people --------------------------------------------------------------------------------------

def _person_run(body: str, seen: list[str], photos=(1, 2)):
    people = [PersonView(1, "Riya Sen", "ambassador", date(2026, 1, 1), aliases=("Riya",)),
              PersonView(2, "Meera Rao", "ambassador", date(2026, 1, 1))]
    board = Board()
    for name in seen:
        board.post(Evidence("person", "img:a", name, None, (0, 0, 10, 10)))
    rules = system_rule_views()
    return SimpleNamespace(rule_by_code={r.code: r for r in rules}, board=board, partial=set(),
                           people=SimpleNamespace(people=people, photos={i: [b"x"] for i in photos}),
                           base=make_ctx(body, rules))


def test_the_text_naming_one_ambassador_while_another_is_shown():
    [f] = person_findings(_person_run("Say hi to Riya, our new face!", ["Meera Rao"]))
    assert f.quote == "Riya" and "Meera Rao" in f.title and f.locator["evidence"][0]["source"] == "img:a"
    assert person_findings(_person_run("Say hi to Riya!", ["Riya Sen"])) == []
    # Without reference photos nobody could have recognised Riya, so her absence proves nothing.
    assert person_findings(_person_run("Say hi to Riya!", ["Meera Rao"], photos=(2,))) == []
    # An approved person listed without photos is the same: the library had nothing to recognise her by.
    run = _person_run("Say hi to Riya!", ["Meera Rao"])
    run.people.photos[1] = []
    assert person_findings(run) == []
    # Only the whole name, capitalised, counts as naming her.
    assert person_findings(_person_run("Our riyadh team says hi", ["Meera Rao"])) == []
    # No face identified at all is the faces check's business, not a mismatch.
    assert person_findings(_person_run("Say hi to Riya!", [])) == []
