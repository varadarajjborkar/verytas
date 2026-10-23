"""Multimodal intake end to end, through the HTTP API, offline providers.

Images, PDFs (text layer, scanned pages, pasted screenshots), brand assets,
video, irregular uploads, creator notes, disputes and resubmission.
"""

from __future__ import annotations

import io

import pytest

from tests.media_fixtures import (
    b64,
    caption_video,
    mascot_face,
    mascot_scene,
    pdf,
    png,
    scanned_pdf,
    text_image,
)
from verytas.media import pixels
from verytas.media.ocr import OcrLine, OcrResult
from verytas.security.terms import term_pattern


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def world(client):
    admin = client.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                            "admin_name": "Ada"}).json()["token"]
    tokens = {"admin": admin}
    for role in ("creator", "reviewer", "approver"):
        tokens[role] = client.post("/users", headers=_auth(admin),
                                   json={"email": f"{role}@acme.io", "name": role, "role": role}).json()["token"]
    h = _auth(admin)
    rule = client.post("/rules", headers=h, json={
        "code": "TERM-01", "category": "terminology", "kind": "deterministic", "severity": "must",
        "title": "Banned hype", "text": "Do not say game-changer.",
        "pattern": {"type": "banned_terms", "terms": ["game-changer"]}, "tier": "public"}).json()
    client.patch(f"/rules/{rule['id']}", headers=h, json={"status": "active"})
    client.post("/confidential-terms", headers=h, json={"term": "Project Lumen", "embargo_until": "2099-01-01"})
    return tokens


def _submit(client, world, body="Launch post", attachments=None, notes=None, channel="instagram", tier="public"):
    res = client.post("/contents?wait=true", headers=_auth(world["creator"]), json={
        "title": "T", "channel": channel, "tier": tier, "body": body, "attachments": attachments or {},
        "creator_notes": notes or {}})
    assert res.status_code == 201, res.text
    review = client.get(f"/reviews/{res.json()['review_id']}", headers=_auth(world["creator"])).json()
    return res.json(), review


def _roles(review) -> list[str]:
    return [a["role"] for a in review["coverage"]["agents"]]


def test_text_inside_an_image_is_checked_like_typed_text(client, world):
    img = text_image(["Psst: Project Lumen is coming", "It is a total game-changer"])
    _, review = _submit(client, world, attachments={"images": [
        {"id": "hero", "alt": "A teaser card for our next launch", "data_base64": b64(png(img))}]})
    by_rule = {f["citations"][0]["label"].split()[0]: f for f in review["findings"]}
    leak, banned = by_rule["CONF-LEAK"], by_rule["TERM-01"]
    assert leak["source"] == "img:hero:ocr" and leak["locator"]["image"] == "img:hero"
    assert leak["level"] == "blocker" and banned["source"] == "img:hero:ocr"
    assert {"image", "ocr", "text", "worker"} <= set(_roles(review))
    src = next(s for s in review["coverage"]["sources"] if s["id"] == "img:hero:ocr")
    assert src["route"] == "ocr:local" and "Project Lumen" in src["text"]


def test_pdf_pages_screenshots_and_scans_each_get_their_own_agents(client, world):
    doc = pdf([
        {"text": ["Spring catalogue", "Our new tutor app is a game-changer"],
         "image": text_image(["Project Lumen sneak peek"])},
        {"text": ["Plain second page with nothing wrong in it"]},
    ])
    _, review = _submit(client, world, body="See the catalogue", channel="linkedin",
                        attachments={"documents": [{"id": "cat", "name": "catalogue.pdf", "data_base64": b64(doc)}]})
    sources = {f["source"] for f in review["findings"]}
    assert "doc:cat:p1:text" in sources  # banned term in the text layer
    assert "doc:cat:p1:img1:ocr" in sources  # codename in the pasted screenshot
    roles = _roles(review)
    assert roles.count("page") == 2 and "document" in roles
    # Depth: prism > document > page > image > ocr > text > worker
    assert max(a["depth"] for a in review["coverage"]["agents"]) >= 6


