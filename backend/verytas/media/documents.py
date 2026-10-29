"""PDF, Word, PowerPoint, Excel and HTML extraction, page by page (a slide, a sheet and a web page are pages).

Real-world PDFs are rarely clean. One file can mix pages with a proper text
layer, pages that are a scanned photo (no selectable text at all) and pages
with screenshots pasted on top of real text. So each page reports its own
text layer, its embedded images, and whether it needs to be rendered and read
by OCR. Text drawn as vector outlines has no text layer either: on a page with
almost no text it is caught by the "too little text, render it" rule, and on a
page that also has real text, by rendering any page that draws vector shapes,
so the review can read what is in the picture but not in the text layer.

A small file can still be a bomb: a 3 KB PDF can declare pages a metre wide,
a 300 KB Word file can inflate to 90 MB of XML. So every expensive step has a
budget (render pixels, decoded image pixels, extracted characters), renders
and images are kept compressed until a page agent needs them, and anything
cut by a budget is reported as a partial read, never passed over in silence.
"""

from __future__ import annotations

import io
import logging
import re
import threading
import zipfile
import zlib
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from verytas.media.files import MAX_HTML_BYTES, WORK_SIDE, MediaError, flatten, shrink

log = logging.getLogger("verytas.media")

MAX_PAGES = 40
MAX_IMAGES_PER_PAGE = 12
MAX_IMAGES_TOTAL = 30
MIN_IMAGE_SIDE = 48  # icons and rules below this carry no checkable content
# A page with fewer visible characters than this is treated as scanned.
SCANNED_CHARS = 25
RENDER_SCALE = 2.0  # about 144 dpi: enough for OCR, small enough to stay fast
# A page with real text that draws any vector shape is rendered as well: outlined text and drawn artwork
# exist only as shapes, and a whole outlined headline can be a single one. Up to this many pages per
# document; past it the rest are reported as partly read.
DRAWN_RENDERS = 20
# Shapes inside nested forms count too, down to this depth.
SHAPE_DEPTH = 12
# OCR works at WORK_SIDE anyway, so a page render never needs more than this.
MAX_RENDER_PIXELS = 4_000_000
MAX_EMBEDDED_PIXELS = 16_000_000  # one embedded image, as decoded
DOC_PIXEL_BUDGET = 160_000_000  # everything decoded from one document
MAX_DOC_CHARS = 200_000  # text kept from one document, about 60 dense pages
MAX_DOCX_UNZIPPED = 40 * 1024 * 1024
MAX_DOCX_PART = 10 * 1024 * 1024  # one XML part (the body, a header)
BLANK_STD = 2.0  # grey-level spread under which a render is an empty page

# pdfium is not thread-safe, even across separate documents. Taken per page,
# not per document, so one long PDF doesn't block every other upload.
_PDFIUM = threading.Lock()


@dataclass
class EmbeddedImage:
    index: int
    data: bytes  # PNG, already shrunk to WORK_SIDE
    box: tuple[float, float, float, float] | None = None  # page coordinates, points
    area_share: float = 0.0

    @property
    def image(self) -> Image.Image:
        return Image.open(io.BytesIO(self.data)).convert("RGB")


@dataclass
class Page:
    number: int  # 1-based, as people say it
    text: str
    images: list[EmbeddedImage] = field(default_factory=list)
    scanned: bool = False
    render_jpeg: bytes | None = None  # set when the page needs OCR
    # Set when a page with a text layer also draws vector shapes: what is drawn may say more than the layer.
    graphics_jpeg: bytes | None = None
    label: str | None = None  # how people name it when it is not a page: "slide 3", "sheet Prices"
    # Pictures a web page shows, as alt-text checks read them: {"id", "alt", "decorative"}.
    alts: list[dict] = field(default_factory=list)

    @property
    def render(self) -> Image.Image | None:
        return Image.open(io.BytesIO(self.render_jpeg)).convert("RGB") if self.render_jpeg else None


@dataclass
class Extracted:
    kind: str  # pdf | docx | pptx | xlsx | html
    pages: list[Page]
    page_count: int
    notes: list[str] = field(default_factory=list)
    partial: bool = False  # some text or images were left unread by a cap


