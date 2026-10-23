"""A brand-artwork benchmark: logos, wordmarks, app icons and packaging, used correctly and misused.

Every brand kit is drawn from parameters (name, colours, emblem, typeface), so the set is unlimited,
reproducible from a seed and free of anyone's trademark. A kit registers what a real brand library holds:
the current logo, its wordmark, an app icon, a pack front, last year's logo (retired) and a competitor's
logo (another kit's). Each is then placed in scenes the way creators place artwork:

- acceptable, which must raise nothing: on a plain background, a busy one, a photo-like one, small,
  rotated a little, recompressed as JPEG, next to other text;
- misused, which must be caught with the right finding: stretched, squashed, skewed, mirrored (logo and
  wordmark; an app icon is often symmetric), recoloured, the retired logo instead of the current one,
  and a competitor's logo in the post;
- absent: a scene with no brand artwork at all, which must raise nothing.

    .venv/bin/python -m evals.assets.generate --out /tmp/assets --count 24
"""

from __future__ import annotations

import argparse
import colorsys
import io
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = [  # macOS first, then the usual Linux paths; whatever is installed is used
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Futura.ttc", "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/System/Library/Fonts/Supplemental/Trebuchet MS Bold.ttf", "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", "/System/Library/Fonts/Supplemental/Didot.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]
EMBLEMS = ["circle", "shield", "hexagon", "stripes", "leaf", "ring", "diamond"]
WORDS = ["Fresh", "Daily", "Save", "New", "Learn", "Today", "Offer", "Shop", "Grow", "Pure", "Smart", "Free"]


def fonts() -> list[str]:
    have = [f for f in FONTS if Path(f).is_file()]
    if not have:
        raise SystemExit("no TrueType fonts found; install DejaVu or run on macOS")
    return have


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


@dataclass
class Kit:
    seed: int
    name: str
    primary: tuple[int, int, int]
    secondary: tuple[int, int, int]
    emblem: str
    font: str
    old_emblem: str
    old_font: str


def random_kit(seed: int, faces: list[str]) -> Kit:
    rnd = random.Random(seed)
    syll = ["ka", "ri", "zo", "mi", "ta", "lu", "ve", "no", "sa", "pe", "dha", "ra", "vi", "qu", "mo", "ne"]
    name = "".join(rnd.choice(syll) for _ in range(rnd.choice([2, 3]))).capitalize()
    h = rnd.random()
    emblem, old = rnd.sample(EMBLEMS, 2)
    font, old_font = rnd.sample(faces, 2) if len(faces) > 1 else (faces[0], faces[0])
    return Kit(seed, name, _hsv(h, rnd.uniform(0.65, 0.95), rnd.uniform(0.55, 0.85)),
               _hsv(h + rnd.uniform(0.3, 0.6), rnd.uniform(0.7, 1.0), rnd.uniform(0.75, 1.0)),
               emblem, font, old, old_font)


