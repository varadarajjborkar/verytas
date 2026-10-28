"""A mascot benchmark: many brand characters, each placed in scenes as the real thing, as a faulty
redraw, and as somebody else's character.

Every mascot is drawn from parameters (body shape, colours, eyes, mouth, limbs, accessories, tail), so
the set is unlimited, reproducible from a seed and free of anyone's trademark. For each one:

- the official artwork (what a brand would register in the library);
- acceptable variants that must pass: resized, rotated, JPEG-compressed, lightly "redrawn" (warped,
  softened, a small colour drift), on plain and busy backgrounds;
- defects that must be caught and named: recolour, colour swap, an extra or a missing eye, an extra or
  a missing limb, a missing accessory, an extra tail piece, stretched proportions;
- near-twins: same body shape and colours, different face and accessories (another brand's character
  built from the same template).

Other mascots in the set are the ordinary impostors. Scenes and a JSON manifest with ground-truth boxes
are written to an output folder:

    .venv/bin/python -m evals.mascots.generate --out /tmp/mascots --count 30
"""

from __future__ import annotations

import argparse
import colorsys
import io
import json
import math
import random
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 400
SHAPES = ["circle", "square", "kite", "triangle", "blob", "pear", "egg"]
ACCESSORIES = ["hat", "antenna", "bow", "horns", "none"]


@dataclass
class Spec:
    seed: int
    shape: str
    body: tuple[int, int, int]
    panel: tuple[int, int, int]
    limb: tuple[int, int, int]
    accent: tuple[int, int, int]
    eyes: int = 2
    pupil: tuple[int, int, int] = (25, 30, 45)
    mouth: str = "smile"
    arms: int = 2
    legs: int = 2
    accessory: str = "none"
    tail: int = 0
    outline: bool = True
    stretch: float = 1.0
    removed: list[str] = field(default_factory=list)


def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def random_spec(seed: int) -> Spec:
    rnd = random.Random(seed)
    hue = rnd.random()
    return Spec(
        seed=seed, shape=rnd.choice(SHAPES),
        body=_hsv(hue, rnd.uniform(0.55, 0.9), rnd.uniform(0.6, 0.9)),
        panel=_hsv(hue + rnd.choice([0.0, 0.08, 0.5]), rnd.uniform(0.2, 0.5), rnd.uniform(0.85, 1.0)),
        limb=_hsv(hue + rnd.uniform(-0.05, 0.05), rnd.uniform(0.6, 0.9), rnd.uniform(0.4, 0.65)),
        accent=_hsv(hue + rnd.choice([0.33, 0.5, 0.66]), 0.85, 0.95),
        eyes=rnd.choice([2, 2, 2, 1, 3]), mouth=rnd.choice(["smile", "open", "smile"]),
        arms=rnd.choice([2, 2, 0]), legs=rnd.choice([2, 2, 0]),
        accessory=rnd.choice(ACCESSORIES), tail=rnd.choice([0, 0, 3, 4]), outline=rnd.random() < 0.6,
    )