class _Budget:
    def __init__(self) -> None:
        self.pixels = DOC_PIXEL_BUDGET
        self.chars = MAX_DOC_CHARS
        self.images = MAX_IMAGES_TOTAL
        self.drawn = DRAWN_RENDERS

    def take_pixels(self, n: int) -> bool:
        if n > self.pixels:
            return False
        self.pixels -= n
        return True

    def text(self, s: str) -> tuple[str, bool]:
        if len(s) <= self.chars:
            self.chars -= len(s)
            return s, False
        kept, self.chars = s[:self.chars], 0
        return kept, True


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    shrink(img, WORK_SIDE).save(buf, "PNG", compress_level=1)
    return buf.getvalue()


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _blank(img: Image.Image) -> bool:
    import numpy as np

    return float(np.asarray(shrink(img, 400).convert("L")).std()) < BLANK_STD


def extract_pdf(raw: bytes) -> Extracted:
    import pypdfium2 as pdfium

    with _PDFIUM:
        try:
            pdf = pdfium.PdfDocument(raw)
        except pdfium.PdfiumError as exc:
            log.info("PDF would not open: %s", exc)
            raise MediaError("PDF could not be opened; encrypted or damaged files need a human look") from exc
        count = len(pdf)
    try:
        return _read_pdf(pdf, pdfium, count)
    finally:
        with _PDFIUM:
            pdf.close()


def _read_pdf(pdf, pdfium, count: int) -> Extracted:
    out = Extracted("pdf", [], count)
    if count > MAX_PAGES:
        out.notes.append(f"only the first {MAX_PAGES} of {count} pages were checked")
        out.partial = True
    budget = _Budget()
    for i in range(min(count, MAX_PAGES)):
        with _PDFIUM:
            page_out = _read_page(pdf, pdfium, i, budget, out)
        out.pages.append(page_out)
        if budget.chars == 0 and i + 1 < min(count, MAX_PAGES):
            out.notes.append(f"text stops after page {i + 1}: the document's text budget "
                             f"({MAX_DOC_CHARS:,} characters) was reached")
            out.partial = True
            break
    return out


def _read_page(pdf, pdfium, i: int, budget: _Budget, out: Extracted) -> Page:
    page = pdf[i]
    try:
        width, height = page.get_size()
        textpage = page.get_textpage()
        text = textpage.get_text_bounded() or ""
        textpage.close()
        text, cut = budget.text(text)
        if cut:
            out.notes.append(f"page {i + 1}: text cut at the document's {MAX_DOC_CHARS:,}-character budget")
            out.partial = True

        visible = sum(1 for c in text if not c.isspace())
        if visible < SCANNED_CHARS:
            # Render the whole page rather than trusting the images: a scan
            # can be split into strips, and vector-outlined text has none.
            # A page can declare any size, so the render is capped in pixels.
            scale = min(RENDER_SCALE, (MAX_RENDER_PIXELS / max(1.0, width * height)) ** 0.5)
            px = int(width * scale) * int(height * scale)
            if not budget.take_pixels(px):
                out.notes.append(f"page {i + 1}: not rendered, the document's image budget was reached")
                out.partial = True
                return Page(i + 1, text, [], True, None)
            render = flatten(page.render(scale=scale).to_pil())
            if _blank(render) and not text.strip():
                out.notes.append(f"page {i + 1} is blank")
                return Page(i + 1, text, [], False, None)
            return Page(i + 1, text, [], True, _jpeg(render))

        images: list[EmbeddedImage] = []
        for k, obj in enumerate(page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,), max_depth=4)):
            if len(images) >= MAX_IMAGES_PER_PAGE or budget.images <= 0:
                out.notes.append(f"page {i + 1}: some images were skipped (limit reached)")
                out.partial = True
                break
            try:
                pw, ph = obj.get_px_size()
                if min(pw, ph) < MIN_IMAGE_SIDE:
                    continue
                if pw * ph > MAX_EMBEDDED_PIXELS or not budget.take_pixels(pw * ph):
                    out.notes.append(f"page {i + 1}: an image of {pw}x{ph} was too large to check")
                    out.partial = True
                    continue
                left, bottom, right, top = obj.get_bounds()
                pil = obj.get_bitmap(render=True).to_pil()
            except pdfium.PdfiumError:
                continue
            if min(pil.size) < MIN_IMAGE_SIDE:
                continue
            share = max(0.0, (right - left) * (top - bottom)) / max(1.0, width * height)
            images.append(EmbeddedImage(k + 1, _png(flatten(pil)), (left, bottom, right, top), round(share, 3)))
            budget.images -= 1
        return Page(i + 1, text, images, False, None, _graphics(page, pdfium, i, width, height, budget, out))
    finally:
        page.close()


