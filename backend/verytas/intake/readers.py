"""Readers: every kind of file a company hands over, turned into text, tables and pictures by code.

No model runs here. What a reader returns is exact and addressable (page 3, sheet "Pricing" cell C4,
slide 2), so every draft the understanding step makes can point back to where it came from, and a
reviewer can check it. Readers never execute anything in a file: Office files are opened as zip
archives and their XML parsed without entities or network access, macros and formulas are ignored
(a formula cell's cached value is read, its formula is not evaluated), and every reader is capped in
size so a hostile file costs a bounded amount of time.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from lxml import etree
from PIL import Image

from verytas.media import documents
from verytas.media.files import MediaError

MAX_TEXT = 60_000
MAX_ROWS = 2_000
MAX_COLS = 60
MAX_IMAGES = 12
MAX_XML = 20 * 1024 * 1024  # an XML part larger than this, uncompressed, is not read (zip bombs)
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=True)
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
       "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class Table:
    name: str  # the sheet, or the file
    header: list[str]
    rows: list[list[str]]
    header_row: int = 1  # 1-based row number of the header in the source, for cell addresses

    def cell(self, row: int, col: int) -> str:
        """The source address of rows[row][col], spreadsheet style ("Pricing!C4")."""
        return f"{self.name}!{_letters(col)}{self.header_row + 1 + row}"

    def preview(self, n: int = 8) -> dict[str, Any]:
        return {"name": self.name, "header": self.header, "rows": self.rows[:n], "total_rows": len(self.rows)}


@dataclass
class Reading:
    kind: str  # document | sheet | slides | data | text | image | video | audio
    text: str = ""
    pages: list[str] = field(default_factory=list)  # pages, slides or paragraphs, in order
    tables: list[Table] = field(default_factory=list)
    images: list[bytes] = field(default_factory=list)  # PNG, the item's own pictures or a document's figures
    notes: list[str] = field(default_factory=list)  # what the reader could not do, said plainly

    def preview(self) -> dict[str, Any]:
        return {"kind": self.kind, "chars": len(self.text), "pages": len(self.pages),
                "tables": [t.preview() for t in self.tables[:6]], "images": len(self.images),
                "text": self.text[:1500], "notes": self.notes}


def _letters(col: int) -> str:
    out, n = "", col + 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def sniff_text(raw: bytes) -> str | None:
    """A text format by content: JSON, CSV/TSV, or plain text. None for binary."""
    try:
        text = raw[:65536].decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw[:65536].decode("latin-1")
        except UnicodeDecodeError:  # pragma: no cover - latin-1 decodes anything
            return None
        if sum(c < " " and c not in "\t\r\n" for c in text) > len(text) / 100:
            return None
    if "\x00" in text:
        return None
    stripped = text.lstrip()
    if stripped[:1] in "[{":
        return "application/json"
    lines = [ln for ln in text.splitlines()[:20] if ln.strip()]
    if len(lines) >= 2 and len({ln.count(",") for ln in lines}) == 1 and lines[0].count(",") >= 1:
        return "text/csv"
    if len(lines) >= 2 and len({ln.count("\t") for ln in lines}) == 1 and lines[0].count("\t") >= 1:
        return "text/tab-separated-values"
    return "text/plain"


def office_kind(raw: bytes) -> str | None:
    if not raw.startswith(b"PK\x03\x04"):
        return None
    try:
        names = set(zipfile.ZipFile(io.BytesIO(raw)).namelist())
    except zipfile.BadZipFile:
        return None
    if "xl/workbook.xml" in names:
        return XLSX
    if "ppt/presentation.xml" in names:
        return PPTX
    if "word/document.xml" in names:
        return DOCX
    return None


def read(raw: bytes, media_type: str, name: str = "file") -> Reading:
    """Blocking; call through asyncio.to_thread."""
    if media_type == "application/pdf":
        return _pdf(raw)
    if media_type == DOCX:
        return _docx(raw)
    if media_type == XLSX:
        return _xlsx(raw)
    if media_type == PPTX:
        return _pptx(raw)
    if media_type in ("text/csv", "text/tab-separated-values"):
        return _csv(raw, name)
    if media_type == "application/json":
        return _json(raw, name)
    if media_type.startswith("text/"):
        text = _decode(raw)[:MAX_TEXT]
        return Reading("text", text, [p for p in re.split(r"\n\s*\n", text) if p.strip()])
    if media_type.startswith("image/"):
        return _image(raw)
    if media_type.startswith(("video/", "audio/")):
        return Reading(media_type.split("/")[0])  # read by the media step (speech and frames), not here
    return Reading("text", notes=[f"{media_type} files can't be read; export as PDF, Word, Excel or CSV"])


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _pdf(raw: bytes) -> Reading:
    try:
        book = documents.extract_pdf(raw)
    except MediaError as exc:
        return Reading("document", notes=[f"couldn't read the PDF: {exc}"])
    pages = [p.text for p in book.pages]
    out = Reading("document", "\n\n".join(pages)[:MAX_TEXT], pages)
    # Figures in the document (charts, logos, photos) are read like any picture handed over.
    out.images = [png for p in book.pages for img in p.images if (png := _as_png(img.data))][:MAX_IMAGES]
    if any(p.scanned for p in book.pages):
        out.notes.append("Some pages are scans with no text layer; their text was not read.")
    return out


def _docx(raw: bytes) -> Reading:
    try:
        book = documents.extract_docx(raw)
    except MediaError as exc:
        return Reading("document", notes=[f"couldn't read the Word file: {exc}"])
    pages = [p.text for p in book.pages]
    return Reading("document", "\n\n".join(pages)[:MAX_TEXT], pages)


def _xml(zf: zipfile.ZipFile, name: str):
    info = zf.getinfo(name)
    if info.file_size > MAX_XML:
        raise MediaError(f"{name} is too large to read")
    return etree.fromstring(zf.read(name), _PARSER)


def _xlsx(raw: bytes) -> Reading:
    out = Reading("sheet")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            for si in _xml(zf, "xl/sharedStrings.xml").iterfind("m:si", _NS):
                shared.append("".join(si.itertext()))
        book = _xml(zf, "xl/workbook.xml")
        links = _xml(zf, "xl/_rels/workbook.xml.rels").iterfind("rel:Relationship", _NS)
        rels = {r.get("Id"): r.get("Target") for r in links}
        for sheet in book.iterfind("m:sheets/m:sheet", _NS):
            target = rels.get(sheet.get(f"{{{_NS['r']}}}id"), "")
            path = "xl/" + target.lstrip("/").removeprefix("xl/")
            if path not in zf.namelist():
                continue
            grid = _sheet_grid(_xml(zf, path), shared)
            table = _table_from_grid(sheet.get("name") or "Sheet", grid)
            if table:
                out.tables.append(table)
    except (zipfile.BadZipFile, KeyError, MediaError, etree.XMLSyntaxError) as exc:
        out.notes.append(f"couldn't read the workbook: {exc}")
    out.text = "\n\n".join(_table_text(t) for t in out.tables)[:MAX_TEXT]
    if not out.tables:
        out.notes.append("No sheet had a table to read.")
    return out


def _sheet_grid(xml, shared: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for r in xml.iterfind("m:sheetData/m:row", _NS):
        if len(rows) > MAX_ROWS:
            break
        line: dict[int, str] = {}
        for c in r.iterfind("m:c", _NS):
            col = _col_index(c.get("r") or "")
            if col is None or col >= MAX_COLS:
                continue
            kind, v = c.get("t"), c.find("m:v", _NS)
            if kind == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
                value = shared[int(v.text)]
            elif kind == "inlineStr":
                value = "".join(c.find("m:is", _NS).itertext()) if c.find("m:is", _NS) is not None else ""
            elif kind == "b":
                value = "TRUE" if (v is not None and v.text == "1") else "FALSE"
            else:
                value = (v.text or "") if v is not None else ""  # numbers, and a formula's cached value
            line[col] = value.strip()
        width = max(line) + 1 if line else 0
        rows.append([line.get(i, "") for i in range(width)])
    return rows


def _col_index(ref: str) -> int | None:
    m = re.match(r"([A-Z]+)\d+$", ref)
    if not m:
        return None
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _table_from_grid(name: str, grid: list[list[str]]) -> Table | None:
    """The first row that looks like a header (mostly filled, mostly words), and the rows under it."""
    filled = [(i, row) for i, row in enumerate(grid) if sum(bool(c) for c in row) >= 2]
    if not filled:
        return None
    start, header = filled[0]
    for i, row in filled[:6]:
        words = sum(bool(c) and not _numeric(c) for c in row)
        if words >= max(2, sum(bool(c) for c in row) * 0.6):
            start, header = i, row
            break
    width = len(header)
    rows = [(r + [""] * width)[:width] for r in grid[start + 1:] if any(c for c in r)]
    header = [h or f"Column {_letters(i)}" for i, h in enumerate(header)]
    # Excel keeps dates as day numbers (46296 is 2026-10-01); in a column whose header says it holds dates,
    # show them as dates, so nobody, model or person, has to ask what the number means.
    for i, h in enumerate(header):
        if _DATE_HEADER.search(h):
            for r in rows:
                if (d := excel_date(r[i])) is not None:
                    r[i] = d.isoformat()
    return Table(name[:60], header, rows[:MAX_ROWS], header_row=start + 1)


_DATE_HEADER = re.compile(r"\b(?:date|from|to|until|valid|start|end|since|expires?|launch(?:es|ed)?)\b", re.I)


def _numeric(v: str) -> bool:
    return bool(re.fullmatch(r"[-+]?[\d,]*\.?\d+(?:[eE][-+]?\d+)?%?", v.replace(" ", "")))


def excel_date(v: str) -> date | None:
    """An Excel serial day number as a date (1900 date system), for columns that hold dates."""
    try:
        n = float(v)
    except ValueError:
        return None
    return date(1899, 12, 30) + timedelta(days=int(n)) if 20000 < n < 80000 else None


def _table_text(t: Table) -> str:
    lines = [" | ".join(t.header)] + [" | ".join(r) for r in t.rows[:200]]
    return f"[{t.name}]\n" + "\n".join(lines)


def _pptx(raw: bytes) -> Reading:
    out = Reading("slides")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        slides = sorted((n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.findall(r"\d+", n)[-1]))
        for n in slides[:200]:
            xml = _xml(zf, n)
            paras = ["".join(p.itertext()).strip() for p in xml.iter(f"{{{_NS['a']}}}p")]
            out.pages.append("\n".join(p for p in paras if p))
        for n in sorted(x for x in zf.namelist() if x.startswith("ppt/media/"))[:MAX_IMAGES]:
            if zf.getinfo(n).file_size < 15 * 1024 * 1024:
                png = _as_png(zf.read(n))
                if png:
                    out.images.append(png)
    except (zipfile.BadZipFile, KeyError, MediaError, etree.XMLSyntaxError) as exc:
        out.notes.append(f"couldn't read the slides: {exc}")
    out.text = "\n\n".join(f"[Slide {i + 1}]\n{p}" for i, p in enumerate(out.pages))[:MAX_TEXT]
    return out


def _csv(raw: bytes, name: str) -> Reading:
    text = _decode(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    grid = [row for _, row in zip(range(MAX_ROWS + 10), csv.reader(io.StringIO(text), dialect), strict=False)]
    grid = [[c.strip() for c in row[:MAX_COLS]] for row in grid]
    table = _table_from_grid(re.sub(r"\.\w+$", "", name)[:60] or "table", grid)
    out = Reading("sheet", tables=[table] if table else [])
    out.text = _table_text(table)[:MAX_TEXT] if table else ""
    if not table:
        out.notes.append("No table found in the file.")
    return out


def _json(raw: bytes, name: str) -> Reading:
    try:
        data = json.loads(_decode(raw))
    except ValueError as exc:
        return Reading("data", notes=[f"not valid JSON: {exc}"])
    rows = data
    if isinstance(data, dict):
        # An API envelope ({"data": [...]}, {"results": [...]}): the first list of records inside it.
        rows = next((v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)), None)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        keys = list(dict.fromkeys(k for r in rows[:MAX_ROWS] if isinstance(r, dict) for k in r))[:MAX_COLS]
        table = Table(re.sub(r"\.\w+$", "", name)[:60] or "data", [str(k) for k in keys],
                      [[_cell(r.get(k)) for k in keys] for r in rows[:MAX_ROWS] if isinstance(r, dict)], header_row=0)
        return Reading("data", _table_text(table)[:MAX_TEXT], tables=[table])
    text = json.dumps(data, ensure_ascii=False, indent=1)[:MAX_TEXT]
    return Reading("data", text, notes=["No list of records found; read as text."])


def _cell(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)[:200]
    return "" if v is None else str(v)[:500]


def _as_png(raw: bytes) -> bytes | None:
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:  # noqa: BLE001, a picture that won't open is skipped, not fatal
        return None
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def _image(raw: bytes) -> Reading:
    png = _as_png(raw)
    if png is None:
        return Reading("image", notes=["The image could not be opened."])
    out = Reading("image", images=[png])
    try:
        from verytas.media import ocr

        result = ocr.read(Image.open(io.BytesIO(png)))
        out.text = "\n".join(line.text for line in result.lines)[:MAX_TEXT]
    except Exception as exc:  # noqa: BLE001, no OCR engine (tests, a lean server): the picture is still seen
        out.notes.append(f"local OCR unavailable: {type(exc).__name__}")
    return out