def _body(d: ImageDraw.ImageDraw, s: Spec, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    line = (20, 20, 30) if s.outline else None
    w = 5 if s.outline else 0
    if s.shape == "circle":
        d.ellipse(box, fill=s.body, outline=line, width=w)
        d.ellipse((cx - (x1 - x0) * 0.28, cy, cx + (x1 - x0) * 0.28, y1 - 18), fill=s.panel)
    elif s.shape == "square":
        d.rounded_rectangle(box, radius=40, fill=s.body, outline=line, width=w)
        d.rounded_rectangle((x0 + 30, cy + 10, x1 - 30, y1 - 20), radius=20, fill=s.panel)
    elif s.shape == "kite":
        d.polygon([(cx, y0), (x1, cy), (cx, y1), (x0, cy)], fill=s.body, outline=line, width=w)
        d.polygon([(cx, y0), (x1, cy), (cx, cy)], fill=s.panel)
    elif s.shape == "triangle":
        d.polygon([(cx, y0), (x1, y1), (x0, y1)], fill=s.body, outline=line, width=w)
        d.polygon([(cx, cy + 20), (cx + 60, y1 - 8), (cx - 60, y1 - 8)], fill=s.panel)
    elif s.shape == "blob":
        pts = [(cx + (x1 - x0) / 2 * math.copysign(abs(math.cos(t)) ** 0.6, math.cos(t)),
                cy + (y1 - y0) / 2 * math.copysign(abs(math.sin(t)) ** 0.6, math.sin(t)))
               for t in np.linspace(0, 2 * math.pi, 80)]
        d.polygon(pts, fill=s.body, outline=line, width=w)
        d.ellipse((cx - 50, cy + 20, cx + 50, y1 - 25), fill=s.panel)
    elif s.shape == "pear":
        d.ellipse((x0 + 25, y0, x1 - 25, cy + 20), fill=s.body, outline=line, width=w)
        d.ellipse((x0, cy - 30, x1, y1), fill=s.body, outline=line, width=w)
        d.ellipse((cx - 55, cy + 10, cx + 55, y1 - 20), fill=s.panel)
    else:  # egg
        d.ellipse((x0 + 15, y0, x1 - 15, y1), fill=s.body, outline=line, width=w)
        d.ellipse((cx - 50, cy + 15, cx + 50, y1 - 20), fill=s.panel)


def draw(s: Spec) -> Image.Image:
    """The character on a transparent canvas."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = (100, 90, 300, 300)
    cx, top, bottom = 200, 90, 300
    if s.tail:
        for i in range(s.tail):
            y = 300 - i * 26
            d.polygon([(300, y), (345 + (i % 2) * 10, y - 12), (300, y - 22)], fill=s.accent)
    # Arms: left, right, then a second right one (the "extra limb" defect).
    for side, y in [(-1, 185), (1, 185), (1, 240)][:s.arms]:
        d.ellipse((cx + side * 108 - 22, y, cx + side * 108 + 22, y + 44), fill=s.limb)
    for side in ([-1, 1] if s.legs >= 2 else [-1] if s.legs == 1 else []):
        d.rounded_rectangle((cx + side * 45 - 18, 285, cx + side * 45 + 18, 340), radius=12, fill=s.limb)
    _body(d, s, box)
    if s.accessory == "hat":
        d.polygon([(cx - 45, top + 12), (cx + 45, top + 12), (cx, top - 70)], fill=s.accent)
    elif s.accessory == "antenna":
        for side in (-1, 1):
            d.line([(cx + side * 25, top + 10), (cx + side * 45, top - 50)], fill=(30, 30, 40), width=5)
            d.ellipse((cx + side * 45 - 14, top - 64, cx + side * 45 + 14, top - 36), fill=s.accent)
    elif s.accessory == "bow":
        d.polygon([(cx, bottom - 75), (cx - 40, bottom - 95), (cx - 40, bottom - 55)], fill=s.accent)
        d.polygon([(cx, bottom - 75), (cx + 40, bottom - 95), (cx + 40, bottom - 55)], fill=s.accent)
    elif s.accessory == "horns":
        for side in (-1, 1):
            horn = [(cx + side * 30, top + 25), (cx + side * 60, top - 35), (cx + side * 70, top + 30)]
            d.polygon(horn, fill=s.accent)
    xs = {1: [cx], 2: [cx - 40, cx + 40], 3: [cx - 55, cx, cx + 55]}.get(s.eyes, [])
    for x in xs:
        d.ellipse((x - 24, 150, x + 24, 198), fill="white", outline=(20, 20, 30), width=3)
        d.ellipse((x - 11, 162, x + 11, 186), fill=s.pupil)
    if s.mouth == "smile":
        d.arc((cx - 35, 195, cx + 35, 240), 15, 165, fill=(30, 25, 30), width=6)
    elif s.mouth == "open":
        d.ellipse((cx - 20, 210, cx + 20, 240), fill=(140, 30, 40))
    if s.stretch != 1.0:
        # Wider, at the same height. (This used to be squeezed back into a square, which undid the
        # stretch: the "stretched" scenes showed the character in proportion.)
        img = img.resize((int(SIZE * s.stretch), SIZE), Image.LANCZOS)
    return img


def _recolour(img: Image.Image, shift: float) -> Image.Image:
    """Rotate the hue of every saturated pixel: the character in someone else's colours."""
    hsv = np.asarray(img.convert("RGB").convert("HSV")).astype(int)
    coloured = hsv[..., 1] > 64
    hsv[..., 0] = np.where(coloured, (hsv[..., 0] + int(shift * 255)) % 256, hsv[..., 0])
    rgb = Image.fromarray(hsv.astype("uint8"), "HSV").convert("RGB")
    rgb.putalpha(img.getchannel("A"))
    return rgb


def defects(s: Spec) -> dict[str, tuple[Image.Image, str]]:
    """Faulty versions of a character, each with the kind of difference that names it."""
    out: dict[str, tuple[Image.Image, str]] = {
        "recolour": (_recolour(draw(s), 0.4), "colour"),
        "swap_colours": (draw(replace(s, body=s.panel, panel=s.body)), "colour"),
    }
    if s.eyes < 3:
        out["extra_eye"] = (draw(replace(s, eyes=s.eyes + 1)), "parts")
    if s.eyes >= 2:
        out["missing_eye"] = (draw(replace(s, eyes=s.eyes - 1)), "parts")
    if s.arms == 2:
        out["extra_limb"] = (draw(replace(s, arms=3)), "parts")
        out["missing_limb"] = (draw(replace(s, arms=1)), "parts")
    if s.accessory != "none":
        out["missing_accessory"] = (draw(replace(s, accessory="none")), "parts")
    if s.tail:
        out["extra_tail_piece"] = (draw(replace(s, tail=s.tail + 1)), "parts")
    out["stretched"] = (draw(replace(s, stretch=1.35)), "shape")
    return out


def twin(s: Spec) -> Image.Image:
    """Another brand's character from the same template: same body and colours, different face and gear."""
    rnd = random.Random(s.seed + 10_000)
    return draw(replace(s, eyes=rnd.choice([e for e in (1, 2, 3) if e != s.eyes]),
                        mouth="open" if s.mouth == "smile" else "smile",
                        accessory=rnd.choice([a for a in ACCESSORIES if a != s.accessory]),
                        arms=0 if s.arms else 2, tail=0 if s.tail else 3))


def _redraw(img: Image.Image, rnd: random.Random) -> Image.Image:
    """What a careful generator does to correct artwork: a slight warp, softer edges, a small drift."""
    j = [rnd.randint(-14, 14) for _ in range(8)]
    quad = (0 + j[0], 0 + j[1], 0 + j[2], SIZE + j[3], SIZE + j[4], SIZE + j[5], SIZE + j[6], 0 + j[7])
    w = img.transform(img.size, Image.Transform.QUAD, quad, Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))
    a = np.asarray(w).astype(int)
    a[..., :3] = np.clip(a[..., :3] + [rnd.randint(-8, 8) for _ in range(3)], 0, 255)
    return Image.fromarray(a.astype("uint8"), "RGBA")