def _graphics(page, pdfium, i: int, width: float, height: float, budget: _Budget, out: Extracted) -> bytes | None:
    """A render of the page when it draws vector shapes that could hide text or artwork, else None.

    Placed images are painted out of the render: they are read as images on their own, and reading them
    again here would report a screenshot's text twice."""
    if next(iter(page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_PATH,), max_depth=SHAPE_DEPTH)), None) is None:
        return None
    if budget.drawn <= 0:
        out.notes.append(f"page {i + 1}: drawn shapes not read, {DRAWN_RENDERS} pages per document are")
        out.partial = True
        return None
    scale = min(RENDER_SCALE, (MAX_RENDER_PIXELS / max(1.0, width * height)) ** 0.5)
    if not budget.take_pixels(int(width * scale) * int(height * scale)):
        out.notes.append(f"page {i + 1}: drawn shapes not read, the document's image budget was reached")
        out.partial = True
        return None
    budget.drawn -= 1
    render = flatten(page.render(scale=scale).to_pil())
    paint = ImageDraw.Draw(render)
    for obj in page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,), max_depth=SHAPE_DEPTH):
        try:
            left, bottom, right, top = obj.get_bounds()
        except pdfium.PdfiumError:
            continue
        paint.rectangle([left * scale, (height - top) * scale, right * scale, (height - bottom) * scale], fill="white")
    return _jpeg(render)


# --- Word ---------------------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
# Everything a reader of the file can see or recover, not just the body:
# headers and footers repeat on every page, comments and tracked deletions
# travel with the file to whoever it is sent to.
_DOCX_PARTS = (("word/document.xml", None), ("word/header", "Header"), ("word/footer", "Footer"),
               ("word/footnotes.xml", "Footnote"), ("word/endnotes.xml", "Endnote"),
               ("word/comments.xml", "Comment"))


def extract_docx(raw: bytes) -> Extracted:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise MediaError("not a readable Word file") from exc
    with zf:
        infos = zf.infolist()
        if sum(info.file_size for info in infos) > MAX_DOCX_UNZIPPED:
            raise MediaError(f"Word file expands to more than {MAX_DOCX_UNZIPPED // 1024 // 1024} MB; refused")
        names = {info.filename: info for info in infos}
        if "word/document.xml" not in names:
            raise MediaError("not a readable Word file")
        out = Extracted("docx", [], 1)
        budget = _Budget()
        sections: list[str] = []
        for prefix, label in _DOCX_PARTS:
            for name in sorted(n for n in names if n == prefix or (n.startswith(prefix) and n.endswith(".xml"))):
                if names[name].file_size > MAX_DOCX_PART:
                    out.notes.append(f"{name} is over {MAX_DOCX_PART // 1024 // 1024} MB and was not read")
                    out.partial = True
                    continue
                if budget.chars == 0:
                    break  # already noted when the budget ran out
                try:
                    body, deleted = _docx_text(zf.read(name))
                except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
                    out.notes.append(f"{name} is damaged and was not read ({type(exc).__name__})")
                    out.partial = True
                    continue
                for text, tag in ((body, label), (deleted, "Deleted text (tracked change)")):
                    if not text.strip() or budget.chars == 0:
                        continue
                    kept, cut = budget.text(text)
                    sections.append(kept if tag is None else f"[{tag}] {kept}")
                    if cut:
                        out.notes.append(f"text cut at {MAX_DOC_CHARS:,} characters")
                        out.partial = True
        images = _docx_images(zf, names, budget, out)
    # Word has no fixed pages; the whole file is one logical page.
    out.pages = [Page(1, "\n\n".join(sections), images)]
    return out