def _emblem(kind: str, size: int, primary, secondary, letter: str, font: str) -> Image.Image:
    """The brand's symbol: a shape in the primary colour with its initial or a mark in the secondary."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s, m = size, size * 0.06
    if kind == "circle":
        d.ellipse((m, m, s - m, s - m), fill=primary)
    elif kind == "shield":
        d.polygon([(m, m), (s - m, m), (s - m, s * 0.55), (s / 2, s - m), (m, s * 0.55)], fill=primary)
    elif kind == "hexagon":
        pts = [(s / 2 + (s / 2 - m) * np.cos(a), s / 2 + (s / 2 - m) * np.sin(a))
               for a in np.linspace(0, 2 * np.pi, 7)[:-1] + np.pi / 6]
        d.polygon(pts, fill=primary)
    elif kind == "stripes":
        d.rounded_rectangle((m, m, s - m, s - m), int(s * 0.18), fill=primary)
        for i in range(3):
            y = s * (0.3 + 0.17 * i)
            d.rectangle((s * 0.22, y, s * (0.78 - 0.12 * i), y + s * 0.08), fill=secondary)
        return img
    elif kind == "leaf":
        d.pieslice((m, m, s * 1.6, s * 1.6), 180, 270, fill=primary)
        d.pieslice((-s * 0.6, -s * 0.6, s - m, s - m), 0, 90, fill=primary)
    elif kind == "ring":
        d.ellipse((m, m, s - m, s - m), fill=primary)
        d.ellipse((s * 0.28, s * 0.28, s * 0.72, s * 0.72), fill=(0, 0, 0, 0))
        d.ellipse((s * 0.42, s * 0.12, s * 0.58, s * 0.28), fill=secondary)
        return img
    else:  # diamond
        d.polygon([(s / 2, m), (s - m, s / 2), (s / 2, s - m), (m, s / 2)], fill=primary)
    f = _font(font, int(s * 0.5))
    d.text((s / 2, s / 2), letter, font=f, fill=secondary, anchor="mm")
    return img


def wordmark(kit: Kit, font: str | None = None, colour=None) -> Image.Image:
    f = _font(font or kit.font, 110)
    box = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), kit.name, font=f)
    w, h = box[2] - box[0] + 40, box[3] - box[1] + 40
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((20 - box[0], 20 - box[1]), kit.name, font=f, fill=colour or kit.primary)
    return img


def logo(kit: Kit, retired: bool = False) -> Image.Image:
    """Emblem beside the name: the lockup most brand books lead with. The retired version keeps the name
    in an older typeface and an older emblem, as real refreshes do."""
    emblem = _emblem(kit.old_emblem if retired else kit.emblem, 220, kit.primary, kit.secondary,
                     kit.name[0], kit.old_font if retired else kit.font)
    text = wordmark(kit, kit.old_font if retired else kit.font, (40, 40, 48) if retired else kit.primary)
    text = text.resize((int(text.width * 160 / text.height), 160), Image.LANCZOS)
    img = Image.new("RGBA", (emblem.width + text.width + 30, 240), (0, 0, 0, 0))
    img.paste(emblem, (0, 10), emblem)
    img.paste(text, (emblem.width + 30, 40), text)
    return img


def icon(kit: Kit) -> Image.Image:
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, 299, 299), 66, fill=kit.secondary)
    emblem = _emblem(kit.emblem, 220, kit.primary, (255, 255, 255), kit.name[0], kit.font)
    img.paste(emblem, (40, 40), emblem)
    return img


def pack(kit: Kit, seed: int) -> Image.Image:
    """A pack front: colour band, logo, product line, a pattern strip. Busy by design, like real packs."""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (420, 560), (250, 248, 242, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 419, 150), fill=kit.primary)
    for i in range(0, 420, 28):
        d.polygon([(i, 520), (i + 14, 490), (i + 28, 520)], fill=kit.secondary)
    lg = logo(kit)
    lg = lg.resize((380, int(380 * lg.height / lg.width)), Image.LANCZOS)
    img.paste(lg, (20, 190), lg)
    f = _font(kit.font, 40)
    d.text((210, 380), rnd.choice(["Masala Oats", "Daily Glow", "Pure Ghee", "Cold Brew", "Rice Crisps"]),
           font=f, fill=(40, 40, 48), anchor="mm")
    d.text((210, 430), "Net wt. 500 g", font=_font(kit.font, 24), fill=(90, 90, 96), anchor="mm")
    return img


def _recolour(img: Image.Image, shift: float) -> Image.Image:
    hsv = np.asarray(img.convert("RGB").convert("HSV")).astype(int)
    coloured = hsv[..., 1] > 64
    hsv[..., 0] = np.where(coloured, (hsv[..., 0] + int(shift * 255)) % 256, hsv[..., 0])
    out = Image.fromarray(hsv.astype("uint8"), "HSV").convert("RGB")
    out.putalpha(img.getchannel("A"))
    return out


def _background(rnd: random.Random, style: str, size=(1080, 1080)) -> Image.Image:
    bg = Image.new("RGB", size, tuple(rnd.randint(205, 250) for _ in range(3)))
    d = ImageDraw.Draw(bg)
    if style == "busy":
        for _ in range(45):
            x, y, r = rnd.randint(-100, size[0]), rnd.randint(-100, size[1]), rnd.randint(20, 170)
            shape = d.ellipse if rnd.random() < 0.5 else d.rectangle
            shape((x, y, x + r, y + r * rnd.uniform(0.4, 1.6)), fill=tuple(rnd.randint(30, 235) for _ in range(3)))
        bg = bg.filter(ImageFilter.GaussianBlur(2))
    elif style == "photo":
        # Not a photograph, but what matters about one here: smooth gradients, soft blobs, sensor noise.
        y, x = np.mgrid[0:size[1], 0:size[0]]
        a, b = (np.array([rnd.randint(40, 220) for _ in range(3)]) for _ in range(2))
        t = ((x + y) / (size[0] + size[1]))[..., None]
        arr = a * (1 - t) + b * t
        for _ in range(8):
            cx, cy, r = rnd.randint(0, size[0]), rnd.randint(0, size[1]), rnd.randint(80, 300)
            blob = np.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / (2 * r * r)))[..., None]
            arr = arr * (1 - 0.6 * blob) + np.array([rnd.randint(0, 255) for _ in range(3)]) * 0.6 * blob
        arr += np.random.default_rng(rnd.randint(0, 10**6)).normal(0, 6, arr.shape)
        bg = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    elif style == "text":
        f = _font(fonts()[0], 46)
        for _ in range(14):
            d.text((rnd.randint(0, size[0] - 300), rnd.randint(0, size[1] - 60)),
                   " ".join(rnd.sample(WORDS, 3)), font=f, fill=tuple(rnd.randint(20, 160) for _ in range(3)))
    return bg


def place(art: Image.Image, rnd: random.Random, *, style: str = "plain", width: float = 0.45, wide: float = 1.0,
          tall: float = 1.0, shear: float = 0.0, mirror: bool = False, rotate: float = 0.0,
          jpeg: int | None = None) -> tuple[Image.Image, list[int]]:
    bg = _background(rnd, style)
    a = art.convert("RGBA")
    if mirror:
        a = a.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    target = int(bg.width * width)
    scale = target / a.width
    a = a.resize((max(1, int(a.width * scale * wide)), max(1, int(a.height * scale * tall))), Image.LANCZOS)
    if shear:
        k = float(np.tan(np.radians(shear)))
        a = a.transform((int(a.width + abs(k) * a.height), a.height), Image.Transform.AFFINE,
                        (1, k, -k * a.height if k > 0 else 0, 0, 1, 0), Image.BICUBIC)
    if rotate:
        a = a.rotate(rotate, Image.BICUBIC, expand=True)
    a.thumbnail((bg.width - 60, bg.height - 60))
    x, y = rnd.randint(30, bg.width - a.width - 30), rnd.randint(30, bg.height - a.height - 30)
    bg.paste(a, (x, y), a)
    ys, xs = np.nonzero(np.asarray(a)[..., 3] > 127)
    box = [int(x + xs.min()), int(y + ys.min()), int(x + xs.max() + 1), int(y + ys.max() + 1)]
    if jpeg:
        buf = io.BytesIO()
        bg.save(buf, "JPEG", quality=jpeg)
        bg = Image.open(buf).convert("RGB")
    return bg, box


# (variant, expected finding or "ok", which artwork, how it is placed). Mirroring is tested on artwork
# with lettering: a mirrored app icon is often identical to the original.
ACCEPTABLE = [
    ("plain", {"style": "plain"}), ("busy", {"style": "busy"}), ("photo", {"style": "photo"}),
    ("text", {"style": "text"}), ("small", {"style": "busy", "width": 0.2}),
    ("rotated", {"style": "busy", "rotate": 8}), ("jpeg", {"style": "photo", "jpeg": 50}),
]
MISUSED = [
    ("stretched", "VIS-ASSET-DISTORTED", {"style": "busy", "wide": 1.3}),
    ("squashed", "VIS-ASSET-DISTORTED", {"style": "photo", "wide": 0.75}),
    ("skewed", "VIS-ASSET-DISTORTED", {"style": "plain", "shear": 12}),
    ("recoloured", "VIS-ASSET-ALTERED", {"style": "plain"}),
]


def generate(out: Path, count: int, seed: int = 11) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    faces = fonts()
    kits = [random_kit(seed * 1000 + i, faces) for i in range(count)]
    cases = []
    for i, kit in enumerate(kits):
        name = f"k{i:02d}"
        rival = kits[(i + 1) % len(kits)]
        art = {"logo": logo(kit), "wordmark": wordmark(kit), "icon": icon(kit), "pack": pack(kit, kit.seed),
               "retired": logo(kit, retired=True), "competitor": logo(rival)}
        for kind, img in art.items():
            img.save(out / f"{name}_{kind}.png")
        rnd = random.Random(kit.seed)

        def scene(variant: str, expect: str, which: str, img: Image.Image, how: dict, name=name, rnd=rnd) -> None:
            pic, box = place(img, rnd, **how)
            file = f"{name}_{which}_{variant}.{'jpg' if how.get('jpeg') else 'png'}"
            pic.save(out / file, quality=95) if file.endswith("jpg") else pic.save(out / file)
            cases.append({"kit": name, "asset": which, "variant": variant, "expect": expect, "file": file,
                          "box": box})

        for which in ("logo", "wordmark", "icon", "pack"):
            for variant, how in ACCEPTABLE:
                scene(variant, "ok", which, art[which], how)
            for variant, expect, how in MISUSED:
                img = _recolour(art[which], 0.4) if variant == "recoloured" else art[which]
                scene(variant, expect, which, img, how)
        for which in ("logo", "wordmark"):
            scene("mirrored", "VIS-ASSET-DISTORTED", which, art[which], {"style": "busy", "mirror": True})
        scene("retired", "VIS-ASSET-RETIRED", "retired", art["retired"], {"style": "busy"})
        scene("retired_photo", "VIS-ASSET-RETIRED", "retired", art["retired"], {"style": "photo"})
        scene("competitor", "VIS-COMPETITOR-MARK", "competitor", art["competitor"], {"style": "busy"})
        bg = _background(rnd, rnd.choice(["busy", "photo", "text"]))
        bg.save(out / f"{name}_none_absent.png")
        cases.append({"kit": name, "asset": None, "variant": "absent", "expect": "ok",
                      "file": f"{name}_none_absent.png", "box": None})
    # Kits depend on the installed fonts as well as the seed, so the manifest records which were used:
    # the same seed on another machine can draw different lettering.
    manifest = {"seed": seed, "fonts": faces, "kits": [asdict(k) | {"id": f"k{i:02d}"} for i, k in enumerate(kits)],
                "cases": cases}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()
    m = generate(args.out, args.count, args.seed)
    print(f"{len(m['kits'])} kits, {len(m['cases'])} scenes in {args.out}")


if __name__ == "__main__":
    main()
