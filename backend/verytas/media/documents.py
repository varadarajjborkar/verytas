"""PDF and Word extraction, page by page.

Real-world PDFs are rarely clean. One file can mix pages with a proper text
layer, pages that are a scanned photo (no selectable text at all) and pages
with screenshots pasted on top of real text. So each page reports its own
text layer, its embedded images, and whether it needs to be rendered and read
by OCR. Text drawn as vector outlines has no text layer either; it is caught
by the same "too little text, render it" rule.

A small file can still be a bomb: a 3 KB PDF can declare pages a metre wide,
a 300 KB Word file can inflate to 90 MB of XML. So every expensive step has a
budget (render pixels, decoded image pixels, extracted characters), renders
and images are kept compressed until a page agent needs them, and anything
cut by a budget is reported as a partial read, never passed over in silence.
"""

from __future__ import annotations

import io
import threading
import zipfile
from dataclasses import dataclass, field

from PIL import Image

from verytas.media.files import WORK_SIDE, MediaError, flatten, shrink

MAX_PAGES = 40
MAX_IMAGES_PER_PAGE = 12
MAX_IMAGES_TOTAL = 30
MIN_IMAGE_SIDE = 48  # icons and rules below this carry no checkable content
# A page with fewer visible characters than this is treated as scanned.
SCANNED_CHARS = 25
RENDER_SCALE = 2.0  # about 144 dpi: enough for OCR, small enough to stay fast
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

    @property
    def render(self) -> Image.Image | None:
        return Image.open(io.BytesIO(self.render_jpeg)).convert("RGB") if self.render_jpeg else None


@dataclass
class Extracted:
    kind: str  # pdf | docx
    pages: list[Page]
    page_count: int
    notes: list[str] = field(default_factory=list)
    partial: bool = False  # some text or images were left unread by a cap


class _Budget:
    def __init__(self) -> None:
        self.pixels = DOC_PIXEL_BUDGET
        self.chars = MAX_DOC_CHARS
        self.images = MAX_IMAGES_TOTAL

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
            raise MediaError(f"PDF could not be opened ({exc}); encrypted or damaged files need a human look") from exc
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
        return Page(i + 1, text, images, False, None)
    finally:
        page.close()


# --- Word ---------------------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
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
                body, deleted = _docx_text(zf.read(name))
                for text, tag in ((body, label), (deleted, "Deleted text (tracked change)")):
                    if not text.strip():
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
        except (OSError, ValueError, Image.DecompressionBombError):
            continue
        images.append(EmbeddedImage(k, _png(flatten(pil))))
        budget.images -= 1
    return images
