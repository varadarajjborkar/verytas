"""Page pictures of an attached document, made only when someone asks to see one, with where each finding's
words sit on the page, so a document is reviewed the way an image is: the page as it looks, boxes on it.

A PDF is drawn as it is. Word and PowerPoint are first turned into a PDF by LibreOffice, which is another
program reading untrusted files, so it gets several locks, none trusted alone:
- the file is read within the same unzipped-size budget as the review's own reader, before anything else;
- every reference to something outside the file is cut from a parsed copy (relationships, and the field
  codes that pull in pictures or text from elsewhere), and a part that cannot be parsed is refused;
- LibreOffice runs with a throwaway profile whose internet settings point at a closed local port and whose
  macros are off, in its own network namespace where the system allows one, under memory, CPU and output
  limits, one at a time, and its whole process group is killed at the deadline.
Sheets and web pages are shown in the browser instead (a table, a locked frame), which reads better than a
picture of them and needs no conversion.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import zipfile
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache

from verytas.media.files import DOCX, PPTX, MediaError

log = logging.getLogger(__name__)

RENDER_SCALE = 1.5  # about 108 dpi: words stay readable, a slide stays under a megabyte as PNG
MAX_RENDER_SIDE = 2200
CONVERT_SECONDS = 90
QUEUE_SECONDS = 60  # how long a request waits for the one conversion slot before it is told to try later
MAX_PREVIEW_PAGES = 60
MAX_UNZIPPED = 40 * 1024 * 1024  # as the review's own Word reader (media/documents.py)
MAX_ENTRIES = 5000
_CACHE_SIZE = 8  # converted PDFs kept in memory, by file digest

_convert = threading.Semaphore(1)  # one LibreOffice at a time: it is heavy, and the box has two cores
_cache_lock = threading.Lock()
_cache: OrderedDict[str, bytes] = OrderedDict()

# PowerPoint leaves hidden slides out of a PDF by default; the review read them, so the preview shows them
# too, and slide numbers stay the same as in findings.
_FILTERS = {DOCX: "pdf", PPTX: 'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'}
_SUFFIX = {DOCX: ".docx", PPTX: ".pptx"}
# Field codes that load something from outside the file when the document is opened or its fields update.
_PULLING_FIELDS = re.compile(r"\b(INCLUDEPICTURE|INCLUDETEXT|LINK|DDE|DDEAUTO|IMPORT|RD)\b", re.IGNORECASE)
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# A fresh profile's settings: every internet request goes to a closed port on this machine, links in a
# document are never updated, and no macro runs.
_SETTINGS = [
    ("/org.openoffice.Inet/Settings", "ooInetProxyType", "2"),  # manual proxy
    *[("/org.openoffice.Inet/Settings", f"ooInet{kind}Proxy{field}", value)
      for kind in ("HTTP", "HTTPS", "FTP") for field, value in (("Name", "127.0.0.1"), ("Port", "9"))],
    ("/org.openoffice.Inet/Settings", "ooInetNoProxy", ""),
    ("/org.openoffice.Office.Common/Security/Scripting", "MacroSecurityLevel", "3"),
    ("/org.openoffice.Office.Common/Security/Scripting", "DisableMacrosExecution", "true"),
    ("/org.openoffice.Office.Writer/Content/Update", "Link", "2"),  # never update links
]
_PROFILE = ('<?xml version="1.0" encoding="UTF-8"?>\n<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
            'xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            + "".join(f'<item oor:path="{path}"><prop oor:name="{name}" oor:op="fuse"><value>{value}</value></prop>'
                      "</item>\n" for path, name, value in _SETTINGS)
            + "</oor:items>\n")


@dataclass
class Mark:
    finding_id: int
    page: int  # 1-based
    box: tuple[int, int, int, int]  # pixels in the page picture


# On the server, conversions go to verytas-convert@.service (deploy/convert.py) over this socket: a separate
# throwaway user with no network and no view of the app's files. Elsewhere LibreOffice runs locally.
CONVERT_SOCKET = os.environ.get("VERYTAS_CONVERT_SOCKET", "/run/verytas-convert.sock")


def soffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    return found or (mac if os.path.exists(mac) else None)


@lru_cache(maxsize=1)
def _jail() -> list[str]:
    """What to run LibreOffice inside: no network (a namespace with only loopback) and resource limits,
    as far as this system allows. Checked once; a system without them still has the profile and the cut
    links, and says so in the log."""
    prefix: list[str] = []
    unshare = shutil.which("unshare")
    if unshare:
        try:
            if subprocess.run([unshare, "-rn", "true"], capture_output=True, timeout=10).returncode == 0:
                prefix = [unshare, "-rn"]
        except (OSError, subprocess.SubprocessError):
            pass
    if not prefix:
        log.warning("LibreOffice previews run without a network namespace on this system")
    prlimit = shutil.which("prlimit")
    limits = [prlimit, "--as=3221225472", f"--cpu={CONVERT_SECONDS + 30}", "--fsize=209715200", "--"] if prlimit else []
    try:  # only limits this system accepts; a refused one would fail every conversion
        if limits and subprocess.run([*limits, "true"], capture_output=True, timeout=10).returncode == 0:
            prefix += limits
    except (OSError, subprocess.SubprocessError):
        pass
    return prefix


def as_pdf(raw: bytes, kind: str) -> bytes:
    """The file as a PDF: itself, or converted (and remembered) for Word and PowerPoint."""
    if kind == "application/pdf":
        return raw
    if kind not in _FILTERS:
        raise MediaError("no page preview for this kind of file")
    key = hashlib.sha256(raw).hexdigest()
    if (hit := _cached(key)) is not None:
        return hit
    via_socket = os.path.exists(CONVERT_SOCKET)
    binary = None if via_socket else soffice()
    if not via_socket and binary is None:
        raise MediaError("page previews of Word and PowerPoint files need LibreOffice on the server")
    offline = _offline(raw)  # refuses an oversized or unparsable file before anything runs
    if not _convert.acquire(timeout=QUEUE_SECONDS):
        raise MediaError("previews are busy; try again in a minute")
    try:
        if (hit := _cached(key)) is not None:  # converted by the request this one waited behind
            return hit
        pdf = _remote(offline, kind) if via_socket else _run(binary, offline, kind)
    finally:
        _convert.release()
    with _cache_lock:
        _cache[key] = pdf
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return pdf


def ready(raw: bytes, kind: str) -> bytes | None:
    """The PDF without converting anything: the file itself, or one already converted; None otherwise."""
    if kind == "application/pdf":
        return raw
    return _cached(hashlib.sha256(raw).hexdigest()) if kind in _FILTERS else None


def _cached(key: str) -> bytes | None:
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    return None


def _remote(data: bytes, kind: str) -> bytes:
    """Convert through the isolated service; see deploy/convert.py for the wire format."""
    import socket
    import struct

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(CONVERT_SECONDS + 20)
        try:
            sock.connect(CONVERT_SOCKET)
            sock.sendall(_SUFFIX[kind][1:].encode() + b"\n" + struct.pack(">Q", len(data)) + data)
            sock.shutdown(socket.SHUT_WR)
            reply = bytearray()
            while chunk := sock.recv(1 << 16):
                reply += chunk
                if len(reply) > 200 * 1024 * 1024:
                    raise MediaError("the converted file is too large to show")
        except OSError as exc:
            raise MediaError("the preview service did not answer; try again in a minute") from exc
    if reply.startswith(b"OK\n") and len(reply) >= 11:
        (size,) = struct.unpack(">Q", reply[3:11])
        if len(reply) == 11 + size:
            return bytes(reply[11:])
    log.warning("conversion service said %s", bytes(reply[:120]))
    raise MediaError("the file could not be turned into pages")


def _run(binary: str, data: bytes, kind: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="vt-preview-") as tmp:
        user = os.path.join(tmp, "profile", "user")
        os.makedirs(user)
        with open(os.path.join(user, "registrymodifications.xcu"), "w") as fh:
            fh.write(_PROFILE)
        src = os.path.join(tmp, "file" + _SUFFIX[kind])
        with open(src, "wb") as fh:
            fh.write(data)
        cmd = [*_jail(), binary, "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nologo",
               f"-env:UserInstallation=file://{tmp}/profile", "--convert-to", _FILTERS[kind], "--outdir", tmp, src]
        env = {"HOME": tmp, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
               "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9", "no_proxy": ""}
        proc = subprocess.Popen(cmd, cwd=tmp, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, start_new_session=True)
        try:
            _, err = proc.communicate(timeout=CONVERT_SECONDS)
        except subprocess.TimeoutExpired:
            # soffice is a launcher; the worker (soffice.bin) is its child, so the whole group goes.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise MediaError("the file took too long to turn into pages") from None
        out = os.path.join(tmp, "file.pdf")
        if not os.path.exists(out):
            log.warning("LibreOffice could not convert a %s (exit %s): %s", kind, proc.returncode,
                        (err or b"")[-500:].decode("utf-8", "replace"))
            raise MediaError("the file could not be turned into pages")
        with open(out, "rb") as fh:
            return fh.read()


# Parts LibreOffice could import from that are not the document's own XML: an "alternative chunk" of HTML or
# MHT pulled into a Word file, and embedded OLE packages (which carry their own links). Previews show their
# fallback pictures instead.
_DROPPED_PARTS = re.compile(r"(\.(html?|xhtml|mht|mhtml)$|/embeddings/)", re.IGNORECASE)
_URL = re.compile(r"^\s*[a-z][a-z0-9+.\-]*:", re.IGNORECASE)  # http:, file:, smb:, … rather than a path inside


def _offline(raw: bytes) -> bytes:
    """A copy with nothing that reaches outside the file: relationships to anything external point nowhere,
    field codes that pull in a picture or text from elsewhere are blanked (however Word split them across
    runs), and imported chunks and embedded packages are left out. Every XML part is checked wherever it sits
    in the package. Read within the review's own budget; a part that cannot be read or parsed is refused
    rather than passed through unchecked."""
    from lxml import etree

    try:
        zin = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise MediaError("not a readable Office file") from exc
    with zin:
        infos = zin.infolist()
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNZIPPED:
            raise MediaError(f"the file expands to more than {MAX_UNZIPPED // 1024 // 1024} MB; no preview")
        parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in infos:
                name = info.filename.lower()
                if _DROPPED_PARTS.search(name):
                    continue
                try:
                    data = zin.read(info)  # bounded by the entry's declared size, which the sum above checked
                except (zipfile.BadZipFile, zlib.error, RuntimeError, EOFError, OSError) as exc:
                    raise MediaError("a part of the file is damaged; no preview") from exc
                if name.endswith((".rels", ".xml", ".vml")):
                    try:
                        root = etree.fromstring(data, parser)
                    except etree.XMLSyntaxError as exc:
                        raise MediaError("a part of the file is damaged; no preview") from exc
                    if _cut(root):
                        data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                zout.writestr(info, data)
    return out.getvalue()


def _cut(root) -> bool:
    """Blank what would reach outside the file, in place; True when anything changed."""
    changed = False
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        local = el.tag.rsplit("}", 1)[-1]
        if local == "Relationship":
            target = el.get("Target") or ""
            if (el.get("TargetMode") or "").strip().lower() == "external" or _URL.match(target):
                el.set("Target", "")
                changed = True
        elif local == "fldSimple" and _PULLING_FIELDS.search(el.get(f"{_W}instr") or ""):
            el.set(f"{_W}instr", "")
            changed = True
    return _cut_fields(root) or changed


def _cut_fields(root) -> bool:
    """A complex field's instruction is split across runs as Word saves it ("INCLUDEPIC" + "TURE ..."), between
    a begin and a separate (or end) mark; it is read whole, and every run of a pulling field is blanked."""
    changed = False
    open_fields: list[list] = []  # the instruction runs of each field being read, innermost last
    for el in root.iter(f"{_W}fldChar", f"{_W}instrText"):
        if el.tag == f"{_W}instrText":
            if open_fields:
                open_fields[-1].append(el)
            elif _PULLING_FIELDS.search(el.text or ""):  # an instruction outside any begin mark
                el.text = ""
                changed = True
            continue
        kind = el.get(f"{_W}fldCharType")
        if kind == "begin":
            open_fields.append([])
        elif kind in ("separate", "end") and open_fields:
            # The instruction ends at the separate mark (or the end mark when there is no result part).
            runs = open_fields.pop()
            if _PULLING_FIELDS.search("".join(r.text or "" for r in runs)):
                for r in runs:
                    r.text = ""
                changed = True
            if kind == "separate":
                open_fields.append([])  # the result part, closed by this field's own end mark
    for runs in open_fields:  # a field left open by a damaged file is judged on what it has
        if _PULLING_FIELDS.search("".join(r.text or "" for r in runs)):
            for r in runs:
                r.text = ""
            changed = True
    return changed


def _open(pdf: bytes):
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(pdf)
    except pdfium.PdfiumError as exc:
        raise MediaError("the file is not a readable PDF") from exc


def page_sizes(pdf: bytes) -> tuple[list[tuple[int, int]], int]:
    """Each page's picture size in pixels (at most MAX_PREVIEW_PAGES of them), and how many pages there are."""
    from verytas.media.documents import _PDFIUM

    with _PDFIUM:
        doc = _open(pdf)
        try:
            return [_size(doc[i]) for i in range(min(len(doc), MAX_PREVIEW_PAGES))], len(doc)
        finally:
            doc.close()


