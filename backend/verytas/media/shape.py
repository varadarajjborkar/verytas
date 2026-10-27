"""Shape-first location of flat artwork whose colours were changed.

`assets.py` finds official artwork by the grey pattern of its keypoints. A hue swap on a small flat icon
(a rounded square, an emblem, one letter) turns light regions dark and the other way round, so that
pattern is gone and the icon is never found, let alone compared. This module finds it by outline
instead and leaves the judging of colour to the comparison that follows:

1. Where is the shape? Edge direction, not brightness, is matched: the colour gradient (Di Zenzo, over
   Lab) gives each edge pixel a direction taken modulo 180 degrees, so a light-on-dark edge and a
   dark-on-light edge look alike. The artwork's edge directions are correlated over the scene at a range
   of scales (coarse, then fine around the best few), as in shape-based template matching.
2. Is it the artwork, or just similar edges? Four gates, all measured on the benchmark: enough of the
   artwork's edges are met in the right direction; each flat colour region of the artwork is still one
   flat colour in the scene; regions that contrasted in the artwork still contrast; and the silhouette
   stands out from what surrounds it (without that, an emblem inside a logo lockup would match an app
   icon made of the same emblem on a plain tile).
3. What changed? The scene colour found in each region of the artwork is returned beside the official
   one, so a finding can say the palette was swapped rather than only that something differs.

Only compact flat artwork is eligible (see `build`): it is where grey keypoints fail, and a search per
asset per image must stay cheap.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Compact flat artwork: icons, badges, emblems.
MAX_ASPECT = 1.5
MIN_FILL = 0.5  # share of the artwork's box that is artwork
MAX_REGIONS = 5
MIN_REGIONS = 2
MIN_FLATNESS = 0.9  # share of the artwork's interior within REGION_TOL of a palette colour
REGION_MERGE = 15.0  # palette colours closer than this (Lab) are one region
REGION_TOL = 14.0
REGION_MIN_SHARE = 0.02
EDGE_STRENGTH = 14.0  # colour gradient magnitude (Lab per pixel) that counts as an edge
SPREAD_SIGMA = 1.5  # position tolerance of an edge, in pixels at search resolution
MIN_COHERENCE = 0.35  # blurred direction vectors shorter than this disagree with themselves
COARSE_SIDE = 200
FINE_SIDE = 450
COARSE_STEP = 1.06
FINE_SCALES = np.geomspace(0.9, 1.1, 11)
MIN_SIDE = 100  # smaller placements are not judged anyway (assets.MIN_JUDGE_SIDE)
COARSE_FLOOR = 0.55  # a coarse hit scoring under this is not refined
KEEP = 3  # distinct coarse hits refined
# Gates on a refined placement, set on the generated benchmark (evals/assets): recoloured icons score
# 0.85 to 0.97 on recall; the best placements elsewhere reach 0.84 and fail the silhouette gate.
MIN_RECALL = 0.8
MIN_UNIFORMITY = 0.9
UNIFORM_TOL = 16.0
MIN_CONTRAST = 12.0  # between regions that differ by more than DIFFER in the artwork
DIFFER = 25.0
MIN_SILHOUETTE = 0.8  # share of the surrounding ring unlike the region it touches
RING = 6
SWAPPED = 20.0  # a region whose scene colour is this far from the official one was recoloured


@dataclass
class ShapeModel:
    labels: np.ndarray  # int16 per artwork pixel: palette region, -1 outside the artwork's interior
    palette: np.ndarray  # (regions, 3) Lab
    outer: np.ndarray  # int16: the region touching the silhouette, extended over the ring outside it, else -1


@dataclass
class Placement:
    box: tuple[float, float, float, float]  # x, y, width, height in the scene's working pixels
    recall: float
    swapped: list[tuple[str, str]]  # (official colour, colour found), as hex, for each recoloured region


def _lab(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    return lab


def _hex(lab: np.ndarray) -> str:
    one = np.array([[[lab[0] * 255.0 / 100.0, lab[1] + 128.0, lab[2] + 128.0]]], np.float32)
    r, g, b = cv2.cvtColor(np.clip(one, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)[0, 0]
    return f"#{r:02x}{g:02x}{b:02x}"


def build(rgb: np.ndarray, mask: np.ndarray) -> ShapeModel | None:
    """The shape model of an official asset, or None when it isn't compact flat artwork."""
    h, w = mask.shape
    if max(h, w) / min(h, w) > MAX_ASPECT or mask.mean() < MIN_FILL:
        return None
    interior = cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    lab = _lab(rgb)
    px = lab[interior]
    if len(px) < 400:
        return None
    sample = np.ascontiguousarray(px[:: max(1, len(px) // 20000)])
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.5)
    cv2.setRNGSeed(7)  # the palette, and so a verdict, must not vary between runs
    _, _, centres = cv2.kmeans(sample, MAX_REGIONS + 1, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    groups: list[list[np.ndarray]] = []
    for c in centres:
        for g in groups:
            if np.linalg.norm(g[0] - c) < REGION_MERGE:
                g.append(c)
                break
        else:
            groups.append([c])
    palette = np.array([np.mean(g, axis=0) for g in groups])
    for _ in range(2):  # a region too small to measure in the scene is not a region
        dist = np.linalg.norm(px[:, None, :] - palette[None], axis=2)
        pick = dist.argmin(axis=1)
        palette = palette[[i for i in range(len(palette)) if (pick == i).mean() >= REGION_MIN_SHARE]]
        if not len(palette):
            return None
    dist = np.linalg.norm(px[:, None, :] - palette[None], axis=2)
    near = dist.min(axis=1) < REGION_TOL
    if not MIN_REGIONS <= len(palette) <= MAX_REGIONS or near.mean() < MIN_FLATNESS:
        return None
    labels = np.full((h, w), -1, np.int16)
    labels[interior] = np.where(near, dist.argmin(axis=1), -1)
    # Extend each region outwards (the larger index wins a tie, which only happens at a corner of regions)
    # so the pixels just outside the silhouette know which region they touch.
    edge = (labels + 1).astype(np.uint8)
    grown = edge.copy()
    for _ in range(RING + 3):
        grown = np.where(grown > 0, grown, cv2.dilate(grown, np.ones((3, 3), np.uint8)))
    outside = cv2.dilate(mask.astype(np.uint8), np.ones((2 * RING + 1,) * 2, np.uint8)) > 0
    ring = outside & (cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) == 0)
    outer = np.where(ring & (grown > 0), grown.astype(np.int16) - 1, -1).astype(np.int16)
    return ShapeModel(labels, palette, outer)


def _orient(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Doubled-angle unit vector of the dominant colour gradient (so opposite directions agree) and its
    strength. The doubled angle of an eigenvector of the structure tensor is atan2(2 gxy, gxx - gyy)."""
    lab = cv2.GaussianBlur(_lab(rgb), (0, 0), 0.8)
    gxx = gyy = gxy = 0
    for i in range(3):
        gx = cv2.Sobel(lab[..., i], cv2.CV_32F, 1, 0, ksize=3) / 8
        gy = cv2.Sobel(lab[..., i], cv2.CV_32F, 0, 1, ksize=3) / 8
        gxx, gyy, gxy = gxx + gx * gx, gyy + gy * gy, gxy + gx * gy
    a, b = gxx - gyy, 2 * gxy
    n = np.sqrt(a * a + b * b) + 1e-9
    return a / n, b / n, np.sqrt(0.5 * (gxx + gyy + n))


def _edges(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    c, s, strength = _orient(rgb)
    w = (strength > EDGE_STRENGTH).astype(np.float32)
    return c * w, s * w, w


def _spread(c: np.ndarray, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each edge pixel's direction, made to cover its neighbourhood: blur, keep only where the nearby
    directions agree, and restore unit length so a straight edge scores 1 rather than 0.6."""
    bc, bs = cv2.GaussianBlur(c, (0, 0), SPREAD_SIGMA), cv2.GaussianBlur(s, (0, 0), SPREAD_SIGMA)
    m = np.sqrt(bc * bc + bs * bs)
    keep = m > MIN_COHERENCE
    return np.where(keep, bc / (m + 1e-9), 0).astype(np.float32), np.where(keep, bs / (m + 1e-9), 0).astype(np.float32)


class SceneShape:
    """Edge-direction fields of one scene at the two search resolutions. Built once, shared by every asset."""

    def __init__(self, rgb: np.ndarray):
        self.rgb = rgb
        self.coarse_k = min(1.0, COARSE_SIDE / max(rgb.shape[:2]))
        self.fine_k = min(1.0, FINE_SIDE / max(rgb.shape[:2]))
        self.coarse = self._field(self.coarse_k)
        self.fine = self._field(self.fine_k)

    def _field(self, k: float) -> tuple[np.ndarray, np.ndarray]:
        small = cv2.resize(self.rgb, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else self.rgb
        c, s, _ = _edges(small)
        return _spread(c, s)


def _recall(field: tuple[np.ndarray, np.ndarray], rgb: np.ndarray, tw: int, th: int) -> np.ndarray:
    """Share of the artwork's edge pixels, drawn tw by th, that meet a scene edge of the same direction,
    at every position."""
    c, s, w = _edges(cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_AREA))
    n = float(w.sum())
    if n < 20:
        return np.zeros((1, 1), np.float32)
    return (cv2.matchTemplate(field[0], c, cv2.TM_CCORR) + cv2.matchTemplate(field[1], s, cv2.TM_CCORR)) / n


Box = tuple[float, float, float, float]


def search(model: ShapeModel, rgb: np.ndarray, scene: SceneShape) -> tuple[float, Box] | None:
    """The best (recall, box) placement of the artwork's edges in the scene, before any gate; boxes in the
    scene's working pixels."""
    ah, aw = model.labels.shape
    h0, w0 = scene.rgb.shape[:2]
    k1 = scene.coarse_k
    hits = []
    size = MIN_SIDE * k1
    top = 0.95 * min(scene.coarse[0].shape[1] / aw, scene.coarse[0].shape[0] / ah)
    sc = size / max(aw, ah)
    while sc <= top:
        tw, th = round(aw * sc), round(ah * sc)
        if min(tw, th) >= 12 and tw < scene.coarse[0].shape[1] and th < scene.coarse[0].shape[0]:
            _, score, _, at = cv2.minMaxLoc(_recall(scene.coarse, rgb, tw, th))
            if score >= COARSE_FLOOR:
                hits.append((float(score), sc / k1, at[0] / k1, at[1] / k1))
        sc *= COARSE_STEP
    hits.sort(reverse=True)
    best, used = None, []
    k2 = scene.fine_k
    fine_h, fine_w = scene.fine[0].shape
    for _, s0, x0, y0 in hits:
        if len(used) == KEEP:
            break
        if any(abs(x0 - ux) < 0.2 * aw * s0 and abs(y0 - uy) < 0.2 * ah * s0 and abs(np.log(s0 / us)) < 0.2
               for ux, uy, us in used):
            continue
        used.append((x0, y0, s0))
        pad = 0.15 * max(aw, ah) * s0
        x_a, y_a = max(0, int((x0 - pad) * k2)), max(0, int((y0 - pad) * k2))
        x_b, y_b = min(fine_w, int((x0 + aw * s0 + pad) * k2)), min(fine_h, int((y0 + ah * s0 + pad) * k2))
        window = (scene.fine[0][y_a:y_b, x_a:x_b], scene.fine[1][y_a:y_b, x_a:x_b])
        for f in FINE_SCALES:
            tw, th = round(aw * s0 * f * k2), round(ah * s0 * f * k2)
            if tw < 16 or th < 16 or tw >= window[0].shape[1] or th >= window[0].shape[0]:
                continue
            _, score, _, at = cv2.minMaxLoc(_recall(window, rgb, tw, th))
            if best is None or score > best[0]:
                best = (float(score), ((x_a + at[0]) / k2, (y_a + at[1]) / k2, tw / k2, th / k2))
    return best


def locate(model: ShapeModel, rgb: np.ndarray, scene: SceneShape) -> Placement | None:
    """Where the artwork is by shape, if anywhere, after the verification gates."""
    best = search(model, rgb, scene)
    if best is None or best[0] < MIN_RECALL:
        return None
    verdict = _verify(model, scene.rgb, best[1])
    return None if verdict is None else Placement(best[1], round(best[0], 3), verdict)


@dataclass
class Palette:
    """What a shape match shows about colour, before any gate is applied."""
    found: dict[int, np.ndarray]  # Lab colour of each region that is big enough to measure
    uniformity: float  # share of those regions' pixels within UNIFORM_TOL of their region's colour
    contrast: float  # smallest scene difference between two regions that differ in the artwork
    silhouette: float  # share of the ring outside the artwork unlike the region it touches
    ring: int  # pixels in that ring that lie inside the image


def measure(model: ShapeModel, scene_rgb: np.ndarray, box: tuple[float, float, float, float]) -> Palette:
    x, y, bw, bh = box
    ah, aw = model.labels.shape
    to_scene = np.array([[bw / aw, 0, x], [0, bh / ah, y]], np.float32)
    size = (scene_rgb.shape[1], scene_rgb.shape[0])
    inside = cv2.warpAffine(model.labels, to_scene, size, flags=cv2.INTER_NEAREST, borderValue=-1)
    ring = cv2.warpAffine(model.outer, to_scene, size, flags=cv2.INTER_NEAREST, borderValue=-1)
    lab = _lab(scene_rgb)
    found: dict[int, np.ndarray] = {}
    weight = uniform = 0.0
    for i in range(len(model.palette)):
        region = cv2.erode((inside == i).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        if region.sum() < 30:
            continue
        px = lab[region]
        found[i] = np.median(px, axis=0)
        uniform += float((np.linalg.norm(px - found[i], axis=1) < UNIFORM_TOL).sum())
        weight += len(px)
    contrast = min((float(np.linalg.norm(found[a] - found[b])) for a in found for b in found
                    if a < b and np.linalg.norm(model.palette[a] - model.palette[b]) > DIFFER), default=99.0)
    # Ring pixels outside the image are not evidence either way.
    unlike = total = 0
    for i, colour in found.items():
        at = ring == i
        if at.any():
            unlike += int((np.linalg.norm(lab[at] - colour, axis=1) > MIN_CONTRAST).sum())
            total += int(at.sum())
    return Palette(found, uniform / weight if weight else 0.0, contrast, unlike / total if total else 0.0, total)


def _verify(model: ShapeModel, scene_rgb: np.ndarray, box: tuple[float, float, float, float]
            ) -> list[tuple[str, str]] | None:
    """The (official, found) hex pairs of every region whose colour changed, or None when this is not the
    artwork in other colours."""
    got = measure(model, scene_rgb, box)
    if len(got.found) < MIN_REGIONS or got.uniformity < MIN_UNIFORMITY or got.contrast < MIN_CONTRAST \
            or got.ring < 100 or got.silhouette < MIN_SILHOUETTE:
        return None
    return [(_hex(model.palette[i]), _hex(c)) for i, c in got.found.items()
            if np.linalg.norm(model.palette[i] - c) > SWAPPED]
