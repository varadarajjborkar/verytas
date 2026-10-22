"""Is this cut-out of a brand character faithful to the official artwork, and if not, what changed?

`assets.py` finds an official asset by its keypoints, which works for copies and light edits. A character
redrawn by an image or video generator keeps the look but not the pixels, so keypoints don't line up.
This module compares by *content* instead, with no alignment at all:

- Palette: every pixel of the cut-out is assigned to the nearest official colour (CIEDE2000). An official
  colour that has mostly disappeared, or a large area in a colour the artwork doesn't use, is reported by
  name ("blue covers 2% here against 61% officially", "red covers 58%").
- Parts: for each official colour, the separate shapes of that colour are counted (eyes, pupils, tail
  pieces, limbs). A different count is the "four hands instead of two" mistake, and is reported as
  "3 dark navy shapes where the artwork has 2".

Both work on flat, cartoon-style artwork, which is what brand mascots usually are. Shaded or
photographic characters break the part count into noise; there the vision model's second opinion and
the likeness score carry the decision. Pure numpy and OpenCV, so it runs on the API server as well as
the vision worker.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from verytas.checks.color import RGB, dominant_colours

SIDE = 256  # both sides are compared at this size, so counts and areas don't depend on resolution
# A pixel belongs to an official colour when it is this close in CIEDE2000; past it, it is "other".
MATCH_DE = 20.0
# Colours under this share of the official artwork (anti-aliasing, highlights) are not reported missing.
MIN_OFFICIAL_SHARE = 0.05
# A new colour is reported when it covers at least this much of the character.
MIN_NEW_SHARE = 0.08
# A shape smaller than this share of the character is noise (anti-aliasing, compression), not a part.
MIN_PART_SHARE = 0.0015
# Counting stops being meaningful for textures and stripes: colours with more official shapes are skipped.
MAX_COUNTED_PARTS = 12
# A shape counts as a part when it fills this much of its bounding box and isn't a sliver: an eye or a
# limb does, a line or an outline doesn't.
COMPACT_FILL = 0.3
COMPACT_ASPECT = 0.2
# Parts are features (eyes, limbs, tail pieces), not body panels: a big region's count depends on the thin
# lines between panels, which resizing makes and breaks.
MAX_PART_SHARE = 0.15
# Counting uses only pixels clearly of a colour; edges between two colours blend and would add slivers.
COUNT_DE = 12.0
# Official shapes smaller than this (a highlight in an eye) are details, not countable parts, and a
# candidate shape is a part when at least this fraction of the smallest official part's size.
SIGNIFICANT_PART_SHARE = 0.004
PART_SIZE_RATIO = 0.4


@dataclass
class Difference:
    kind: str  # "colour_missing" | "colour_new" | "parts"
    text: str
    colour: RGB
    severity: float  # 0..1, how far from the artwork


@dataclass
class Fidelity:
    differences: list[Difference] = field(default_factory=list)
    official_palette: list[tuple[RGB, float]] = field(default_factory=list)

    @property
    def faithful(self) -> bool:
        return not self.differences


def colour_label(rgb: RGB) -> str:
    """A colour as a person reads it in a finding: a plain word and the exact value ("blue #1A5FD1")."""
    return f"{colour_name(rgb)} {'#{:02X}{:02X}{:02X}'.format(*rgb)}"


def colour_name(rgb: RGB) -> str:
    """A plain word for a colour ("dark navy", "orange")."""
    r, g, b = (c / 255 for c in rgb)
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    if light > 0.9:
        return "white"
    if light < 0.12:
        return "black"
    if s < 0.15:
        return "grey" if light > 0.3 else "dark grey"
    hue = h * 360
    name = ("red" if hue < 15 or hue >= 345 else "orange" if hue < 40 else "yellow" if hue < 65
            else "green" if hue < 165 else "teal" if hue < 190 else "blue" if hue < 255
            else "purple" if hue < 290 else "pink")
    if light < 0.3:
        return "dark navy" if name == "blue" else f"dark {name}"
    if light > 0.7:
        return f"light {name}"
    return name


def _normalised(rgb: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Crop to the mask and scale its longer side to SIDE, so two cut-outs compare at one size."""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        raise ValueError("empty mask")
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgb, mask = rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    scale = SIDE / max(rgb.shape[:2])
    size = (max(1, round(rgb.shape[1] * scale)), max(1, round(rgb.shape[0] * scale)))
    return (cv2.resize(rgb, size, interpolation=cv2.INTER_AREA),
            cv2.resize(mask.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool))


def _lab(rgb: np.ndarray) -> np.ndarray:
    """CIELAB (D65) of (N, 3) sRGB values: checks.color.rgb_to_lab vectorised, same constants, so a
    distance here is the same ΔE the palette rule reports."""
    c = rgb.reshape(-1, 3).astype(np.float64) / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ np.array([[0.4124564, 0.2126729, 0.0193339],
                          [0.3575761, 0.7151522, 0.1191920],
                          [0.1804375, 0.0721750, 0.9503041]]) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


def _ciede2000(lab: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """CIEDE2000 from every row of `lab` (N, 3) to every row of `ref` (K, 3): (N, K)."""
    L1, a1, b1 = (lab[:, None, i] for i in range(3))
    L2, a2, b2 = (ref[None, :, i] for i in range(3))
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm**7 / (Cm**7 + 25**7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lpm, Cpm = (L1 + L2) / 2, (C1p + C2p) / 2
    hsum = h1p + h2p
    wrapped = np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)
    hpm = np.where(C1p * C2p == 0, hsum, np.where(np.abs(h1p - h2p) <= 180, hsum / 2, wrapped))
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    SL = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
    SC, SH = 1 + 0.045 * Cpm, 1 + 0.015 * Cpm * T
    RT = -2 * np.sqrt(Cpm**7 / (Cpm**7 + 25**7)) * np.sin(np.radians(60 * np.exp(-(((hpm - 275) / 25) ** 2))))
    return np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH))