def _geometry(page) -> tuple[float, float, float, float, int, float]:
    """(left, top, width, height) of the part of the page that is shown (its crop box), its rotation in
    degrees and the render scale; the picture is the crop box, turned by the rotation."""
    left, bottom, right, top = page.get_cropbox()
    w, h, rot = right - left, top - bottom, page.get_rotation() % 360
    shown_w, shown_h = (h, w) if rot in (90, 270) else (w, h)
    return left, top, w, h, rot, min(RENDER_SCALE, MAX_RENDER_SIDE / max(shown_w, shown_h, 1))


def _size(page) -> tuple[int, int]:
    _, _, w, h, rot, s = _geometry(page)
    return (round(h * s), round(w * s)) if rot in (90, 270) else (round(w * s), round(h * s))


def render(pdf: bytes, number: int) -> bytes:
    """One page as PNG."""
    from verytas.media.documents import _PDFIUM

    with _PDFIUM:
        doc = _open(pdf)
        try:
            if not 1 <= number <= min(len(doc), MAX_PREVIEW_PAGES):
                raise MediaError("no such page")
            page = doc[number - 1]
            image = page.render(scale=_geometry(page)[5]).to_pil().convert("RGB")
        finally:
            doc.close()
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def locate(pdf: bytes, wanted: list[tuple[int, str, int | None]]) -> list[Mark]:
    """Where each finding's words are: (finding id, quote, page or None for anywhere). A quote is looked up
    whole, then by its first line, since a PDF breaks lines where the source text did not. A finding on a
    page past the preview's cap is not marked anywhere else."""
    from verytas.media.documents import _PDFIUM

    marks: list[Mark] = []
    with _PDFIUM:
        doc = _open(pdf)
        texts: dict[int, object] = {}
        try:
            last = min(len(doc), MAX_PREVIEW_PAGES)
            for fid, quote, only in wanted:
                if only is not None and not 1 <= only <= last:
                    continue
                for n in [only] if only is not None else range(1, last + 1):
                    page = doc[n - 1]
                    if n not in texts:
                        texts[n] = page.get_textpage()
                    if found := _boxes(page, texts[n], quote):
                        marks.extend(Mark(fid, n, b) for b in found)
                        break
        finally:
            for t in texts.values():
                t.close()
            doc.close()
    return marks


