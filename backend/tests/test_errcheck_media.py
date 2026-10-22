"""Regressions for the multimodal review's coverage, privacy and resource findings."""

from __future__ import annotations

import io
import os
import zipfile
import zlib

import pytest
from PIL import Image, ImageDraw

from tests.helpers import make_ctx, system_rule_views
from tests.media_fixtures import b64, pdf, text_image
from tests.test_media import _auth, _submit, world  # noqa: F401, the fixture is used by name
from verytas.checks.base import RawFinding
from verytas.media import assets as asset_match
from verytas.media import documents
from verytas.media.files import pdf_active_content, sniff
from verytas.media.profile import HARD_PAGES, hidden_characters
from verytas.prism import agents
from verytas.prism.agents import AgentTree, ReviewRun
from verytas.prism.disputes import is_mechanical
from verytas.prism.governor import Governor
from verytas.prism.orchestrator import _apply_cleared, _coverage_gaps
from verytas.providers.offline import OfflineJudge, OfflineLLM

# --- coverage ---------------------------------------------------------------------------------------


async def test_essential_agents_run_after_the_budget_is_spent():
    tree = AgentTree(max_depth=8, max_nodes=3)
    ran = []

    async def work(node):
        ran.append(node.label)

    for i in range(5):
        await tree.spawn(None, "page", f"p{i}", work)
    await tree.spawn(None, "policy", "policy", work, essential=True)
    assert ran == ["p0", "p1", "p2", "policy"]
    assert [n.label for n in tree.gaps()] == ["p3", "p4"]


def test_every_kind_of_gap_demotes_what_it_covers():
    from verytas.prism.agents import AgentNode

    def gap(role, label="x"):
        return AgentNode("a", role, label, None, 1, status="skipped")

    failed, degraded = _coverage_gaps([gap("worker", "claim verifier"), gap("policy"), gap("context-layer")],
                                      has_assets=False)
    assert failed == {"claims", "messaging", "legal"} and degraded == {"messaging"}
    failed, _ = _coverage_gaps([gap("keyframes")], has_assets=True)
    assert failed == {"visual"}


def test_a_banned_term_on_page_40_is_found_and_policy_still_runs(client, world):  # noqa: F811
    pages = [{"text": [f"Page {i} of the annual report, nothing to see here."]} for i in range(1, 40)]
    pages.append({"text": ["Closing page: our app is a game-changer."]})
    _, review = _submit(client, world, body="Annual report", channel="blog", attachments={"documents": [
        {"id": "report", "name": "report.pdf", "data_base64": b64(pdf(pages))}]})
    assert any(f["quote"] == "game-changer" for f in review["findings"])
    roles = {a["role"]: a["status"] for a in review["coverage"]["agents"] if a["role"] in ("policy", "intent")}
    assert roles == {"policy": "ok", "intent": "ok"}


async def test_no_image_reaches_the_vision_model_when_local_ocr_fails(monkeypatch):
    sent = []

    class Vision:
        name = "test/vision"

        async def run(self, task):
            sent.append(task)
            raise AssertionError("pixels left without redaction")

    def broken(_img):
        raise RuntimeError("onnx session died")

    monkeypatch.setattr(agents.local_ocr, "read", broken)
    tree = AgentTree(8, 50)
    run = ReviewRun(base=make_ctx("x", system_rule_views()), llm=OfflineLLM(), judge=OfflineJudge(),
                    vision=Vision(), governor=Governor(2, 10), tree=tree, rule_by_code={}, assets=[],
                    content_tier_rank=0, allow_cloud_vision=True, semantic_threshold=0.6, ocr_min_confidence=0.8)
    img = text_image(["Project Lumen launches soon"])
    await tree.spawn(None, "image", "img", lambda n: agents.image_agent(run, n, img, "img:x", {"image": "x"}))
    assert not sent
    assert any("local OCR failed" in note for note in run.notes)
    assert any(n.role == "ocr" and n.status == "failed" for n in tree.nodes.values())


def test_fact_backed_claims_are_mechanical_even_when_a_model_linked_them():
    linked = RawFinding(unit_id="p1", category="claims", title="Outdated", explanation="", confidence=0.9,
                        checker="claims", fact_id=7, model="ollama/gpt-oss:120b")
    judged = RawFinding(unit_id="p1", category="claims", title="Unsupported", explanation="", confidence=0.7,
                        checker="claims", model="ollama/gpt-oss:120b")
    assert is_mechanical(linked) and not is_mechanical(judged)