def _docx_text(xml: bytes) -> tuple[str, str]:
    """(visible text, tracked-deleted text) of one WordprocessingML part, a paragraph per line.

    Paragraphs nested in text boxes and table cells are read as their own
    paragraphs, so a text box's words aren't glued onto the paragraph that
    anchors it. The parser refuses entities and network access.
    """
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)
    try:
        root = etree.fromstring(xml, parser)
    except etree.XMLSyntaxError as exc:
        raise MediaError("Word file has a damaged part") from exc
    body, deleted = [], []
    for p in root.iter(f"{_W}p"):
        # A text box is stored twice, as DrawingML (mc:Choice) and as a VML copy for old readers
        # (mc:Fallback). Reading both would double its words, and every finding in them.
        if next(p.iterancestors(f"{_MC}Fallback"), None) is not None:
            continue
        shown, gone = [], []
        for el in p.iter(f"{_W}t", f"{_W}delText", f"{_W}tab", f"{_W}br"):
            if next(el.iterancestors(f"{_W}p"), None) is not p:
                continue  # belongs to a nested paragraph (text box), read on its own
            if el.tag == f"{_W}delText":
                gone.append(el.text or "")
            elif el.tag == f"{_W}t":
                shown.append(el.text or "")
            else:
                shown.append("\t" if el.tag == f"{_W}tab" else "\n")
        if "".join(shown).strip():
            body.append("".join(shown))
        if "".join(gone).strip():
            deleted.append("".join(gone))
    return "\n".join(body), "\n".join(deleted)


def _docx_images(zf: zipfile.ZipFile, names: dict, budget: _Budget, out: Extracted) -> list[EmbeddedImage]:
    images: list[EmbeddedImage] = []
    for k, name in enumerate(sorted(n for n in names if n.startswith("word/media/")), start=1):
        if budget.images <= 0:
            out.notes.append("some images were skipped (limit reached)")
            out.partial = True
            break
        try:
            pil = Image.open(io.BytesIO(zf.read(name)))
            pw, ph = pil.size
            if min(pw, ph) < MIN_IMAGE_SIDE:
                continue
            if pw * ph > MAX_EMBEDDED_PIXELS or not budget.take_pixels(pw * ph):
                out.notes.append(f"an image of {pw}x{ph} was too large to check")
                out.partial = True
                continue
            pil.draft("RGB", (WORK_SIDE, WORK_SIDE))  # JPEG decodes straight to a smaller size
            pil.load()
        except Image.DecompressionBombError:
            out.notes.append(f"{name.rsplit('/', 1)[-1]} was too large to check")
            out.partial = True
            continue
        except Exception:  # noqa: BLE001, one malformed image (a bad EMF divides by zero in PIL) skips itself
            # Vector formats (SVG, EMF, WMF) and anything else PIL can't draw can carry text and artwork: say
            # so, never pass the document as fully read.
            out.notes.append(f"{name.rsplit('/', 1)[-1]}: an image in a format that can't be read here")
            out.partial = True
            continue
        images.append(EmbeddedImage(k, _png(flatten(pil))))
        budget.images -= 1
    return images


# --- PowerPoint ------------------------------------------------------------------------------------------

_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
MAX_SLIDES = 60


def _office_zip(raw: bytes, what: str, required: str) -> tuple[zipfile.ZipFile, dict]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise MediaError(f"not a readable {what} file") from exc
    infos = {info.filename: info for info in zf.infolist()}
    if sum(info.file_size for info in infos.values()) > MAX_DOCX_UNZIPPED:
        zf.close()
        raise MediaError(f"{what} file expands to more than {MAX_DOCX_UNZIPPED // 1024 // 1024} MB; refused")
    if required not in infos:
        zf.close()
        raise MediaError(f"not a readable {what} file")
    return zf, infos


def _xml(zf: zipfile.ZipFile, infos: dict, name: str, out: Extracted):
    """One XML part, parsed without entities or network; None (and a note) when it is too big or damaged."""
    from lxml import etree

    if infos[name].file_size > MAX_DOCX_PART:
        out.notes.append(f"{name} is over {MAX_DOCX_PART // 1024 // 1024} MB and was not read")
        out.partial = True
        return None
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)
    try:
        return etree.fromstring(zf.read(name), parser)
    except (etree.XMLSyntaxError, zipfile.BadZipFile, zlib.error, EOFError):
        out.notes.append(f"{name} is damaged and was not read")
        out.partial = True
        return None