def _palette(rgb: np.ndarray, mask: np.ndarray) -> list[tuple[RGB, float]]:
    """The artwork's own colours: k-means, near-duplicates merged, slivers dropped."""
    pixels = rgb[mask]
    if len(pixels) > 40_000:
        pixels = pixels[np.random.default_rng(0).choice(len(pixels), 40_000, replace=False)]
    found = dominant_colours(pixels, k=10, iters=20)
    merged: list[list] = []
    for colour, share in found:
        lab = _lab(np.array([colour]))
        twin = next((m for m in merged if _ciede2000(lab, _lab(np.array([m[0]])))[0, 0] < 10), None)
        if twin:
            twin[1] += share
        else:
            merged.append([colour, share])
    return [(c, s) for c, s in merged if s >= 0.01]


def _assign(rgb: np.ndarray, mask: np.ndarray, palette: list[tuple[RGB, float]],
            within: float = MATCH_DE) -> np.ndarray:
    """Each masked pixel's official colour index, -1 for "other", -2 outside the mask."""
    labels = np.full(mask.shape, -2, dtype=np.int32)
    dist = _ciede2000(_lab(rgb[mask]), _lab(np.array([c for c, _ in palette])))
    nearest = dist.argmin(axis=1)
    labels[mask] = np.where(dist.min(axis=1) <= within, nearest, -1)
    return labels


def _parts(labels: np.ndarray, index: int, area: int) -> list[float]:
    """Shares of the character covered by each compact shape of one colour: eyes, pupils, limbs, tail
    pieces. Lines and outlines are left out, since resizing or a generator's blur splits and joins them
    without anything having changed."""
    n, _, stats, _ = cv2.connectedComponentsWithStats((labels == index).astype(np.uint8), connectivity=8)
    floor = max(12, MIN_PART_SHARE * area)
    shares = []
    for i in range(1, n):
        w, h, a = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT], stats[i, cv2.CC_STAT_AREA]
        if (floor <= a <= MAX_PART_SHARE * area and a / (w * h) >= COMPACT_FILL
                and min(w, h) / max(w, h) >= COMPACT_ASPECT):
            shares.append(a / area)
    return shares


def _count(official: list[float], candidate: list[float]) -> tuple[int, int] | None:
    """(official, candidate) counts of the parts that matter, or None when the colour has none.

    Only official parts clearly above the speck floor count (a highlight in an eye is not a part), and a
    candidate shape counts when it is comparable in size to the smallest of those: a compression speck
    near a part's size line must not flip the count."""
    significant = [s for s in official if s >= SIGNIFICANT_PART_SHARE]
    if not significant:
        return None
    least = min(significant)
    return len(significant), sum(s >= PART_SIZE_RATIO * least for s in candidate)


def official_reference(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """RGB pixels and mask of official artwork: its alpha when it has one, else what isn't near-white
    background."""
    rgba = np.asarray(img.convert("RGBA"))
    mask = rgba[..., 3] > 127
    if mask.all():
        mask = (rgba[..., :3].astype(int).sum(axis=2) < 735)
    return rgba[..., :3], mask


def compare(official: tuple[np.ndarray, np.ndarray], candidate: tuple[np.ndarray, np.ndarray]) -> Fidelity:
    """Differences between official artwork and a cut-out of the same character, each as (rgb, mask)."""
    o_rgb, o_mask = _normalised(*official)
    c_rgb, c_mask = _normalised(*candidate)
    palette = _palette(o_rgb, o_mask)
    out = Fidelity(official_palette=palette)
    o_lab, c_lab = _assign(o_rgb, o_mask, palette), _assign(c_rgb, c_mask, palette)
    o_area, c_area = int(o_mask.sum()), int(c_mask.sum())

    for i, (colour, _) in enumerate(palette):
        o_share = float((o_lab == i).sum()) / o_area
        c_share = float((c_lab == i).sum()) / c_area
        if o_share >= MIN_OFFICIAL_SHARE and c_share < 0.3 * o_share:
            out.differences.append(Difference(
                "colour_missing", f"{colour_label(colour)} covers {c_share:.0%} here; the artwork uses it for "
                f"{o_share:.0%}", colour, min(1.0, 1 - c_share / o_share)))

    other = c_rgb[c_lab == -1]
    if len(other) / c_area >= MIN_NEW_SHARE:
        for colour, share in dominant_colours(other, k=3):
            covered = share * len(other) / c_area
            if covered >= MIN_NEW_SHARE:
                out.differences.append(Difference(
                    "colour_new", f"{colour_label(colour)} covers {covered:.0%}, a colour the artwork doesn't use",
                    colour, min(1.0, covered * 2)))

    gone = {d.colour for d in out.differences if d.kind == "colour_missing"}
    o_core, c_core = _assign(o_rgb, o_mask, palette, COUNT_DE), _assign(c_rgb, c_mask, palette, COUNT_DE)
    for i, (colour, _) in enumerate(palette):
        if colour in gone:
            continue  # already reported as missing; counting its shapes would only repeat that
        counted = _count(_parts(o_core, i, o_area), _parts(c_core, i, c_area))
        if counted is None or counted[0] > MAX_COUNTED_PARTS:
            continue
        want, got = counted
        if got != want:
            out.differences.append(Difference(
                "parts", f"{got} {colour_label(colour)} shape{'s' if got != 1 else ''} where the artwork has {want}",
                colour, min(1.0, abs(got - want) / want)))
    return out