def test_a_cleared_quote_less_dispute_only_covers_its_own_image():
    def finding(source):
        return RawFinding(unit_id=source, category="visual", title="Imitation", explanation="", confidence=0.6,
                          checker="assets", rule_code="VIS-ASSET-IMITATION", model="vision", source=source)

    a, b = finding("img:one"), finding("img:two")
    _apply_cleared([a, b], [(5, None, "img:one", 1)], {"VIS-ASSET-IMITATION": 5})
    assert a.level_cap == "advisory" and b.level_cap is None


def test_long_videos_are_sampled_sparser_not_cut_short():
    from verytas.media import video

    assert video.sample_every(120, 900) == 1.0
    assert video.sample_every(900, 900) * video.MAX_FRAMES == pytest.approx(900)


def test_resubmit_review_runs_even_if_a_dispute_evaluation_crashes(client, world, monkeypatch):  # noqa: F811
    from verytas.prism import disputes

    async def boom(prism, dispute_id):
        raise RuntimeError("database is locked")

    res, review = _submit(client, world, body="It is a game-changer")
    finding = review["findings"][0]
    monkeypatch.setattr(disputes, "evaluate", boom)
    out = client.post(f"/contents/{res['content']['id']}/resubmit?wait=true", headers=_auth(world["creator"]),
                      json={"disputes": [{"finding_id": finding["id"], "claim": "It is a quote from a customer"}]})
    assert out.status_code == 201, out.text
    again = client.get(f"/reviews/{out.json()['submit']['review_id']}", headers=_auth(world["creator"])).json()
    assert again["status"] == "done"


# --- documents --------------------------------------------------------------------------------------


def _huge_blank_pdf(pages: int) -> bytes:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(14400, 14400)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_huge_blank_pages_are_rendered_small_and_not_kept():
    out = documents.extract_pdf(_huge_blank_pdf(5))
    assert [p.render_jpeg for p in out.pages] == [None] * 5
    assert sum("blank" in n for n in out.notes) == 5


def _docx(document_xml: str, extra: dict[str, str] | None = None) -> bytes:
    from docx import Document

    buf = io.BytesIO()
    Document().save(buf)
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                data = document_xml.encode()
            dst.writestr(item, data)
        for name, xml in (extra or {}).items():
            dst.writestr(name, xml)
    return out.getvalue()


_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def test_word_headers_footers_text_boxes_comments_and_deletions_are_read():
    body = (f'<w:document {_W}><w:body>'
            '<w:p><w:r><w:t>Body text normal</w:t></w:r>'
            '<w:r><w:pict><w:txbxContent><w:p><w:r><w:t>Box says game-changer</w:t></w:r></w:p></w:txbxContent>'
            '</w:pict></w:r></w:p>'
            '<w:p><w:ins><w:r><w:t>Inserted line</w:t></w:r></w:ins>'
            '<w:del><w:r><w:delText>Project Lumen</w:delText></w:r></w:del></w:p>'
            '</w:body></w:document>')
    raw = _docx(body, {
        "word/header1.xml": f'<w:hdr {_W}><w:p><w:r><w:t>HEADER Project Lumen</w:t></w:r></w:p></w:hdr>',
        "word/footer1.xml": f'<w:ftr {_W}><w:p><w:r><w:t>FOOTER text</w:t></w:r></w:p></w:ftr>',
        "word/comments.xml": f'<w:comments {_W}><w:comment><w:p><w:r><w:t>remove before launch</w:t>'
                             '</w:r></w:p></w:comment></w:comments>',
    })
    text = documents.extract_docx(raw).pages[0].text
    for expected in ("Body text normal", "Box says game-changer", "Inserted line",
                     "[Deleted text (tracked change)] Project Lumen", "[Header] HEADER Project Lumen",
                     "[Footer] FOOTER text", "[Comment] remove before launch"):
        assert expected in text
    assert "Body text normalBox" not in text  # the text box is its own paragraph