def _rel_targets(zf: zipfile.ZipFile, infos: dict, part: str, out: Extracted) -> dict[str, str]:
    """Relationship id -> zip path, for a part's own .rels file."""
    folder, _, leaf = part.rpartition("/")
    rels = f"{folder}/_rels/{leaf}.rels"
    if rels not in infos:
        return {}
    root = _xml(zf, infos, rels, out)
    if root is None:
        return {}
    targets = {}
    for rel in root.iter(f"{_REL}Relationship"):
        target = rel.get("Target") or ""
        if rel.get("TargetMode") == "External":
            continue  # a linked picture on the web is not fetched
        path = target.lstrip("/") if target.startswith("/") else _join(folder, target)
        targets[rel.get("Id")] = path
    return targets


def _join(folder: str, target: str) -> str:
    parts = folder.split("/")
    for piece in target.split("/"):
        if piece == "..":
            parts = parts[:-1]
        elif piece and piece != ".":
            parts.append(piece)
    return "/".join(parts)


def _picture(zf: zipfile.ZipFile, infos: dict, name: str, index: int, budget: _Budget,
             out: Extracted) -> EmbeddedImage | None:
    """One embedded picture, shrunk and budgeted as Word's are."""
    if name not in infos or budget.images <= 0:
        if budget.images <= 0:
            out.notes.append("some images were skipped (limit reached)")
            out.partial = True
        return None
    try:
        pil = Image.open(io.BytesIO(zf.read(name)))
        pw, ph = pil.size
        if min(pw, ph) < MIN_IMAGE_SIDE:
            return None
        if pw * ph > MAX_EMBEDDED_PIXELS or not budget.take_pixels(pw * ph):
            out.notes.append(f"an image of {pw}x{ph} was too large to check")
            out.partial = True
            return None
        pil.draft("RGB", (WORK_SIDE, WORK_SIDE))
        pil.load()
    except Image.DecompressionBombError:
        out.notes.append(f"{name.rsplit('/', 1)[-1]} was too large to check")
        out.partial = True
        return None
    except Exception:  # noqa: BLE001, as in Word: an unreadable picture is reported, never passed over
        out.notes.append(f"{name.rsplit('/', 1)[-1]}: an image in a format that can't be read here")
        out.partial = True
        return None
    budget.images -= 1
    return EmbeddedImage(index, _png(flatten(pil)))


def extract_pptx(raw: bytes) -> Extracted:
    """A deck, one page per slide in the deck's own order: its text in reading order, its pictures, and its
    speaker notes, which travel with the file to whoever it is sent to (as Word's comments do)."""
    zf, infos = _office_zip(raw, "PowerPoint", "ppt/presentation.xml")
    out = Extracted("pptx", [], 0)
    budget = _Budget()
    with zf:
        slides = _deck_order(zf, infos, out)
        out.page_count = len(slides)
        if len(slides) > MAX_SLIDES:
            out.notes.append(f"only the first {MAX_SLIDES} of {len(slides)} slides were read")
            out.partial = True
        _unread_parts(infos, out, {"ppt/charts/": "charts", "ppt/diagrams/": "SmartArt", "ppt/comments/": "comments"})
        # A picture is read once per deck, however many times slides place it (a logo on every slide, or a
        # crafted file pointing ten thousand placements at one part); failures count against the budget too.
        seen: dict[str, EmbeddedImage | None] = {}
        for number, name in enumerate(slides[:MAX_SLIDES], start=1):
            root = _xml(zf, infos, name, out)
            if root is None:
                continue
            rels = _rel_targets(zf, infos, name, out)
            lines = ["".join(t.text or "" for t in p.iter(f"{_A}t")).strip() for p in root.iter(f"{_A}p")]
            text = "\n".join(ln for ln in lines if ln)
            notes_part = next((t for t in rels.values() if "notesSlide" in t and t in infos), None)
            if notes_part is not None and (notes := _xml(zf, infos, notes_part, out)) is not None:
                said = [ln for p in notes.iter(f"{_A}p")
                        if (ln := "".join(t.text or "" for t in p.iter(f"{_A}t")).strip()) and not ln.isdigit()]
                if said:
                    text += "\n[Speaker notes] " + " ".join(said)
            if root.get("show") == "0":
                text = "[Hidden slide] " + text
            kept, cut = budget.text(text)
            if cut:
                out.notes.append(f"text cut at {MAX_DOC_CHARS:,} characters")
                out.partial = True
            targets = list(dict.fromkeys(t for blip in root.iter(f"{_A}blip") if (t := rels.get(blip.get(_R_EMBED)))))
            images = []
            for k, target in enumerate(targets, start=1):
                if target in seen or len(images) >= MAX_IMAGES_PER_PAGE:
                    continue
                if len(seen) >= 2 * MAX_IMAGES_TOTAL:
                    out.notes.append("some pictures were not read (too many in one deck)")
                    out.partial = True
                    break
                seen[target] = img = _picture(zf, infos, target, k, budget, out)
                if img is not None:
                    images.append(img)
            out.pages.append(Page(number, kept, images, label=f"slide {number}"))
    out.notes = list(dict.fromkeys(out.notes))
    return out


