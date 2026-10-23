"""Artwork drawn in code, so the repo carries no binary files and the demo still has official marks,
packs, patterns and campaign images for the visual checks to compare against.

Each company draws its own marks from these primitives. Misuse is drawn the same way a careless creator
would make it: `stretch` squeezes a logo into a banner slot, `recolour` swaps its brand colours for a
campaign palette, `tint_shift` is a quieter version of the same mistake. Everything is deterministic."""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw, ImageFont

Color = tuple[int, int, int]
_BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
_REG = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(size: int, bold: bool = True):
    for path in (_BOLD if bold else _REG):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def image_attachment(key: str, alt: str, img: Image.Image) -> dict:
    return {"id": key, "alt": alt, "data_base64": b64(img)}


def canvas(size: tuple[int, int], color: Color | tuple = (255, 255, 255)) -> Image.Image:
    return Image.new("RGB" if len(color) == 3 else "RGBA", size, color)


def gradient(size: tuple[int, int], top: Color, bottom: Color) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)))
    return img


def text_w(txt: str, size: int, bold: bool = True) -> int:
    box = font(size, bold).getbbox(txt)
    return box[2] - box[0]


def fit_text(d: ImageDraw.ImageDraw, xy: tuple[int, int], txt: str, width: int, fill, start: int = 120,
             bold: bool = True) -> int:
    """Draw `txt` at the largest size that fits `width`; returns the size used."""
    size = start
    while size > 10 and text_w(txt, size, bold) > width:
        size -= 2
    d.text(xy, txt, fill=fill, font=font(size, bold))
    return size


def wrap(d: ImageDraw.ImageDraw, xy: tuple[int, int], txt: str, width: int, fill, size: int, gap: int = 8,
         bold: bool = True) -> int:
    """Greedy word wrap; returns the y below the last line."""
    x, y = xy
    line = ""
    for word in txt.split():
        trial = f"{line} {word}".strip()
        if text_w(trial, size, bold) > width and line:
            d.text((x, y), line, fill=fill, font=font(size, bold))
            y += size + gap
            line = word
        else:
            line = trial
    if line:
        d.text((x, y), line, fill=fill, font=font(size, bold))
        y += size + gap
    return y


def paste(scene: Image.Image, art: Image.Image, xy: tuple[int, int], width: int | None = None,
          height: int | None = None) -> Image.Image:
    """Place `art` on `scene`. Giving both width and height ignores the aspect ratio, which is how a logo gets
    stretched; giving one keeps it."""
    a = art.convert("RGBA")
    if width and height:
        a = a.resize((width, height), Image.LANCZOS)
    elif width:
        a = a.resize((width, round(a.height * width / a.width)), Image.LANCZOS)
    elif height:
        a = a.resize((round(a.width * height / a.height), height), Image.LANCZOS)
    scene.paste(a, xy, a)
    return scene


def stretch(art: Image.Image, sx: float, sy: float) -> Image.Image:
    return art.resize((round(art.width * sx), round(art.height * sy)), Image.LANCZOS)


def recolour(art: Image.Image, order: str = "gbr") -> Image.Image:
    """Swap colour channels: the brand's blue becomes a different hue, the shapes stay the same."""
    a = art.convert("RGBA")
    ch = dict(zip("rgb", a.split()[:3], strict=True))
    return Image.merge("RGBA", (ch[order[0]], ch[order[1]], ch[order[2]], a.split()[3]))


def tint_shift(art: Image.Image, amount: int = 40) -> Image.Image:
    """A slightly wrong shade (a rushed export, a different colour profile)."""
    a = art.convert("RGBA")
    r, g, b, al = a.split()
    return Image.merge("RGBA", (r.point(lambda v: min(255, v + amount)), g, b.point(lambda v: max(0, v - amount)), al))


def mono(art: Image.Image, color: Color = (255, 255, 255)) -> Image.Image:
    """The one-colour version of a mark: the alpha shape filled with a single colour."""
    a = art.convert("RGBA")
    solid = Image.new("RGBA", a.size, color + (255,))
    solid.putalpha(a.split()[3])
    return solid


def on_color(art: Image.Image, bg: Color, pad: int = 40) -> Image.Image:
    base = Image.new("RGB", (art.width + 2 * pad, art.height + 2 * pad), bg)
    a = art.convert("RGBA")
    base.paste(a, (pad, pad), a)
    return base


# --- reusable shapes ---------------------------------------------------------------------------------

