"""PowerPoint, Excel and HTML go through review like a PDF: a slide, a sheet and a web page are pages, with
their own text checks, pictures and locations."""

from __future__ import annotations

import base64
import io
import zipfile

from tests.media_fixtures import b64, text_image
from tests.test_intake import xlsx
from tests.test_media import _auth, _submit, world  # noqa: F401, the fixture
from verytas.media import documents
from verytas.media.files import sniff

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def deck(slides: list[dict]) -> bytes:
    """slides: {"text": [...], "notes": str | None, "image": PIL image | None, "hidden": bool}"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ppt/presentation.xml", f'<p:presentation xmlns:p="{P}"/>')
        for n, s in enumerate(slides, start=1):
            paras = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in s.get("text", []))
            rels = []
            pic = ""
            if s.get("image") is not None:
                z.writestr(f"ppt/media/image{n}.png", _png(s["image"]))
                rels.append(f'<Relationship Id="rIdImg" Target="../media/image{n}.png"/>')
                pic = '<p:pic><p:blipFill><a:blip r:embed="rIdImg"/></p:blipFill></p:pic>'
            if s.get("notes"):
                z.writestr(f"ppt/notesSlides/notesSlide{n}.xml",
                           f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><a:p><a:r><a:t>{s["notes"]}</a:t></a:r></a:p>'
                           f"<a:p><a:r><a:t>{n}</a:t></a:r></a:p></p:notes>")
                rels.append(f'<Relationship Id="rIdN" Target="../notesSlides/notesSlide{n}.xml"/>')
            show = ' show="0"' if s.get("hidden") else ""
            z.writestr(f"ppt/slides/slide{n}.xml",
                       f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"{show}><p:cSld><p:spTree>'
                       f"<p:sp><p:txBody>{paras}</p:txBody></p:sp>{pic}</p:spTree></p:cSld></p:sld>")
            if rels:
                z.writestr(f"ppt/slides/_rels/slide{n}.xml.rels", f'<Relationships xmlns="{REL}">{"".join(rels)}'
                           "</Relationships>")
    return buf.getvalue()


def web_page(picture) -> bytes:
    data = base64.b64encode(_png(picture)).decode()
    return f"""<!DOCTYPE html><html><head><title>Spring sale</title>