def test_word_text_is_capped_and_reported():
    para = "<w:p><w:r><w:t>" + "word " * 2000 + "</w:t></w:r></w:p>"
    out = documents.extract_docx(_docx(f"<w:document {_W}><w:body>{para * 30}</w:body></w:document>"))
    assert out.partial and len(out.pages[0].text) <= documents.MAX_DOC_CHARS


def test_word_entities_are_not_expanded():
    bomb = ('<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;">]>'
            f'<w:document {_W}><w:body><w:p><w:r><w:t>&b;</w:t></w:r></w:p></w:body></w:document>')
    try:
        text = documents.extract_docx(_docx(bomb)).pages[0].text
    except ValueError:
        return  # refusing the part is fine too
    assert "aaaa" not in text


def test_intake_promises_the_page_cap_the_extractor_keeps():
    assert HARD_PAGES == documents.MAX_PAGES


# --- files and intake -------------------------------------------------------------------------------


def test_active_pdf_content_sees_through_escapes_and_object_streams():
    assert "JavaScript" in pdf_active_content(b"%PDF-1.4 1 0 obj << /S /J#61vaScript /JS (x) >> endobj")
    inner = zlib.compress(b"5 0 obj << /S /JavaScript /JS (x) >>")
    assert pdf_active_content(b"%PDF-1.5 4 0 obj << /Type /ObjStm >> stream\n" + inner + b"\nendstream") \
        == ["JavaScript"]


def test_random_stream_bytes_are_not_active_content():
    for _ in range(3):
        raw = b"%PDF-1.5 1 0 obj <</Length 9>> stream\n" + os.urandom(4_000_000) + b"endstream endobj"
        assert pdf_active_content(raw) == []


def test_phone_stills_are_not_mistaken_for_video(client, world):  # noqa: F811
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
    assert sniff(heic) == "image/heic" and sniff(b"\x00\x00\x00\x18ftypisom") == "video/mp4"
    res = client.post("/media", headers=_auth(world["creator"]), files={"file": ("a.heic", heic)})
    assert res.status_code == 415 and "JPEG or PNG" in res.json()["detail"]


def test_hidden_characters_cover_the_full_invisible_set_but_not_emoji():
    assert hidden_characters("hi \u2764\ufe0f \U0001f468\u200d\U0001f469\u200d\U0001f467 1\ufe0f\u20e3 "
                             "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f") == 0
    assert hidden_characters("Pro\u2066ject \U000e0041x \u034f \u3164 a\u200bb \ufe0f") == 6


def test_later_frames_of_an_animated_image_are_read(client, world):  # noqa: F811
    first, second = text_image(["Spring sale"]), text_image(["Project Lumen is coming"])
    buf = io.BytesIO()
    first.save(buf, "GIF", save_all=True, append_images=[second], duration=500)
    _, review = _submit(client, world, attachments={"images": [
        {"id": "anim", "alt": "Sale banner", "data_base64": b64(buf.getvalue())}]})
    leak = next(f for f in review["findings"] if f["category"] == "confidentiality")
    assert leak["source"].startswith("img:anim@f2")
    assert any("animated" in n for n in review["coverage"]["notes"])


# --- assets -------------------------------------------------------------------------------------


def _flat_logo() -> Image.Image:
    logo = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    d.ellipse((20, 20, 380, 380), fill=(220, 30, 40, 255))
    d.rectangle((150, 150, 250, 250), fill=(255, 255, 255, 255))
    return logo


@pytest.mark.parametrize("size", [120, 300])
def test_flat_logos_are_found_by_template_and_exact_copies_pass(size):
    logo = _flat_logo()
    prepared = asset_match.prepare(1, logo)
    assert asset_match.flat(prepared)
    scene = Image.new("RGB", (1200, 800), (240, 240, 230))
    scene.paste(logo.resize((size, size)), (433, 211), logo.resize((size, size)))
    m = asset_match.match(prepared, scene)
    assert m.found and not m.altered
    assert not asset_match.match(prepared, Image.new("RGB", (1200, 800), (240, 240, 230))).found