def test_text_converted_to_outlines_is_read_from_the_drawing(client, world):
    # A design tool's "convert text to outlines" leaves a page whose real text layer is clean and whose
    # codename exists only as shapes. The drawn line is checked; the layer's own lines aren't checked twice.
    doc = pdf([{"text": ["Spring catalogue", "Courses for every learner, at every level"],
                "outlined": ["Project Lumen sneak peek"]}])
    _, review = _submit(client, world, body="See the catalogue", channel="linkedin",
                        attachments={"documents": [{"id": "cat", "data_base64": b64(doc)}]})
    leak = next(f for f in review["findings"] if f["category"] == "confidentiality")
    assert leak["source"] == "doc:cat:p1:drawn" and leak["locator"]["page"] == 1
    drawn = next(s for s in review["coverage"]["sources"] if s["id"] == "doc:cat:p1:drawn")
    assert "Lumen" in drawn["text"] and "catalogue" not in drawn["text"].lower()


def test_a_headline_outlined_as_one_shape_is_still_read(client, world):
    from verytas.media.documents import extract_pdf

    doc = pdf([{"text": ["Spring catalogue", "Courses for every learner"], "outlined": ["Project Lumen"],
                "one_shape": True}])
    assert extract_pdf(doc).pages[0].graphics_jpeg is not None
    _, review = _submit(client, world, body="See the catalogue", channel="linkedin",
                        attachments={"documents": [{"id": "cat", "data_base64": b64(doc)}]})
    assert any(f["source"] == "doc:cat:p1:drawn" for f in review["findings"])


def test_a_screenshot_on_a_drawn_page_is_reported_once(client, world):
    doc = pdf([{"text": ["Spring catalogue", "Courses for every learner"], "outlined": ["Spring sale"],
                "image": text_image(["Project Lumen sneak peek"])}])
    _, review = _submit(client, world, body="See the catalogue", channel="linkedin",
                        attachments={"documents": [{"id": "cat", "data_base64": b64(doc)}]})
    leaks = [f["source"] for f in review["findings"] if f["category"] == "confidentiality"]
    assert leaks == ["doc:cat:p1:img1:ocr"]


def test_drawn_lettering_in_an_unreadable_script_is_said_to_be_unread(client, world, monkeypatch):
    from verytas.media import ocr

    real = ocr.read

    def with_hindi(img):
        out = real(img)
        out.foreign.append(ocr.OcrLine("\u5e02H\u5e02149", 0.9, (0, 0, 50, 20)))
        return out

    monkeypatch.setattr(ocr, "read", with_hindi)
    doc = pdf([{"text": ["Spring catalogue", "Courses for every learner"], "outlined": ["Spring sale"]}])
    _, review = _submit(client, world, body="See the catalogue", channel="linkedin",
                        attachments={"documents": [{"id": "cat", "data_base64": b64(doc)}]})
    assert any(f["citations"][0]["label"].startswith("MEDIA-UNREAD") and f["source"] == "doc:cat:p1:drawn"
               for f in review["findings"])


def test_a_drawn_word_among_layer_words_is_caught_and_ocr_slips_are_not():
    from verytas.prism.agents import _drawn_only

    known = {"spring", "catalogue", "courses", "for", "every", "learner", "launches"}
    assert _drawn_only("Lumen launches for every learner", known)
    assert not _drawn_only("Courses for every leamer.", known)
    assert not _drawn_only("Spring-catalogue", known)