<meta name="description" content="Our tutor app is a game-changer">
<script>var hidden = "Project Lumen";</script><style>.x{{}}</style></head>
<body><h1>Learn faster</h1><p>Plain words for everyone.</p>
<div hidden>Project Lumen draft</div>
<img src="https://cdn.example/hero.png">
<img src="spacer.gif" alt="">
<img src="data:image/png;base64,{data}" alt="Teaser for the spring launch event">
</body></html>""".encode()


def test_each_format_is_told_apart_by_its_bytes():
    assert sniff(deck([{"text": ["Hi"]}])).endswith("presentationml.presentation")
    assert sniff(xlsx([["Plan", "Price"], ["Basic", 299]])).endswith("spreadsheetml.sheet")
    assert sniff(b"\xef\xbb\xbf  <!DOCTYPE html><p>x</p>") == "text/html"
    assert sniff(b"<p>a fragment is not a page</p>") == "unknown"


def test_a_deck_is_read_slide_by_slide_with_notes_and_pictures():
    out = documents.extract_pptx(deck([
        {"text": ["Spring launch"], "notes": "Mention Project Lumen only to the board"},
        {"text": ["Draft ideas"], "hidden": True, "image": text_image(["Project Lumen sneak peek"])},
    ]))
    assert [p.label for p in out.pages] == ["slide 1", "slide 2"]
    # The notes travel with the file; the notes page number is not read as text.
    assert out.pages[0].text == "Spring launch\n[Speaker notes] Mention Project Lumen only to the board"
    assert out.pages[1].text.startswith("[Hidden slide] Draft ideas") and len(out.pages[1].images) == 1


def test_a_web_page_reads_what_people_see_and_nothing_that_is_hidden():
    out = documents.extract_html(web_page(text_image(["Project Lumen sneak peek"])))
    [page] = out.pages
    assert "[Page title] Spring sale" in page.text and "[description] Our tutor app is a game-changer" in page.text
    assert "Learn faster" in page.text and "Project Lumen" not in page.text  # script and hidden div dropped
    assert len(page.images) == 1 and out.partial
    assert any(n.startswith("1 linked picture") for n in out.notes)  # the decorative spacer is not counted
    assert [(a["alt"], a["decorative"]) for a in page.alts] == [
        ("", False), ("", True), ("Teaser for the spring launch event", False)]


def test_slides_sheets_and_web_pages_are_reviewed_where_they_are(client, world):  # noqa: F811
    files = {
        "deck": deck([{"text": ["Our tutor app is a game-changer"]},
                      {"text": ["Teaser"], "image": text_image(["Project Lumen sneak peek"])}]),
        "prices": xlsx([["Plan", "Note"], ["Basic", "a game-changer price"]], sheet="Prices"),
        "page": web_page(text_image(["Spring launch"])),
    }
    _, review = _submit(client, world, body="See the attached material", channel="linkedin", attachments={
        "documents": [{"id": k, "name": k, "data_base64": b64(v)} for k, v in files.items()]})
    by_source = {}
    for f in review["findings"]:
        by_source.setdefault(f["source"], []).append(f)
    banned = [f for f in review["findings"] if f["title"] == 'Avoid "game-changer"']
    assert {f["locator"].get("label") for f in banned} == {"slide 1", "sheet Prices", "the page"}
    assert "doc:deck:p2:img1:ocr" in by_source  # the codename in the slide's picture
    alt = [f for f in by_source.get("doc:page:p1:text", []) if f["category"] == "accessibility"
           and "alt text" in f["title"]]
    assert len(alt) == 1 and alt[0]["title"].startswith("Image 1 ")  # the linked hero, not the decorative one
    pages = [a for a in review["coverage"]["agents"] if a["role"] == "page"]
    assert len(pages) == 4  # two slides, one sheet, one web page


def test_a_hostile_or_odd_file_is_read_within_bounds_and_says_what_it_left_out():
    import time

    # One picture placed thousands of times is read once.
    flood = io.BytesIO()
    with zipfile.ZipFile(flood, "w") as z:
        z.writestr("ppt/presentation.xml", f'<p:presentation xmlns:p="{P}"/>')
        z.writestr("ppt/media/junk.bin", b"\0" * (1 << 20))
        blips = '<a:blip r:embed="rId1"/>' * 2000
        z.writestr("ppt/slides/slide1.xml", f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}">{blips}</p:sld>')
        z.writestr("ppt/slides/_rels/slide1.xml.rels",
                   f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Target="../media/junk.bin"/></Relationships>')
    started = time.monotonic()
    out = documents.extract_pptx(flood.getvalue())
    assert time.monotonic() - started < 2 and len(out.notes) == 1
    # Every row of a long sheet is read, so a price in row 500 is checked.
    rows = [["Plan", "Note"]] + [[f"Plan {i}", "fine"] for i in range(999)] + [["Last", "a game-changer"]]
    sheet = documents.extract_xlsx(xlsx(rows))
    assert "a game-changer" in sheet.pages[0].text and not sheet.partial
    # A hidden root, deep nesting and a flood of pictures: no crash, nothing silently dropped.
    assert documents.extract_html(b"<!DOCTYPE html><html hidden><body><p>x</p></body></html>").pages[0].text == "x"
    deep = documents.extract_html(b"<!DOCTYPE html><body>" + b"<div>" * 300 + b"Project Lumen" + b"</div>" * 300)
    assert "Project Lumen" in deep.pages[0].text
    many = documents.extract_html(b"<!DOCTYPE html><body>" + b'<img src="a.png">' * 300
                                  + b'<noscript><img src="px.gif"></noscript></body>')
    assert len(many.pages[0].alts) == documents.MAX_ALTS and many.partial
    for page in (b'<?xml version="1.0"?>\n<html xmlns="http://www.w3.org/1999/xhtml"></html>',
                 b"<!-- built --><!DOCTYPE html><p>x</p>", b"<head><title>x</title></head>"):
        assert sniff(page) == "text/html"


def test_slides_follow_the_deck_order_and_unread_parts_are_named():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("ppt/presentation.xml", f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>'
                   '<p:sldId id="256" r:id="rB"/><p:sldId id="257" r:id="rA"/></p:sldIdLst></p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels", f'<Relationships xmlns="{REL}">'
                   '<Relationship Id="rA" Target="slides/slide1.xml"/>'
                   '<Relationship Id="rB" Target="slides/slide2.xml"/>'
                   "</Relationships>")
        for n, text in ((1, "Second on screen"), (2, "First on screen"), (3, "Not in the deck")):
            z.writestr(f"ppt/slides/slide{n}.xml", f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:p><a:r><a:t>{text}</a:t>'
                       "</a:r></a:p></p:sld>")
        z.writestr("ppt/charts/chart1.xml", "<c/>")
    out = documents.extract_pptx(raw.getvalue())
    assert [(p.label, p.text) for p in out.pages] == [("slide 1", "First on screen"), ("slide 2", "Second on screen")]
    assert out.partial and any(n.startswith("charts in the file were not read") for n in out.notes)
