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
from verytas.media.files import MediaError, open_image

MAX_TEXT = 60_000
MAX_ROWS = 2_000
MAX_COLS = 60
MAX_IMAGES = 12
MAX_XML = 20 * 1024 * 1024  # an XML part larger than this, uncompressed, is not read (zip bombs)
# What one file may make us parse in all: a workbook can list hundreds of sheets that point at one big part.
MAX_XML_TOTAL = 60 * 1024 * 1024
MAX_SHEETS = 20
# A cell longer than this is cut. Shared strings let one 2 MB string fill every cell of a sheet for a few
# bytes each, and every copy is joined into the text and the stored preview.
MAX_CELL = 500
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
    # 1-based source row of each entry in rows, when blank rows were skipped; None means contiguous.
    lines: list[int] | None = None

    def cell(self, row: int, col: int) -> str:
        """The source address of rows[row][col], spreadsheet style ("Pricing!C4")."""
        line = self.lines[row] if self.lines is not None and row < len(self.lines) else self.header_row + 1 + row
        return f"{self.name}!{_letters(col)}{line}"

    def preview(self, n: int = 8) -> dict[str, Any]:
        return {"name": self.name, "header": [h[:120] for h in self.header],
                "rows": [[c[:120] for c in r] for r in self.rows[:n]], "total_rows": len(self.rows)}


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
    # "[Draft] Always write..." starts with a bracket too: only text that parses (or, cut at the sniffing
    # window, starts like a JSON value) is data. _json falls back to text when it does not parse anyway.
    cut = len(raw) > 65536 and re.match(r'[\[{]\s*["{\[\d-]', stripped)
    if stripped and stripped[0] in "[{" and (cut or _parses(text)):
        return "application/json"
    lines = [ln for ln in text.splitlines()[:20] if ln.strip()]
    if len(lines) >= 2 and len({ln.count(",") for ln in lines}) == 1 and lines[0].count(",") >= 1:
        return "text/csv"
    if len(lines) >= 2 and len({ln.count("\t") for ln in lines}) == 1 and lines[0].count("\t") >= 1:
        return "text/tab-separated-values"
    return "text/plain"


