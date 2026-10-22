"""Synthetic media for tests: images with text, PDFs, a mascot, a short video.

Built in code so the tests carry no binary fixtures and every expected
answer is known exactly.
"""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_PATHS = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
               "/Library/Fonts/Arial.ttf"]


def font(size: int = 34):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def text_image(lines: list[str], size=(900, 300), bg="white", fg="black") -> Image.Image:
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((24, 24 + i * 64), line, fill=fg, font=font())
    return img


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def mascot_face(eye=(30, 30, 30), size=400) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(60, 90), (110, 10), (150, 95)], fill=(200, 90, 20, 255))
    d.polygon([(250, 95), (290, 10), (340, 90)], fill=(200, 90, 20, 255))
    d.ellipse((40, 60, 360, 380), fill=(240, 130, 40, 255))
    d.ellipse((70, 120, 190, 240), fill="white")
    d.ellipse((210, 120, 330, 240), fill="white")
    d.ellipse((105, 155, 160, 210), fill=eye)
    d.ellipse((245, 155, 300, 210), fill=eye)
    d.ellipse((118, 165, 135, 182), fill="white")
    d.ellipse((258, 165, 275, 182), fill="white")
    d.polygon([(175, 250), (225, 250), (200, 300)], fill=(250, 200, 30, 255))
    for i in range(8):
        d.arc((120 + i * 20, 300, 160 + i * 20, 340), 0, 180, fill=(180, 80, 20, 255), width=4)
    return img


def mascot_scene(face: Image.Image, *, body=False, caption: str | None = None) -> Image.Image:
    s = Image.new("RGB", (1000, 800), (250, 248, 240))
    d = ImageDraw.Draw(s)
    f = face.resize((240, 240), Image.LANCZOS)
    x, y = 360, 120
    if body:
        d.ellipse((x + 10, y + f.height - 30, x + f.width - 10, y + f.height + 300), fill=(240, 130, 40))
        d.rectangle((x - 60, y + f.height + 40, x + 20, y + f.height + 80), fill=(240, 130, 40))
    s.paste(f, (x, y), f)
    if caption:
        d.text((30, 720), caption, fill="black", font=font(30))
    return s


def pdf(pages: list[dict]) -> bytes:
    """A small real PDF. Each page: {"text": [lines], "image": PIL or None, "outlined": [lines],
    "one_shape": bool}.

    Text goes in as a proper text layer (Helvetica); an image becomes an
    XObject drawn on the page, like a screenshot pasted into a document.
    Outlined lines are drawn as filled vector shapes with no text layer, the
    way a design tool exports text converted to outlines.
    """
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    kids = []
    for page in pages:
        stream = b""
        for i, line in enumerate(page.get("text") or []):
            esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")
            stream += b"BT /F1 18 Tf 50 %d Td (" % (740 - i * 28) + esc + b") Tj ET\n"
        if page.get("outlined"):
            # Each dark run of pixels in a rendering of the lines becomes one filled rectangle.
            bitmap = np.asarray(text_image(page["outlined"], size=(1000, 70 * len(page["outlined"]) + 40))
                                .convert("L")) < 128
            scale = 0.5
            for y, row in enumerate(bitmap):
                xs = np.flatnonzero(np.diff(np.concatenate([[0], row.astype(np.int8), [0]])))
                for x0, x1 in zip(xs[::2], xs[1::2], strict=True):
                    # One fill per run, or (as most design tools export a line) a single shape for all of it.
                    stream += b"%.1f %.1f %.1f %.1f re%s\n" % (40 + x0 * scale, 380 - y * scale,
                                                                (x1 - x0) * scale, scale,
                                                                b"" if page.get("one_shape") else b" f")
            if page.get("one_shape"):
                stream += b"f\n"
        resources = b"/Font << /F1 %d 0 R >>" % font_id
        img = page.get("image")
        if img is not None:
            rgb = img.convert("RGB")
            img_id = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                         b"/BitsPerComponent 8 /Length %d >>\nstream\n" % (rgb.width, rgb.height, len(rgb.tobytes()))
                         + rgb.tobytes() + b"\nendstream")
            w, h = page.get("image_size", (400, 400 * rgb.height // rgb.width))
            stream += b"q %d 0 0 %d 100 200 cm /Im1 Do Q\n" % (w, h)
            resources += b" /XObject << /Im1 %d 0 R >>" % img_id
        content_id = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append((content_id, resources))
    pages_id = len(objects) + len(kids) + 1
    for content_id, resources in kids:
        page_ids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                            b"/Resources << %s >> >>" % (pages_id, content_id, resources)))
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % p for p in page_ids),
                                                              len(page_ids))) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref))
    return out.getvalue()


def scanned_pdf(img: Image.Image) -> bytes:
    """An image-only PDF: what a scanner or "print to PDF" of a photo produces."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PDF", resolution=100)
    return buf.getvalue()


def caption_video(captions: list[tuple[float, float, str]], seconds: int = 6, fps: int = 5) -> bytes:
    """A small vertical video with burned-in captions and a silent audio track."""
    import av

    buf = io.BytesIO()
    out = av.open(buf, "w", format="mp4")
    codec = "libx264" if "libx264" in av.codecs_available else "mpeg4"
    vs = out.add_stream(codec, rate=fps)
    vs.width, vs.height, vs.pix_fmt = 360, 640, "yuv420p"
    aus = out.add_stream("aac", rate=16000)  # every stream before the first packet
    aus.layout = "mono"
    for i in range(seconds * fps):
        t = i / fps
        img = Image.new("RGB", (360, 640), (30, 60, 120) if t < seconds / 2 else (150, 40, 60))
        d = ImageDraw.Draw(img)
        txt = next((c for a, b, c in captions if a <= t < b), "")
        if txt:
            d.rectangle((10, 520, 350, 570), fill="black")
            d.text((18, 528), txt, fill="white", font=font(22))
        frame = av.VideoFrame.from_image(img)
        frame.pts = i
        for pkt in vs.encode(frame):
            out.mux(pkt)
    for pkt in vs.encode():
        out.mux(pkt)
    silence = np.zeros(1024, dtype=np.float32)
    for k in range(0, 16000 * seconds, 1024):
        af = av.AudioFrame.from_ndarray(silence.reshape(1, -1), format="fltp", layout="mono")
        af.sample_rate = 16000
        af.pts = k
        for pkt in aus.encode(af):
            out.mux(pkt)
    for pkt in aus.encode():
        out.mux(pkt)
    out.close()
    return buf.getvalue()
