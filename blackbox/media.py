"""The simulator's own media generator: images, PDFs and video with planted content.

Written independently of the backend (no shared code), so a bug in how
Verytas reads a PDF can't also be a bug in how the test writes one.
"""

from __future__ import annotations

import base64
import io
import random

from PIL import Image, ImageDraw, ImageFont

_FONTS = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def _font(size: int):
    for path in _FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def text_card(lines: list[str], style: str, rng: random.Random) -> Image.Image:
    """A social card with text. Styles: plain, stylised (colour, tilt, big type), low_contrast."""
    bg = {"plain": (255, 255, 255), "stylised": rng.choice([(30, 60, 120), (150, 40, 60), (20, 110, 80)]),
          "low_contrast": (232, 232, 232)}[style]
    fg = {"plain": (20, 20, 20), "stylised": (255, 236, 160), "low_contrast": (182, 182, 182)}[style]
    img = Image.new("RGB", (1080, 1080), bg)
    d = ImageDraw.Draw(img)
    size = 64 if style == "stylised" else 48
    y = 300
    for line in lines:
        d.text((80, y), line, fill=fg, font=_font(size))
        y += size + 30
    if style == "stylised":
        img = img.rotate(rng.choice([-8, -5, 5, 8]), fillcolor=bg)
    return img


def mascot(colour: tuple[int, int, int], eye=(30, 30, 30)) -> Image.Image:
    """A simple brand character face with enough detail for feature matching."""
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    dark = tuple(max(0, c - 50) for c in colour)
    d.polygon([(60, 90), (110, 10), (150, 95)], fill=(*dark, 255))
    d.polygon([(250, 95), (290, 10), (340, 90)], fill=(*dark, 255))
    d.ellipse((40, 60, 360, 380), fill=(*colour, 255))
    for x in (70, 210):
        d.ellipse((x, 120, x + 120, 240), fill="white")
        d.ellipse((x + 35, 155, x + 90, 210), fill=eye)
        d.ellipse((x + 48, 165, x + 65, 182), fill="white")
    d.polygon([(175, 250), (225, 250), (200, 300)], fill=(250, 200, 30, 255))
    for i in range(8):
        d.arc((120 + i * 20, 300, 160 + i * 20, 340), 0, 180, fill=(*dark, 255), width=4)
    return img


def mascot_post(face: Image.Image, colour: tuple[int, int, int], *, body: bool) -> Image.Image:
    s = Image.new("RGB", (1000, 900), (250, 248, 240))
    d = ImageDraw.Draw(s)
    f = face.resize((260, 260), Image.LANCZOS)
    x, y = 360, 120
    if body:
        d.ellipse((x + 10, y + 230, x + 250, y + 600), fill=colour)
        d.rectangle((x - 70, y + 300, x + 20, y + 340), fill=colour)
    s.paste(f, (x, y), f)
    return s


def other_character() -> Image.Image:
    s = Image.new("RGB", (900, 900), (240, 246, 255))
    d = ImageDraw.Draw(s)
    d.rounded_rectangle((280, 200, 620, 640), 60, fill=(90, 160, 220))
    d.rectangle((360, 330, 420, 390), fill="white")
    d.rectangle((480, 330, 540, 390), fill="white")
    d.arc((380, 440, 520, 540), 20, 160, fill=(20, 40, 80), width=10)
    return s


def pdf(pages: list[dict]) -> bytes:
    """Minimal PDF writer: per page an optional text layer and an optional pasted image."""
    objs: list[bytes] = []

    def add(o: bytes) -> int:
        objs.append(o)
        return len(objs)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    contents = []
    for page in pages:
        stream, res = b"", b"/Font << /F1 %d 0 R >>" % font
        for i, line in enumerate(page.get("text") or []):
            esc = line.encode("latin-1", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            stream += b"BT /F1 20 Tf 60 %d Td (" % (720 - 32 * i) + esc + b") Tj ET\n"
        if page.get("image") is not None:
            rgb = page["image"].convert("RGB")
            raw = rgb.tobytes()
            im = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                     b"/BitsPerComponent 8 /Length %d >>\nstream\n" % (rgb.width, rgb.height, len(raw)) + raw
                     + b"\nendstream")
            stream += b"q 420 0 0 %d 90 160 cm /Im0 Do Q\n" % (420 * rgb.height // rgb.width)
            res += b" /XObject << /Im0 %d 0 R >>" % im
        contents.append((add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"), res))
    parent = len(objs) + len(contents) + 1
    kids = [add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Contents %d 0 R /Resources << %s >> >>"
                % (parent, c, r)) for c, r in contents]
    add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids)))
    root = add(b"<< /Type /Catalog /Pages %d 0 R >>" % parent)
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, o in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    out.write(b"".join(b"%010d 00000 n \n" % off for off in offsets))
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, root, xref))
    return out.getvalue()


def scanned_pdf(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PDF", resolution=110)
    return buf.getvalue()


def caption_video(captions: list[str], seconds_each: float = 2.0) -> bytes:
    """A vertical reel with burned-in captions and silent audio."""
    import av
    import numpy as np

    fps = 5
    total = int(len(captions) * seconds_each * fps)
    buf = io.BytesIO()
    out = av.open(buf, "w", format="mp4")
    vs = out.add_stream("libx264" if "libx264" in av.codecs_available else "mpeg4", rate=fps)
    vs.width, vs.height, vs.pix_fmt = 360, 640, "yuv420p"
    aus = out.add_stream("aac", rate=16000)
    aus.layout = "mono"
    for i in range(total):
        img = Image.new("RGB", (360, 640), (40, 50, 90))
        d = ImageDraw.Draw(img)
        txt = captions[min(len(captions) - 1, int(i / fps / seconds_each))]
        d.rectangle((8, 520, 352, 572), fill="black")
        d.text((16, 530), txt, fill="white", font=_font(22))
        frame = av.VideoFrame.from_image(img)
        frame.pts = i
        for pkt in vs.encode(frame):
            out.mux(pkt)
    for pkt in vs.encode():
        out.mux(pkt)
    silence = np.zeros((1, 1024), dtype=np.float32)
    for k in range(0, int(16000 * total / fps), 1024):
        af = av.AudioFrame.from_ndarray(silence, format="fltp", layout="mono")
        af.sample_rate, af.pts = 16000, k
        for pkt in aus.encode(af):
            out.mux(pkt)
    for pkt in aus.encode():
        out.mux(pkt)
    out.close()
    return buf.getvalue()