def test_extreme_artwork_shapes_are_refused(client, world):  # noqa: F811
    with pytest.raises(ValueError):
        asset_match.prepare(1, Image.new("RGB", (6000, 2), "red"))
    res = client.post("/brand-assets", headers=_auth(world["admin"]), json={
        "name": "Line", "kind": "logo", "part": "full", "data_base64": b64(_png(Image.new("RGB", (3000, 40))))})
    assert res.status_code == 422


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_wordmarks_tolerate_ordinary_words_but_not_look_alikes():
    from verytas.media.ocr import OcrLine

    def check(mark, text):
        return agents._misspelled(mark, [OcrLine(text, 0.9, (0, 0, 1, 1))])

    assert check("Nike", "Mike") is None and check("Acme", "Acne") is None
    assert check("Nike", "Nlke") == "Nlke" and check("Amazon", "Arnazon") == "Arnazon"
    assert check("Inkloom", "Inkolom") == "Inkolom"


def test_a_restricted_asset_is_reported_without_its_name():
    from verytas.prism.agents import OfficialAsset

    hit = asset_match.AssetMatch(9, True, 40, (0, 0, 10, 10))
    run = ReviewRun(base=make_ctx("x", system_rule_views()), llm=OfflineLLM(), judge=OfflineJudge(),
                    vision=OfflineLLM(), governor=Governor(1, 1), tree=AgentTree(8, 10),
                    rule_by_code={r.code: r for r in system_rule_views()},
                    assets=[OfficialAsset(9, "Codename Falcon mascot", "mascot", "full", True, None, None, "")],
                    content_tier_rank=0, allow_cloud_vision=False, semantic_threshold=0.6, ocr_min_confidence=0.8)
    node = run.tree.nodes.setdefault("a1", agents.AgentNode("a1", "image", "img", None, 0))
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [hit], None)
    [leak] = run.findings
    assert "Falcon" not in leak.title + leak.explanation



def test_a_damaged_word_part_costs_only_that_part():
    body = f'<w:document {_W}><w:body><w:p><w:r><w:t>Body survives</w:t></w:r></w:p></w:body></w:document>'
    raw = _docx(body, {"word/header1.xml": f'<w:hdr {_W}><w:p><w:r><w:t>HEADERMARK</w:t></w:r></w:p></w:hdr>'})
    # Flip a byte inside the stored header so its CRC no longer matches.
    raw = raw.replace(b"HEADERMARK", b"HEADERMARX", 1)
    out = documents.extract_docx(raw)
    assert "Body survives" in out.pages[0].text
    assert out.partial and any("damaged" in n for n in out.notes)


def test_reading_order_keeps_a_tall_heading_on_the_row_beside_it():
    from verytas.media.ocr import OcrLine, _reading_order

    heading = OcrLine("SALE", 0.9, (0, 90, 200, 150))     # 60 px tall, centre 120
    beside = OcrLine("ends Friday", 0.9, (220, 110, 400, 130))  # 20 px tall, centre 120
    below = OcrLine("Terms apply", 0.9, (0, 200, 180, 220))
    assert [ln.text for ln in _reading_order([below, beside, heading])] == ["SALE", "ends Friday", "Terms apply"]


def test_damaged_animation_is_a_media_error_and_base64_is_strict():
    from verytas.media.files import MediaError, animation_frames, decode_b64

    with pytest.raises(MediaError):
        animation_frames(b"GIF89a" + b"\x00" * 20)
    assert decode_b64("aGVs\nbG8=", 1024) == b"hello"  # line-wrapped is fine
    with pytest.raises(MediaError):
        decode_b64("aGVs*bG8=", 1024)


def test_data_appended_after_an_image_is_found_even_behind_a_fake_end_marker():
    # errcheck 217: the end was the last end marker in the file, so junk that finished with a fake
    # IEND (or FF D9) hid itself. The end is now found by walking the file's own structure.
    import io

    from PIL import Image

    from verytas.media.profile import _trailing_bytes

    def encoded(fmt: str) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), (200, 80, 40)).save(buf, fmt)
        return buf.getvalue()

    png, jpeg = encoded("PNG"), encoded("JPEG")
    assert _trailing_bytes(png, "PNG") == 0 and _trailing_bytes(jpeg, "JPEG") == 0
    junk = b"\x00" * 5000
    assert _trailing_bytes(png + junk, "PNG") == 5000
    assert _trailing_bytes(png + junk + b"IEND" + b"\x00" * 4, "PNG") == 5008
    assert _trailing_bytes(jpeg + junk + b"\xff\xd9", "JPEG") == 5002