def _boxes(page, text, quote: str) -> list[tuple[int, int, int, int]]:
    tries = [" ".join(quote.split())]
    first = " ".join(quote.strip().splitlines()[0].split()) if quote.strip() else ""
    if first and first != tries[0]:
        tries.append(first)
    left, top, w, h, rot, s = _geometry(page)

    def to_pixels(x: float, y: float) -> tuple[float, float]:
        u, v = x - left, top - y  # from the shown area's top left, unturned
        if rot == 90:
            u, v = h - v, u
        elif rot == 180:
            u, v = w - u, h - v
        elif rot == 270:
            u, v = v, w - u
        return u * s, v * s

    for needle in tries:
        if len(needle) < 2:
            continue
        searcher = text.search(needle[:200], match_case=False, match_whole_word=False)
        hit = searcher.get_next()
        searcher.close()
        if hit is None:
            continue
        index, count = hit
        boxes = []
        for i in range(text.count_rects(index, count)):
            x0, y0, x1, y1 = text.get_rect(i)
            (ax, ay), (bx, by) = to_pixels(x0, y0), to_pixels(x1, y1)
            boxes.append((round(min(ax, bx)) - 2, round(min(ay, by)) - 2, round(max(ax, bx)) + 2,
                          round(max(ay, by)) + 2))
        return boxes
    return []