def test_a_word_image_that_cannot_be_read_makes_the_read_partial():
    import zipfile

    from verytas.media.documents import extract_docx

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
                    '2006/main"><w:body><w:p><w:r><w:t>Hello there, learners</w:t></w:r></w:p></w:body></w:document>')
        zf.writestr("word/media/image1.emf", b"\x01\x00\x00\x00" + b"\x00" * 80)
        zf.writestr("word/media/image2.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><text>Lumen</text></svg>')
    out = extract_docx(buf.getvalue())
    assert out.partial and sum("can't be read" in n for n in out.notes) == 2


def test_a_plain_text_page_is_not_rendered_again(client, world):
    doc = pdf([{"text": ["Spring catalogue", "Courses for every learner"]}])
    _, review = _submit(client, world, body="See the catalogue", channel="linkedin",
                        attachments={"documents": [{"id": "cat", "data_base64": b64(doc)}]})
    assert not any(s["id"].endswith(":drawn") for s in review["coverage"]["sources"])


def test_a_scanned_pdf_is_rendered_and_read_by_ocr(client, world):
    doc = scanned_pdf(text_image(["Scanned flyer", "Project Lumen launches soon"], size=(1200, 300)))
    _, review = _submit(client, world, body="Flyer attached", channel="linkedin",
                        attachments={"documents": [{"id": "scan", "data_base64": b64(doc)}]})
    leak = next(f for f in review["findings"] if f["category"] == "confidentiality")
    assert leak["source"] == "doc:scan:p1:scan:ocr" and leak["locator"]["page"] == 1


def _register_mascot(client, world, *, part="face", wordmark=None):
    res = client.post("/brand-assets", headers=_auth(world["admin"]), json={
        "name": "Owly", "kind": "mascot", "part": part, "data_base64": b64(png(mascot_face())),
        "wordmark": wordmark})
    assert res.status_code == 201, res.text


def test_a_body_attached_to_an_official_face_is_an_unapproved_extension(client, world):
    _register_mascot(client, world)
    _, review = _submit(client, world, attachments={"images": [
        {"id": "post", "alt": "Owly at the beach", "data_base64": b64(png(mascot_scene(mascot_face(), body=True)))}]})
    ext = [f for f in review["findings"] if f["title"].startswith("Unapproved additions to Owly")]
    assert ext and ext[0]["level"] == "blocker" and ext[0]["model"] is None  # pixel evidence alone
    assert ext[0]["locator"]["box"]


def test_an_altered_official_asset_is_caught_and_an_exact_copy_is_not(client, world):
    _register_mascot(client, world, part="full")
    _, clean = _submit(client, world, attachments={"images": [
        {"id": "a", "alt": "Owly says hello", "data_base64": b64(png(mascot_scene(mascot_face())))}]})
    assert not [f for f in clean["findings"] if f["category"] == "visual"]
    _, altered = _submit(client, world, attachments={"images": [
        {"id": "b", "alt": "Owly says hello", "data_base64": b64(png(mascot_scene(mascot_face(eye=(30, 140, 220)))))}]})
    hit = [f for f in altered["findings"] if f["title"] == "Owly differs from the official artwork"]
    assert hit and "colour" in hit[0]["explanation"]


def test_a_misspelled_wordmark_is_flagged(client, world):
    client.post("/brand-assets", headers=_auth(world["admin"]), json={
        "name": "Inkloom logo", "kind": "logo", "part": "wordmark", "wordmark": "Inkloom",
        "data_base64": b64(png(text_image(["Inkloom"], size=(400, 120))))})
    _, review = _submit(client, world, attachments={"images": [
        {"id": "ad", "alt": "Our logo on a banner", "data_base64": b64(png(text_image(["Inkl00m", "new season"])))}]})
    assert any("Wordmark misspelled: 'Inkl00m'" in f["title"] for f in review["findings"])


def test_video_captions_and_speech_are_checked_with_timestamps(client, world, monkeypatch):
    from verytas.media import video
    from verytas.media.video import Cue

    monkeypatch.setattr(video, "transcribe", lambda pcm, model, vocabulary=None: (
        [Cue(1.0, 3.5, "honestly this app is a game-changer")], "en", 0.98))
    clip = caption_video([(0, 3, "Project Lumen drops soon"), (3, 6, "Join the waitlist")])
    blob = client.post("/media", headers=_auth(world["creator"]),
                       files={"file": ("reel.mp4", clip, "video/mp4")}).json()
    assert blob["media_type"] == "video/mp4" and blob["metrics"]["duration"] > 5
    _, review = _submit(client, world, body="New reel", attachments={"videos": [{"id": "reel", "blob_id": blob["id"]}]},
                        notes={"brief": "A short reel with captions about the waitlist; I speak over it."})
    leak = next(f for f in review["findings"] if f["source"] == "vid:reel:captions")
    assert leak["category"] == "confidentiality" and leak["locator"]["time"][0] < 3
    said = next(f for f in review["findings"] if f["source"] == "vid:reel:speech")
    assert said["locator"]["time"] == [1.0, 3.5]
    assert any(f["title"] == "Captions are burned in only" for f in review["findings"])
    assert {"video", "captions", "speech", "keyframes"} <= set(_roles(review))


def test_irregular_uploads_need_a_reason_and_then_count_against_the_score(client, world):
    long_caption = "Our story. " * 400  # far over X's typical length
    res = client.post("/contents", headers=_auth(world["creator"]), json={
        "title": "T", "channel": "x", "body": long_caption})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["irregularities"][0]["code"] == "caption_length"

    _, review = _submit(client, world, body=long_caption, channel="x",
                        notes={"irregularity": "Marketing asked for the full founder letter as one post"})
    irregular = [f for f in review["findings"] if f["title"].startswith("Irregular caption")]
    assert irregular and irregular[0]["level"] in ("warning", "blocker")


def test_precheck_reports_hidden_characters_before_submission(client, world):
    res = client.post("/contents/precheck", headers=_auth(world["creator"]),
                      json={"channel": "instagram", "body": "game\u200b-changer deal"}).json()
    assert res["needs_reason"] and res["irregularities"][0]["code"] == "hidden_characters"


def test_declared_ai_use_without_a_label_is_flagged(client, world):
    _, review = _submit(client, world, body="Fresh summer look", notes={"ai_used": True})
    assert any(f["title"] == "AI-made content without an AI label" for f in review["findings"])
    _, labelled = _submit(client, world, body="Fresh summer look #MadeWithAI", notes={"ai_used": True})
    assert not any("AI label" in f["title"] for f in labelled["findings"])


def test_a_dispute_cannot_talk_away_a_mechanical_finding(client, world):
    res, review = _submit(client, world, body="Project Lumen is coming")
    leak = next(f for f in review["findings"] if f["category"] == "confidentiality")
    d = client.post(f"/findings/{leak['id']}/disputes?wait=true", headers=_auth(world["creator"]),
                    json={"claim": "Lumen is just the Latin word for light here, not the codename"}).json()
    assert d["status"] == "upheld" and d["verdict"]["decided_by"] == "policy"


def test_resubmit_applies_fixes_records_disputes_and_reruns(client, world):
    admin = _auth(world["admin"])
    rule = client.post("/rules", headers=admin, json={
        "code": "TERM-02", "category": "terminology", "kind": "deterministic", "severity": "should",
        "title": "House style", "text": "Say email.",
        "pattern": {"type": "preferred_terms", "map": {"e-mail": "email"}},
        "tier": "public"}).json()
    client.patch(f"/rules/{rule['id']}", headers=admin, json={"status": "active"})
    res, review = _submit(client, world, body="Send us an e-mail today")
    fix = next(f for f in review["findings"] if f["suggestions"])
    out = client.post(f"/contents/{res['content']['id']}/resubmit?wait=true", headers=_auth(world["creator"]),
                      json={"apply": [fix["id"]], "resolved": [fix["id"]]})
    assert out.status_code == 201, out.text
    body = out.json()
    assert body["applied"] == 1
    assert body["submit"]["version"]["body"] == "Send us an email today"
    again = client.get(f"/reviews/{body['submit']['review_id']}", headers=_auth(world["creator"])).json()
    assert again["status"] == "done" and not [f for f in again["findings"] if f["suggestions"]]


def test_coverage_is_plain_json_even_with_numpy_details():
    import numpy as np

    from verytas.prism.orchestrator import _plain

    out = _plain({"a": np.bool_(True), "b": [np.float64(1.5), (np.int64(2),)], "c": "x"})
    assert out == {"a": True, "b": [1.5, [2]], "c": "x"} and type(out["a"]) is bool


def test_unknown_or_foreign_blob_ids_are_refused(client, world):
    res = client.post("/contents", headers=_auth(world["creator"]), json={
        "title": "T", "body": "x", "attachments": {"videos": [{"id": "v", "blob_id": "0" * 32}]},
        "creator_notes": {"brief": "A clip of the launch event with our mascot."}})
    assert res.status_code == 422 and "unknown media" in res.text


def test_a_picture_without_text_is_not_reported_unreadable(client, world):
    # Black-box finding: OCR noise on a plain illustration raised a blocker.
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 900), (240, 246, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((280, 200, 620, 640), 60, fill=(90, 160, 220))
    d.arc((380, 440, 520, 540), 20, 160, fill=(20, 40, 80), width=10)
    _, review = _submit(client, world, attachments={"images": [
        {"id": "pic", "alt": "A friendly blue character waving", "data_base64": b64(png(img))}]})
    assert not [f for f in review["findings"] if "could not be read" in f["title"]]


def test_ocr_noise_is_dropped_but_short_real_words_are_kept():
    from verytas.media.ocr import _meaningful

    assert not _meaningful("l", 0.9) and not _meaningful("~.", 0.95) and not _meaningful("ab", 0.4)
    assert _meaningful("OK", 0.95) and _meaningful("Sale ends Friday", 0.55)


def test_pixel_redaction_blacks_out_only_the_term():
    from PIL import Image

    img = Image.new("RGB", (600, 60), "white")
    words = [("hello", (0, 10, 90, 50)), ("Project", (110, 10, 230, 50)), ("Lumen", (240, 10, 340, 50)),
             ("world", (400, 10, 500, 50))]
    ocr = OcrResult([OcrLine("hello Project Lumen world", 0.99, (0, 10, 500, 50), words)])
    out, hidden = pixels.redact(img, ocr, [term_pattern("Project Lumen", loose=True)])
    assert hidden == 1
    px = out.load()
    assert px[112, 30] == px[338, 30] == (0, 0, 0)  # the term's own word boxes, edge to edge
    assert px[10, 30] == (255, 255, 255) and px[490, 30] == (255, 255, 255)


def test_pixel_redaction_covers_the_whole_line_without_word_boxes():
    from PIL import Image

    img = Image.new("RGB", (600, 60), "white")
    ocr = OcrResult([OcrLine("hello Project Lumen world", 0.99, (0, 10, 500, 50))])
    out, _ = pixels.redact(img, ocr, [term_pattern("Project Lumen", loose=True)])
    assert out.load()[10, 30] == out.load()[490, 30] == (0, 0, 0)


def test_pixel_redaction_catches_wrapped_terms_and_noise_lines():
    from PIL import Image

    img = Image.new("RGB", (600, 200), "white")
    ocr = OcrResult([OcrLine("Teaser for Project", 0.99, (0, 10, 400, 50)),
                     OcrLine("Lumen arrives", 0.99, (0, 70, 300, 110))],
                    noise=[OcrLine("Project Lumen", 0.2, (0, 140, 300, 180))])
    out, hidden = pixels.redact(img, ocr, [term_pattern("Project Lumen", loose=True)])
    px = out.load()
    assert hidden == 2 and px[10, 30] == px[10, 90] == px[10, 160] == (0, 0, 0)


# --- emoji -----------------------------------------------------------------------------------

def test_emoji_inside_a_codename_does_not_hide_it(client, world):
    _, review = _submit(client, world, body="Psst: Project\U0001F525Lumen and Proj\U0001F680ect Lumen soon")
    leaks = [f for f in review["findings"] if f["category"] == "confidentiality"]
    assert len(leaks) == 2


def test_obscene_gesture_emoji_and_emoji_noise_are_flagged(client, world):
    body = "To the haters \U0001F595 our sale is live \U0001F680\U0001F680\U0001F680\U0001F680\U0001F680 sa\U0001F525le"
    _, review = _submit(client, world, body=body)
    titles = [f["title"] for f in review["findings"]]
    assert any(t.startswith("Obscene gesture emoji") for t in titles)
    assert any("emoji in a row" in t for t in titles) and any("inside a word" in t for t in titles)


def test_a_brand_can_ban_its_own_emoji(client, world):
    admin = _auth(world["admin"])
    rule = client.post("/rules", headers=admin, json={
        "code": "EMOJI-BANK", "category": "terminology", "kind": "deterministic", "severity": "should",
        "title": "No money emoji", "text": "A bank never uses money emoji next to offers.",
        "pattern": {"type": "banned_emoji", "emojis": ["\U0001F4B0", "\U0001F911"]}, "tier": "public"}).json()
    client.patch(f"/rules/{rule['id']}", headers=admin, json={"status": "active"})
    _, review = _submit(client, world, body="Open an account today \U0001F4B0")
    assert any(f["title"].startswith("Emoji \U0001F4B0 is not used") for f in review["findings"])


# --- presentation ------------------------------------------------------------------------------

def test_a_disclosure_hidden_behind_more_is_flagged(client, world):
    body = "Loving my new morning routine with this brand. " * 4 + "#ad"
    _, review = _submit(client, world, body=body, channel="instagram")
    assert any("hidden behind" in f["title"] for f in review["findings"])
    _, upfront = _submit(client, world, body="#ad " + body[:-3], channel="instagram")
    assert not any("hidden behind" in f["title"] for f in upfront["findings"])


def test_text_cut_by_the_feed_crop_is_flagged(client, world):
    from PIL import Image, ImageDraw

    from tests.media_fixtures import font

    img = Image.new("RGB", (1080, 1920), "white")  # 9:16 in a 4:5 feed: top and bottom are cut
    d = ImageDraw.Draw(img)
    d.text((60, 40), "Offer ends Sunday, terms apply", fill="black", font=font(56))
    d.text((60, 900), "Big summer sale", fill="black", font=font(72))
    _, review = _submit(client, world, attachments={"images": [
        {"id": "tall", "alt": "Summer sale poster", "data_base64": b64(png(img))}]}, channel="instagram")
    cut = [f for f in review["findings"] if f["title"].startswith("Cut off in the instagram feed")]
    assert cut and "Offer ends Sunday" in cut[0]["title"]


def test_text_under_the_app_buttons_is_flagged_on_full_screen_channels(client, world):
    from PIL import Image, ImageDraw

    from tests.media_fixtures import font

    img = Image.new("RGB", (1080, 1920), (30, 40, 80))
    d = ImageDraw.Draw(img)
    d.text((60, 1800), "Use code SAVE20 at checkout", fill="white", font=font(56))
    _, review = _submit(client, world, attachments={"images": [
        {"id": "story", "alt": "Promo card with a discount code", "data_base64": b64(png(img))}]}, channel="tiktok")
    assert any(f["title"].startswith("Text under the tiktok buttons") for f in review["findings"])


def test_an_attached_image_is_served_back_to_whoever_can_read_the_piece(client, world):
    made, _ = _submit(client, world, attachments={"images": [
        {"id": "poster", "alt": "A poster", "data_base64": b64(png(text_image(["Hello"], size=(600, 400))))}]})
    cid = made["content"]["id"]
    [version] = client.get(f"/contents/{cid}", headers=_auth(world["creator"])).json()["versions"]
    # References only: the bytes never ride along with the piece.
    assert version["images"] == [{"id": "poster", "alt": "A poster", "decorative": False, "media_type": "image/png"}]
    url = f"/contents/{cid}/versions/{version['id']}/images/poster"
    for who in ("creator", "reviewer"):
        res = client.get(url, headers=_auth(world[who]))
        assert res.status_code == 200 and res.headers["content-type"] == "image/png"
        assert res.content.startswith(b"\x89PNG") and res.headers["x-content-type-options"] == "nosniff"
    # Another creator can't see the piece, so not its images either; unknown ids are the same 404.
    other = client.post("/users", headers=_auth(world["admin"]),
                        json={"email": "other@acme.io", "name": "Other", "role": "creator"}).json()["token"]
    assert client.get(url, headers=_auth(other)).status_code == 404
    assert client.get(f"/contents/{cid}/versions/{version['id']}/images/nope", headers=_auth(world["creator"])
                      ).status_code == 404
    assert client.get(f"/contents/{cid}/versions/999999/images/poster", headers=_auth(world["creator"])
                      ).status_code == 404


def test_drawn_pages_past_the_cap_are_reported_partly_read(monkeypatch):
    from verytas.media import documents

    monkeypatch.setattr(documents, "DRAWN_RENDERS", 1)
    page = {"text": ["Spring catalogue", "Courses for every learner"], "outlined": ["Spring sale"]}
    out = documents.extract_pdf(pdf([page, page]))
    assert out.pages[0].graphics_jpeg is not None and out.pages[1].graphics_jpeg is None
    assert out.partial and any("page 2: drawn shapes not read" in n for n in out.notes)


def test_glyphs_from_a_script_ocr_cannot_read_are_set_aside_not_checked(monkeypatch):
    # RapidOCR reads a Hindi price as look-alike Chinese glyphs ("市H市149"); that is not text to check.
    from types import SimpleNamespace

    from PIL import Image

    from verytas.media import ocr

    out = SimpleNamespace(txts=["Diwali sale", "市H市149"], scores=[0.95, 0.9],
                          boxes=[[[0, 0], [100, 0], [100, 20], [0, 20]], [[0, 30], [100, 30], [100, 50], [0, 50]]],
                          word_results=None)
    monkeypatch.setattr(ocr, "_get_engine", lambda: (lambda *a, **k: out))
    result = ocr.read(Image.new("RGB", (200, 80), "white"))
    assert result.text == "Diwali sale" and [ln.text for ln in result.foreign] == ["市H市149"]


def test_one_stray_glyph_is_dropped_and_the_line_still_checked(monkeypatch):
    # A dash or a box can come back as a single CJK glyph; the contact number beside it must still be read.
    from types import SimpleNamespace

    from PIL import Image

    from verytas.media import ocr

    out = SimpleNamespace(txts=["Guaranteed 100% returns, call 9876543210 \u4e00"], scores=[0.95],
                          boxes=[[[0, 0], [300, 0], [300, 20], [0, 20]]], word_results=None)
    monkeypatch.setattr(ocr, "_get_engine", lambda: (lambda *a, **k: out))
    result = ocr.read(Image.new("RGB", (400, 40), "white"))
    assert result.text == "Guaranteed 100% returns, call 9876543210" and not result.foreign


def test_speech_vocabulary_has_the_brands_public_names_and_never_a_confidential_term():
    from types import SimpleNamespace

    from verytas.checks.base import TermView
    from verytas.prism.orchestrator import _vocabulary

    rules = [SimpleNamespace(pattern={"type": "casing", "terms": ["Kitepath", "KiteLearn", "Project Falcon app"]}),
             SimpleNamespace(pattern={"type": "preferred_terms", "map": {"webinar": "live class"}}),
             SimpleNamespace(pattern={"type": "banned_terms", "terms": ["guaranteed job"]})]
    ctx = SimpleNamespace(rules=rules, terms=[TermView(1, "Project Falcon", None)])
    assets = [SimpleNamespace(official=True, restricted=False, wordmark="Kitepath"),
              SimpleNamespace(official=True, restricted=True, wordmark="KiteLearn 2.0"),
              SimpleNamespace(official=False, restricted=False, wordmark="SkillSprint")]
    said = _vocabulary(ctx, assets)
    assert said == "Kitepath, KiteLearn, live class"
    # A public name inside a confidential term primes it too, and a long list ends on a whole name.
    rules.append(SimpleNamespace(pattern={"type": "casing", "terms": ["Falcon", *(f"Name{i:03d}" for i in range(80))]}))
    said = _vocabulary(ctx, assets)
    assert "Falcon" not in said and len(said) <= 400 and said.split(", ")[-1].startswith("Name")
    assert len(said.split(", ")[-1]) == 7


def test_the_better_speech_model_gets_less_audio_on_fewer_cores():
    from verytas.prism.orchestrator import _small_model_seconds

    assert _small_model_seconds(180, 180, cores=2) < 60 < _small_model_seconds(180, 180, cores=8) <= 180
    assert _small_model_seconds(0, 180, cores=8) == 0


def test_long_audio_uses_the_lighter_speech_model():
    import numpy as np

    from verytas.prism.agents import ReviewRun

    run = ReviewRun.__new__(ReviewRun)
    run.asr_model, run.asr_long_model, run.asr_long_seconds = "small", "base", 180
    assert run.asr_for(np.zeros(16_000 * 60)) == "small"
    assert run.asr_for(np.zeros(16_000 * 600)) == "base"


def test_ocr_puts_back_brand_names_whose_i_and_l_strokes_were_swapped():
    from verytas.media.ocr import restore_names

    text, n = restore_names("Proud to be #Madelnlndia with lnkloom, by INKLOOM", ["MadeInIndia", "Inkloom", "AI"])
    assert text == "Proud to be #MadeInIndia with Inkloom, by INKLOOM" and n == 2
    # Case and spelling are the casing check's to judge, and a name inside a longer word is not the name.
    for kept in ("#madeinindia", "Madelnlndias", "Inkl00m", "Al Jazeera"):
        assert restore_names(kept, ["MadeInIndia", "Inkloom", "AI"]) == (kept, 0)