def _deck_order(zf: zipfile.ZipFile, infos: dict, out: Extracted) -> list[str]:
    """Slide parts in the order the deck shows them (presentation.xml's slide list), so "slide 3" in a finding
    is the third slide people see. A slide part the deck does not list is not part of it."""
    listed = []
    root = _xml(zf, infos, "ppt/presentation.xml", out)
    if root is not None:
        rels = _rel_targets(zf, infos, "ppt/presentation.xml", out)
        listed = [t for s in root.iter(f"{_P}sldId") if (t := rels.get(s.get(_R_ID))) and t in infos]
    if listed:
        return list(dict.fromkeys(listed))
    # No slide list to go by (a hand-made or damaged file): the part names' own numbering.
    return sorted((n for n in infos if _SLIDE.fullmatch(n)), key=lambda n: int(_SLIDE.fullmatch(n)[1]))


def _unread_parts(infos: dict, out: Extracted, kinds: dict[str, str]) -> None:
    """Say which parts were not read, so a deck with a chart is never passed as fully checked."""
    found = [label for prefix, label in kinds.items() if any(n.startswith(prefix) for n in infos)]
    if found:
        out.notes.append(f"{', '.join(found)} in the file were not read; check them by eye or attach them as images")
        out.partial = True


_R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_SLIDE = re.compile(r"ppt/slides/slide(\d+)\.xml")


# --- Excel -----------------------------------------------------------------------------------------------

def extract_xlsx(raw: bytes) -> Extracted:
    """A workbook, one page per sheet, each read as its table (header then every row), with its pictures.
    Cells are read by the same bounded reader Intake uses; whatever its caps leave out is reported."""
    from verytas.intake import readers

    zf, infos = _office_zip(raw, "Excel", "xl/workbook.xml")
    with zf:
        reading = readers.read(raw, readers.XLSX, "workbook")
        out = Extracted("xlsx", [], len(reading.tables), notes=list(reading.notes))
        out.partial = bool(reading.notes)
        _unread_parts(infos, out, {"xl/charts/": "charts", "xl/comments": "comments", "xl/threadedComments/":
                                   "comments"})
        budget = _Budget()
        for number, table in enumerate(reading.tables, start=1):
            if len(table.rows) >= readers.MAX_ROWS:
                out.notes.append(f"sheet {table.name}: only the first {readers.MAX_ROWS:,} rows were read")
                out.partial = True
            lines = [f"[{table.name}]", " | ".join(table.header), *(" | ".join(r) for r in table.rows)]
            kept, cut = budget.text("\n".join(lines))
            if cut:
                out.notes.append(f"text cut at {MAX_DOC_CHARS:,} characters")
                out.partial = True
            out.pages.append(Page(number, kept, label=f"sheet {table.name}"))
        images = []
        for k, name in enumerate(sorted(n for n in infos if n.startswith("xl/media/")), start=1):
            if len(images) >= MAX_IMAGES_PER_PAGE or k > 2 * MAX_IMAGES_TOTAL:
                out.notes.append("some pictures were not read (too many in one workbook)")
                out.partial = True
                break
            if (img := _picture(zf, infos, name, k, budget, out)) is not None:
                images.append(img)
    if images:
        # Which sheet shows a picture takes the drawing parts to tell; the pictures are checked all the same.
        if not out.pages:
            out.pages.append(Page(1, "", label="workbook"))
        out.pages[0].images.extend(images)
    return out


# --- HTML ------------------------------------------------------------------------------------------------

MAX_ALTS = 200  # pictures on one page whose alt text is checked; past this the page is said to be partly read
_HIDDEN_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "object", "embed", "head")
_BLOCKS = {"p", "div", "section", "article", "header", "footer", "aside", "nav", "main", "li", "ul", "ol",
           "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "blockquote", "figcaption", "figure", "br", "hr",
           "button", "label", "dt", "dd", "pre", "form"}