def _parses(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


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


class _Budget:
    """Uncompressed XML bytes one file may still make us parse."""

    def __init__(self, total: int = MAX_XML_TOTAL):
        self.left = total

    def xml(self, zf: zipfile.ZipFile, name: str):
        size = zf.getinfo(name).file_size
        if size > MAX_XML:
            raise MediaError(f"{name} is too large to read")
        if size > self.left:
            raise MediaError("the file has more to read than one item may take; split it")
        self.left -= size
        return etree.fromstring(zf.read(name), _PARSER)


def _xlsx(raw: bytes) -> Reading:
    out = Reading("sheet")
    budget = _Budget()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        names = set(zf.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in budget.xml(zf, "xl/sharedStrings.xml").iterfind("m:si", _NS):
                shared.append("".join(si.itertext())[:MAX_CELL])
        dates = _date_styles(budget.xml(zf, "xl/styles.xml")) if "xl/styles.xml" in names else None
        book = budget.xml(zf, "xl/workbook.xml")
        links = budget.xml(zf, "xl/_rels/workbook.xml.rels").iterfind("rel:Relationship", _NS)
        rels = {r.get("Id"): r.get("Target") for r in links}
        seen: set[str] = set()
        for sheet in book.iterfind("m:sheets/m:sheet", _NS):
            target = rels.get(sheet.get(f"{{{_NS['r']}}}id"), "")
            path = "xl/" + target.lstrip("/").removeprefix("xl/")
            if path not in names or path in seen:
                continue
            seen.add(path)
            if len(seen) > MAX_SHEETS:
                out.notes.append(f"Only the first {MAX_SHEETS} sheets were read.")
                break
            grid = _sheet_grid(budget.xml(zf, path), shared, dates)
            # A workbook without a styles part (written by a script, not Excel) says nothing about which
            # numbers are dates; then a column headed plainly as a date is the only hint left.
            table = _table_from_grid(sheet.get("name") or "Sheet", grid, header_dates=dates is None)
            if table:
                out.tables.append(table)
    except (zipfile.BadZipFile, KeyError, MediaError, etree.XMLSyntaxError) as exc:
        out.notes.append(f"couldn't read the workbook: {exc}")
    out.text = "\n\n".join(_table_text(t) for t in out.tables)[:MAX_TEXT]
    if not out.tables:
        out.notes.append("No sheet had a table to read.")
    return out


# Excel's built-in number formats that show a date or time.
_DATE_FORMATS = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}


def _date_styles(xml) -> set[int]:
    """Indexes of the cell styles (the `s` attribute) whose number format shows a date."""
    custom = set()
    for f in xml.iterfind("m:numFmts/m:numFmt", _NS):
        # Quoted text and [colour] tags aside, a format that writes days, months or years is a date.
        code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", f.get("formatCode") or "").lower()
        if re.search(r"[dy]|m{3,}|\bm\b|mm[/.-]", code) and (n := f.get("numFmtId") or "").isdigit():
            custom.add(int(n))
    out = set()
    for i, xf in enumerate(xml.iterfind("m:cellXfs/m:xf", _NS)):
        n = xf.get("numFmtId") or ""
        if n.isdigit() and (int(n) in _DATE_FORMATS or int(n) in custom):
            out.add(i)
    return out


def _sheet_grid(xml, shared: list[str], dates: set[int] | None = None) -> list[list[str]]:
    """The sheet as rows of cell text, row i being sheet row i + 1, so cell addresses stay true."""
    rows: list[list[str]] = []
    for r in xml.iterfind("m:sheetData/m:row", _NS):
        number = r.get("r")
        if number and number.isdigit():
            # Rows Excel leaves out (blank ones) still count for addresses; a jump past the cap ends the read.
            if int(number) > MAX_ROWS + 10:
                break
            rows.extend([] for _ in range(int(number) - 1 - len(rows)))
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
                style = c.get("s") or ""
                if dates and kind in (None, "n") and style.isdigit() and int(style) in dates \
                        and (d := excel_date(value)) is not None:
                    value = d.isoformat()
            line[col] = value.strip()[:MAX_CELL]
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


def _table_from_grid(name: str, grid: list[list[str]], *, header_dates: bool = False) -> Table | None:
    """The first row that looks like a header (mostly filled, mostly words), and the rows under it.

    grid[i] is source row i + 1; blank rows are dropped from the table but keep their place in the
    addresses."""
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
    kept = [(i + 1, (r + [""] * width)[:width]) for i, r in enumerate(grid) if i > start and any(c for c in r)]
    kept = kept[:MAX_ROWS]
    rows = [r for _, r in kept]
    header = [h or f"Column {_letters(i)}" for i, h in enumerate(header)]
    if header_dates:
        # Excel keeps dates as day numbers (46296 is 2026-10-01). Without styles to say which cells are
        # dates, a column headed only as a date ("Valid from", "Launch date") is shown as dates, so nobody,
        # model or person, has to ask what the number means. "Price from" is not a date column.
        for i, h in enumerate(header):
            if _DATE_HEADER.fullmatch(h.strip()):
                for r in rows:
                    if (d := excel_date(r[i])) is not None:
                        r[i] = d.isoformat()
    return Table(name[:60], header, rows, header_row=start + 1, lines=[n for n, _ in kept])


_DATE_HEADER = re.compile(r"(?:(?:valid|start|end|launch|expiry|effective|release)\s*)?(?:date|from|to|until|on|"
                          r"since|expires?|starts?|ends?|launch(?:es|ed)?)(?:\s+date)?", re.I)


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
    out, size = [f"[{t.name}]", " | ".join(t.header)], 0
    for r in t.rows[:200]:
        line = " | ".join(r)
        size += len(line) + 1
        if size > MAX_TEXT:
            break
        out.append(line)
    return "\n".join(out)


def _pptx(raw: bytes) -> Reading:
    out = Reading("slides")
    budget = _Budget()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        slides = sorted((n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.findall(r"\d+", n)[-1]))
        for n in slides[:200]:
            xml = budget.xml(zf, n)
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
    grid = [[c.strip()[:MAX_CELL] for c in row[:MAX_COLS]] for row in grid]
    table = _table_from_grid(re.sub(r"\.\w+$", "", name)[:60] or "table", grid)
    out = Reading("sheet", tables=[table] if table else [])
    out.text = _table_text(table)[:MAX_TEXT] if table else ""
    if not table:
        out.notes.append("No table found in the file.")
    return out


def _json(raw: bytes, name: str) -> Reading:
    try:
        data = json.loads(_decode(raw))
    except ValueError:
        # Called JSON by its name or type but not JSON: read it as the text it is rather than drop it.
        text = _decode(raw)[:MAX_TEXT]
        return Reading("text", text, [p for p in re.split(r"\n\s*\n", text) if p.strip()],
                       notes=["Not valid JSON; read as text."])
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
        # The shared guard: the declared size is checked against the pixel budget before decoding.
        img = open_image(raw)
    except Exception:  # noqa: BLE001, a picture that won't open (or is too large) is skipped, not fatal
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