def _background(rnd: random.Random, busy: bool, size=(900, 700)) -> Image.Image:
    base = tuple(rnd.randint(200, 250) for _ in range(3))
    bg = Image.new("RGB", size, base)
    if busy:
        d = ImageDraw.Draw(bg)
        for _ in range(40):
            x, y = rnd.randint(-100, size[0]), rnd.randint(-100, size[1])
            r = rnd.randint(20, 160)
            colour = tuple(rnd.randint(40, 230) for _ in range(3))
            shape = d.ellipse if rnd.random() < 0.5 else d.rectangle
            shape((x, y, x + r, y + r * rnd.uniform(0.4, 1.6)), fill=colour)
        bg = bg.filter(ImageFilter.GaussianBlur(2))
    return bg


def place(character: Image.Image, rnd: random.Random, *, busy: bool, scale: float = 1.0, angle: float = 0.0,
          jpeg: int | None = None) -> tuple[Image.Image, list[int], Image.Image]:
    """The character in a scene; returns the scene, the character's true box and its true mask."""
    c = character.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else character
    side = int(300 * scale)
    # The character's height sets its size and its own proportions are kept, so a stretched one stays so.
    c = c.resize((max(1, round(side * c.width / c.height)), side), Image.LANCZOS)
    bg = _background(rnd, busy)
    x, y = rnd.randint(30, bg.width - c.width - 30), rnd.randint(30, bg.height - c.height - 30)
    bg.paste(c, (x, y), c)
    truth = Image.new("L", bg.size, 0)
    truth.paste(c.getchannel("A").point(lambda a: 255 if a > 127 else 0), (x, y))
    ys, xs = np.nonzero(np.asarray(c)[..., 3] > 127)
    box = [int(x + xs.min()), int(y + ys.min()), int(x + xs.max() + 1), int(y + ys.max() + 1)]
    if jpeg:
        buf = io.BytesIO()
        bg.save(buf, "JPEG", quality=jpeg)
        bg = Image.open(buf).convert("RGB")
    return bg, box, truth


def generate(out: Path, count: int, seed: int = 7) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for m in range(count):
        s = random_spec(seed * 1000 + m)
        name = f"m{m:02d}"
        official = draw(s)
        official.save(out / f"{name}_official.png")
        rnd = random.Random(s.seed)
        cases: list[tuple[str, str, Image.Image, dict]] = [
            ("plain", "ok", official, {"busy": False}),
            ("busy", "ok", official, {"busy": True}),
            ("small", "ok", official, {"busy": False, "scale": 0.45}),
            ("rotated", "ok", official, {"busy": True, "angle": rnd.choice([-14, 12])}),
            ("jpeg", "ok", official, {"busy": True, "jpeg": 45}),
            ("redrawn", "ok", _redraw(official, rnd), {"busy": False}),
            ("twin", "impostor", twin(s), {"busy": False}),
        ]
        for kind, (img, expect) in defects(s).items():
            cases.append((kind, f"defect:{expect}", img, {"busy": rnd.random() < 0.5}))
        for variant, expect, img, how in cases:
            scene, box, truth = place(img, rnd, **how)
            file = f"{name}_{variant}.jpg" if how.get("jpeg") else f"{name}_{variant}.png"
            scene.save(out / file)
            # The true mask is its own file, not part of the scene, so the scenes are byte for byte what
            # they were; it lets mask quality be measured against the truth.
            truth.save(out / f"{name}_{variant}_truth.png")
            rows.append({"mascot": name, "variant": variant, "expect": expect, "file": file, "box": box,
                         "busy": bool(how.get("busy"))})
        (out / f"{name}.json").write_text(json.dumps(asdict(s)))
    manifest = {"seed": seed, "count": count, "cases": rows}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.mascots.generate")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--count", type=int, default=30)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    m = generate(args.out, args.count, args.seed)
    print(f"{args.count} mascots, {len(m['cases'])} scenes in {args.out}")


if __name__ == "__main__":
    main()
