"""Decoding uploads safely.

The declared media type is a hint from the client; the bytes decide. Limits
are enforced before any parser sees the data: a 20 MB PDF can still inflate
into gigapixels of page images, and an image header can claim any size.
"""

from __future__ import annotations

import base64
import binascii
import io
import re
import warnings
import zlib

import numpy as np
from PIL import Image, UnidentifiedImageError

MAX_DOC_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # a voice note of several minutes
# Decoded pixels per image. Larger images are refused, not downscaled: the
# decoder would already have allocated the full bitmap.
MAX_PIXELS = 40_000_000
# Images are shrunk to this longest side before OCR, matching and vision calls.
WORK_SIDE = 2000


class MediaError(ValueError):
    """The upload could not be read. Reported as "not checked", never as a pass."""


def decode_b64(data: str, limit: int) -> bytes:
    try:
        # Line-wrapped base64 is common and fine; anything else outside the alphabet is refused
        # rather than silently dropped, so what is checked is exactly what was sent.
        raw = base64.b64decode("".join(data.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MediaError("not valid base64") from exc
    if len(raw) > limit:
        raise MediaError(f"{len(raw) // 1024} KB is over the {limit // 1024 // 1024} MB limit")
    return raw


def sniff(raw: bytes) -> str:
    """Media type from magic bytes, or "unknown"."""
    if raw.startswith(b"%PDF-"):
        return "application/pdf"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw.startswith(b"PK\x03\x04") and b"word/" in raw[:4096]:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if raw[4:8] == b"ftyp":
        # Phones save HEIC and AVIF stills in the same ISO container as MP4;
        # the major brand tells them apart.
        brand = raw[8:12]
        if brand in _HEIF_BRANDS:
            return "image/avif" if brand in (b"avif", b"avis") else "image/heic"
        return "video/quicktime" if raw[8:10] == b"qt" else "video/mp4"
    if raw.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if raw[:4] == b"RIFF" and raw[8:12] == b"AVI ":
        return "video/x-msvideo"
    # Voice notes for a creator's brief. Browsers record WebM or MP4 (sniffed above as video); phones and
    # recorders also save these.
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return "audio/wav"
    if raw.startswith(b"OggS"):
        return "audio/ogg"
    if raw.startswith(b"ID3") or _mp3_frame(raw):
        return "audio/mpeg"
    return "unknown"


def _mp3_frame(raw: bytes) -> bool:
    """An MPEG audio frame header, not just any bytes starting 0xFF: the layer, bitrate and sample rate
    fields must hold real values (a UTF-16 text file starts FF FE and is not audio)."""
    if len(raw) < 4 or raw[0] != 0xFF or raw[1] & 0xE0 != 0xE0 or raw[1] == 0xFE:
        return False
    layer, bitrate, rate = (raw[1] >> 1) & 0x3, raw[2] >> 4, (raw[2] >> 2) & 0x3
    return layer != 0 and bitrate not in (0, 0xF) and rate != 3


_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif", b"avis"}
UNSUPPORTED_IMAGES = {"image/heic", "image/avif"}


def open_image(raw: bytes) -> Image.Image:
    """Decode to RGB, refusing anything over the pixel budget before decoding.

    Image.open only reads the header, so the declared size is checked before
    load() allocates the bitmap. (Changing Image.MAX_IMAGE_PIXELS instead
    would be process-global and race with OCR running in worker threads.)
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            img = Image.open(io.BytesIO(raw))
            if img.width * img.height > MAX_PIXELS:
                raise MediaError("image is too large to check safely")
            img.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise MediaError("image is too large to check safely") from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            if isinstance(exc, MediaError):
                raise
            raise MediaError("not a readable image") from exc
    return flatten(img)


def animation_frames(raw: bytes, limit: int = 4) -> tuple[int, list[Image.Image]]:
    """(frame count, up to `limit` evenly spaced frames after the first) of an animated GIF or WebP.

    Same guards as open_image: a damaged or oversized file is a MediaError, never a raw crash.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            img = Image.open(io.BytesIO(raw))
            n = getattr(img, "n_frames", 1)
            if n <= 1 or img.width * img.height > MAX_PIXELS:
                return n, []
            picks = sorted({round(i * (n - 1) / limit) for i in range(1, limit + 1)} - {0})
            out = []
            for k in picks:
                img.seek(k)
                out.append(flatten(img.copy()))
            return n, out
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise MediaError("animation is too large to check safely") from exc
        except (UnidentifiedImageError, OSError, ValueError, EOFError) as exc:
            raise MediaError("not a readable animation") from exc


def flatten(img: Image.Image) -> Image.Image:
    """RGB on white. Transparent regions would otherwise read as black."""
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, "white")
        base.paste(rgba, mask=rgba.split()[3])
        return base
    return img.convert("RGB")


def shrink(img: Image.Image, side: int = WORK_SIDE) -> Image.Image:
    if max(img.size) <= side:
        return img
    scale = side / max(img.size)
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def to_array(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"))


def png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def limit_for(media_type: str) -> int:
    if media_type.startswith("video/"):
        return MAX_VIDEO_BYTES
    if media_type.startswith("audio/"):
        return MAX_AUDIO_BYTES
    if media_type.startswith("image/"):
        return MAX_IMAGE_BYTES
    return MAX_DOC_BYTES


# PDF names that mean a file can act, not just display: scripts, launch
# actions, embedded files, auto-run forms. A social post needs none of them.
_PDF_ACTIVE = {b"JavaScript": "JavaScript", b"JS": "JavaScript", b"Launch": "launch action",
               b"EmbeddedFile": "embedded file", b"EmbeddedFiles": "embedded file", b"OpenAction": "auto-open action",
               b"AA": "auto-run action", b"RichMedia": "rich media", b"XFA": "XFA form"}
_NAME = re.compile(rb"/([^\s/<>\[\]()%{}]+)")
_HEX = re.compile(rb"#([0-9A-Fa-f]{2})")
_OBJSTM_MAX = 8 * 1024 * 1024  # inflated bytes read from all object streams together


def _names(chunk: bytes) -> set[bytes]:
    """PDF names in a chunk of object syntax, with #xx escapes decoded (/J#61vaScript is /JavaScript)."""
    return {_HEX.sub(lambda m: bytes([int(m.group(1), 16)]), m.group(1)) for m in _NAME.finditer(chunk)}


def _streams(raw: bytes):
    """(start, body, end) of each `stream ... endstream` run, scanning forward only.

    A lazy regex for this is quadratic: every unterminated `stream` makes it read to the end of the
    file again, so a few megabytes of them stall a worker for minutes. An unterminated stream ends
    the walk and the rest is read as dictionary text, as the regex did."""
    pos = 0
    while (start := raw.find(b"stream", pos)) != -1:
        data = start + 6
        if raw.startswith(b"\r\n", data):
            data += 2
        elif raw.startswith(b"\n", data):
            data += 1
        else:
            pos = data
            continue
        end = raw.find(b"endstream", data)
        if end == -1:
            return
        yield start, raw[data:end], end + 9
        pos = end + 9


def pdf_active_content(raw: bytes) -> list[str]:
    """Active features named in a PDF's object dictionaries.

    Stream contents (page drawing, images, fonts) are skipped: they are
    arbitrary bytes, and a short token like /JS turns up in them by chance.
    Compressed object streams, where PDF 1.5+ files keep their dictionaries,
    are inflated (within a budget) and scanned as dictionaries.
    """
    names: set[bytes] = set()
    pos, budget = 0, _OBJSTM_MAX
    for start, body, end in _streams(raw):
        head = raw[pos:start]
        names |= _names(head)
        # The stream's own dictionary sits just before the keyword.
        if b"ObjStm" in _names(head[-400:]) and budget > 0:
            try:
                inflated = zlib.decompressobj().decompress(body, budget)
            except zlib.error:
                inflated = b""
            budget -= len(inflated)
            names |= _names(inflated)
        pos = end
    names |= _names(raw[pos:])
    found = []
    for name, label in _PDF_ACTIVE.items():
        if name in names and label not in found:
            found.append(label)
    # An OpenAction that only sets the initial view is harmless and very common.
    if found == ["auto-open action"]:
        return []
    return found