def emblem(shape: str, size: int, c1: Color, c2: Color, accent: Color, glyph: str = "") -> Image.Image:
    """A distinctive, textured mark on a transparent square: enough corners and facets to be matched later."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    if shape == "hex":
        pts = [(s * .5, s * .04), (s * .93, s * .27), (s * .93, s * .73), (s * .5, s * .96), (s * .07, s * .73),
               (s * .07, s * .27)]
        d.polygon(pts, fill=c1 + (255,))
        d.polygon([pts[0], pts[1], pts[2], (s * .5, s * .5)], fill=c2 + (255,))
        d.polygon([pts[3], pts[4], pts[5], (s * .5, s * .5)], fill=c2 + (255,))
        d.ellipse((s * .32, s * .32, s * .68, s * .68), fill=accent + (255,))
    elif shape == "drop":
        d.ellipse((s * .12, s * .3, s * .88, s * .94), fill=c1 + (255,))
        d.polygon([(s * .5, s * .03), (s * .2, s * .5), (s * .8, s * .5)], fill=c1 + (255,))
        d.pieslice((s * .2, s * .38, s * .8, s * .98), 90, 270, fill=c2 + (255,))
        d.ellipse((s * .56, s * .5, s * .72, s * .66), fill=accent + (255,))
    elif shape == "leaf":
        d.pieslice((s * .05, s * .05, s * .95, s * .95), 180, 270, fill=c1 + (255,))
        d.pieslice((s * .05, s * .05, s * .95, s * .95), 0, 90, fill=c1 + (255,))
        d.pieslice((s * .05, s * .05, s * .95, s * .95), 270, 360, fill=c2 + (255,))
        d.pieslice((s * .05, s * .05, s * .95, s * .95), 90, 180, fill=c2 + (255,))
        d.line([(s * .2, s * .8), (s * .8, s * .2)], fill=accent + (255,), width=max(3, s // 36))
    elif shape == "loop":
        d.ellipse((s * .05, s * .05, s * .95, s * .95), fill=c1 + (255,))
        d.ellipse((s * .25, s * .25, s * .75, s * .75), fill=(0, 0, 0, 0))
        d.arc((s * .05, s * .05, s * .95, s * .95), 200, 340, fill=accent + (255,), width=max(6, s // 10))
        d.polygon([(s * .62, s * .1), (s * .88, s * .22), (s * .64, s * .32)], fill=c2 + (255,))
        d.ellipse((s * .42, s * .42, s * .58, s * .58), fill=c2 + (255,))
    elif shape == "sun":
        for i in range(12):
            a0 = i * 30
            d.pieslice((s * .02, s * .02, s * .98, s * .98), a0, a0 + 15, fill=(c1 if i % 2 else c2) + (255,))
        d.ellipse((s * .22, s * .22, s * .78, s * .78), fill=accent + (255,))
        d.ellipse((s * .34, s * .34, s * .66, s * .66), fill=c1 + (255,))
    else:  # shield
        d.polygon([(s * .1, s * .08), (s * .9, s * .08), (s * .9, s * .55), (s * .5, s * .95), (s * .1, s * .55)],
                  fill=c1 + (255,))
        d.polygon([(s * .5, s * .08), (s * .9, s * .08), (s * .9, s * .55), (s * .5, s * .95)], fill=c2 + (255,))
        d.line([(s * .5, s * .2), (s * .5, s * .8)], fill=accent + (255,), width=max(3, s // 30))
    if glyph:
        f = font(round(s * .3))
        box = d.textbbox((0, 0), glyph, font=f)
        d.text(((s - (box[2] - box[0])) / 2 - box[0], (s - (box[3] - box[1])) / 2 - box[1] + s * .02), glyph,
               fill=(255, 255, 255, 255), font=f)
    return img


def wordmark_img(text: str, color: Color, size: tuple[int, int] = (560, 160), sub: str = "",
                 bg: Color | None = None) -> Image.Image:
    img = Image.new("RGB" if bg else "RGBA", size, bg or (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    used = fit_text(d, (24, 18), text, size[0] - 48, color + ((255,) if not bg else ()), start=int(size[1] * .62))
    if sub:
        d.text((28, 18 + used + 14), sub, fill=color + ((255,) if not bg else ()), font=font(max(14, used // 3), False))
    return img


def lockup(mark: Image.Image, text: str, color: Color, height: int = 220, gap: int = 24,
           bg: Color | None = None) -> Image.Image:
    """Emblem beside the name: the primary logo."""
    m = mark.resize((height, height), Image.LANCZOS)
    w = height + gap + text_w(text, round(height * .5)) + 40
    img = Image.new("RGB" if bg else "RGBA", (w, height + 20), bg or (0, 0, 0, 0))
    img.paste(m, (10, 10), m)
    d = ImageDraw.Draw(img)
    f = font(round(height * .5))
    d.text((10 + height + gap, 10 + height * .5 - f.getbbox(text)[3] / 2 - f.getbbox(text)[1] / 2), text,
           fill=color + (() if bg else (255,)), font=f)
    return img


def pattern(kind: str, size: int, c1: Color, c2: Color, c3: Color) -> Image.Image:
    img = Image.new("RGB", (size, size), c1)
    d = ImageDraw.Draw(img)
    step = size // 6
    for i in range(7):
        for j in range(7):
            x, y = i * step, j * step
            if kind == "dots":
                d.ellipse((x + 4, y + 4, x + step * .55, y + step * .55), fill=c2 if (i + j) % 2 else c3)
            elif kind == "waves":
                d.arc((x - step // 2, y, x + step, y + step), 0 if (i + j) % 2 else 180, 180 if (i + j) % 2 else 360,
                      fill=c2 if j % 2 else c3, width=max(3, step // 8))
            else:  # chevron
                d.polygon([(x, y + step), (x + step // 2, y), (x + step, y + step), (x + step // 2, y + step * .6)],
                          fill=c2 if (i + j) % 2 else c3)
    return img


def pack(size: tuple[int, int], body: Color, band: Color, title: str, flavour: str, mark: Image.Image | None = None,
         seal: str = "", kind: str = "pouch") -> Image.Image:
    """A product pack seen from the front: pouch, box or can. `seal` is a printed claim on the label."""
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "can":
        d.rounded_rectangle((w * .14, h * .02, w * .86, h * .98), radius=int(w * .08), fill=body + (255,))
        d.rectangle((w * .14, h * .02, w * .86, h * .09), fill=(200, 200, 205, 255))
    elif kind == "box":
        d.rectangle((w * .06, h * .04, w * .94, h * .96), fill=body + (255,))
    else:
        d.polygon([(w * .08, h * .05), (w * .92, h * .05), (w * .96, h * .95), (w * .04, h * .95)], fill=body + (255,))
        for i in range(10):
            d.line([(w * .08 + i * w * .084, h * .05), (w * .08 + i * w * .084, h * .09)], fill=band + (255,), width=2)
    d.rectangle((w * .1, h * .52, w * .9, h * .72), fill=band + (255,))
    fit_text(d, (int(w * .14), int(h * .15)), title, int(w * .72), (255, 255, 255), start=int(h * .14))
    fit_text(d, (int(w * .16), int(h * .56)), flavour, int(w * .68), (255, 255, 255), start=int(h * .09))
    if mark is not None:
        m = mark.resize((int(w * .22), int(w * .22)), Image.LANCZOS)
        img.paste(m, (int(w * .39), int(h * .30)), m)
    if seal:
        fit_text(d, (int(w * .14), int(h * .80)), seal, int(w * .72), (255, 255, 255), start=int(h * .06), bold=False)
    return img


def bottle(size: tuple[int, int], liquid: Color, label: Color, title: str, sub: str,
           mark: Image.Image | None = None) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((w * .38, h * .02, w * .62, h * .14), radius=6, fill=(60, 60, 66, 255))
    d.rounded_rectangle((w * .30, h * .12, w * .70, h * .98), radius=int(w * .1), fill=liquid + (255,))
    d.rectangle((w * .30, h * .42, w * .70, h * .82), fill=label + (255,))
    fit_text(d, (int(w * .33), int(h * .47)), title, int(w * .34), (40, 40, 40), start=int(h * .08))
    fit_text(d, (int(w * .33), int(h * .65)), sub, int(w * .34), (90, 90, 90), start=int(h * .05), bold=False)
    if mark is not None:
        m = mark.resize((int(w * .16), int(w * .16)), Image.LANCZOS)
        img.paste(m, (int(w * .42), int(h * .20)), m)
    return img


def card(size: tuple[int, int], bg: Color | Image.Image, headline: str, sub: str = "", fg: Color = (255, 255, 255),
         logo: Image.Image | None = None, logo_at: tuple[int, int] | None = None, logo_w: int = 220,
         art: Image.Image | None = None, art_at: tuple[int, int] | None = None, art_w: int = 380,
         fine: str = "") -> Image.Image:
    """A social card or poster: headline, subline, optional product art, logo and the small print."""
    img = bg.copy().convert("RGB") if isinstance(bg, Image.Image) else Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    w, h = size
    y = wrap(d, (int(w * .07), int(h * .12)), headline, int(w * (.56 if art else .86)), fg, max(30, h // 11))
    if sub:
        wrap(d, (int(w * .07), y + 12), sub, int(w * (.56 if art else .86)), fg, max(20, h // 24), bold=False)
    if art is not None:
        paste(img, art, art_at or (int(w * .62), int(h * .18)), width=art_w)
    if logo is not None:
        paste(img, logo, logo_at or (int(w * .07), int(h * .82)), width=logo_w)
    if fine:
        d.text((int(w * .07), int(h * .95)), fine, fill=fg, font=font(max(12, h // 60), False))
    return img


def portrait(size: tuple[int, int], skin: Color, bg: Color, outfit: Color, caption: str = "") -> Image.Image:
    """A stylised head-and-shoulders figure for ambassador and creator photos. Drawn, not a real face."""
    w, h = size
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    d.ellipse((w * .2, h * .72, w * .8, h * 1.3), fill=outfit)
    d.rectangle((w * .44, h * .55, w * .56, h * .75), fill=skin)
    d.ellipse((w * .3, h * .15, w * .7, h * .65), fill=skin)
    d.pieslice((w * .28, h * .1, w * .72, h * .5), 180, 360, fill=(40, 30, 28))
    d.ellipse((w * .4, h * .35, w * .45, h * .39), fill=(30, 30, 30))
    d.ellipse((w * .55, h * .35, w * .6, h * .39), fill=(30, 30, 30))
    d.arc((w * .42, h * .44, w * .58, h * .56), 20, 160, fill=(120, 50, 50), width=3)
    if caption:
        d.text((int(w * .06), int(h * .92)), caption, fill=(255, 255, 255), font=font(max(14, h // 28)))
    return img