def extract_html(raw: bytes) -> Extracted:
    """A web page or an HTML email as one page: the visible text, the title and share text people see in a
    link preview, inline (data:) pictures, and every picture's alt text for the accessibility checks.
    Nothing is fetched: linked pictures, styles and scripts stay where they are, and the page says so."""
    import base64
    import binascii

    from lxml import etree, html

    if len(raw) > MAX_HTML_BYTES:
        raise MediaError(f"HTML file is over {MAX_HTML_BYTES // 1024 // 1024} MB; refused")
    out = Extracted("html", [], 1)
    try:
        # huge_tree: libxml2 otherwise stops at 256 levels and drops the rest without a word, while a browser
        # still shows it, so deep nesting could hide text from review. The 5 MB cap bounds the cost.
        root = html.document_fromstring(raw, parser=html.HTMLParser(no_network=True, remove_comments=True,
                                                                    remove_pis=True, huge_tree=True))
    except (etree.ParserError, ValueError) as exc:
        raise MediaError("not a readable HTML file") from exc
    preview = []
    if (title := root.findtext(".//title")) and title.strip():
        preview.append(f"[Page title] {title.strip()}")
    for meta in root.iter("meta"):
        key = (meta.get("name") or meta.get("property") or "").lower()
        value = (meta.get("content") or "").strip()
        if value and key in ("description", "og:title", "og:description", "twitter:title", "twitter:description"):
            preview.append(f"[{key}] {value}")
    # What the page hides is not checked, its pictures included (a tracking pixel in <noscript>).
    for bad in list(root.iter(*_HIDDEN_TAGS)):
        bad.drop_tree()
    for el in list(root.iter()):
        if el is root or not isinstance(el.tag, str):
            continue
        if el.get("hidden") is not None or el.get("aria-hidden") == "true" or "display:none" in (
                el.get("style") or "").replace(" ", "").lower():
            el.drop_tree()
    budget = _Budget()
    images, alts, linked = [], [], 0
    for k, img in enumerate(root.iter("img"), start=1):
        if k > MAX_ALTS:
            out.notes.append(f"only the first {MAX_ALTS} pictures were checked")
            out.partial = True
            break
        alt = img.get("alt")
        # alt="" is how a page marks a picture decorative; a missing alt is the problem.
        decorative = alt == "" or img.get("role") == "presentation"
        alts.append({"id": str(k), "alt": alt or "", "decorative": decorative})
        src = (img.get("src") or "").strip()
        if not src.startswith("data:image/"):
            linked += not decorative  # a spacer or a flourish is nothing to check
            continue
        try:
            data = base64.b64decode(src.split(",", 1)[1], validate=False)
        except (IndexError, binascii.Error, ValueError):
            continue
        if len(images) < MAX_IMAGES_PER_PAGE and (pic := _data_picture(data, k, budget, out)) is not None:
            images.append(pic)
    for el in root.iter(*_BLOCKS):
        el.tail = "\n" + (el.tail or "")
    lines = [" ".join(ln.split()) for ln in (root.text_content() or "").splitlines()]
    body = "\n".join(ln for ln in lines if ln)
    kept, cut = budget.text("\n".join([*preview, body]))
    if cut:
        out.notes.append(f"text cut at {MAX_DOC_CHARS:,} characters")
        out.partial = True
    if linked:
        out.notes.append(f"{linked} linked picture(s) were not fetched; attach them as images to check them")
        out.partial = True
    out.pages.append(Page(1, kept, images, label="the page", alts=alts))
    return out


def _data_picture(data: bytes, index: int, budget: _Budget, out: Extracted) -> EmbeddedImage | None:
    try:
        pil = Image.open(io.BytesIO(data))
        pw, ph = pil.size
        if min(pw, ph) < MIN_IMAGE_SIDE:
            return None
        if pw * ph > MAX_EMBEDDED_PIXELS or not budget.take_pixels(pw * ph):
            out.notes.append(f"an inline picture of {pw}x{ph} was too large to check")
            out.partial = True
            return None
        pil.load()
    except Exception:  # noqa: BLE001, a broken inline picture is reported, never passed over
        out.notes.append(f"inline picture {index} could not be read")
        out.partial = True
        return None
    budget.images -= 1
    return EmbeddedImage(index, _png(flatten(pil)))
