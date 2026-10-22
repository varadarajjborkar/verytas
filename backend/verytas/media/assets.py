"""Brand-asset matching: is the official artwork here, unchanged, and only the approved part?

Three questions per official asset, answered from pixels alone:

1. Where is it? SIFT keypoints matched with Lowe's ratio test and a RANSAC
   homography find the asset even scaled, rotated or slightly in perspective.
2. Is it the real thing? The scene is warped back into the asset's frame and
   compared cell by cell on a grid: structural similarity (SSIM) for shape and
   detail, Lab colour distance for colour. AI redraws tend to keep the overall
   look and get small things wrong (an eye, a stripe, a shade), which shows up
   as a few bad cells rather than a low global score.
3. Is anything attached to it? When the asset is registered as only a part
   (a mascot's face), the foreground shape containing the match is measured.
   If it extends well past the matched box, something (usually a body) has
   been joined on. This is a geometric signal; the vision model confirms it.

Flat artwork (a plain circle, a two-colour icon) has too few SIFT keypoints
to match. For those, step 1 falls back to multi-scale template matching on
the artwork mask, which finds unrotated copies at any size; steps 2 and 3
are the same.

Thresholds were set on synthetic tests (resized, recompressed and recoloured
copies); calibrate them per brand from reviewer decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from verytas.media.files import shrink

GRID = 6
MIN_INLIERS = 10
MIN_INLIER_RATIO = 0.25
CELL_SSIM_FLOOR = 0.45  # below this a cell's structure has changed
# Colour is scored by the 90th percentile of a lightly blurred Lab distance,
# so a small strongly recoloured feature (an eye) counts while edge
# misalignment, which is thin and scattered, does not.
CELL_DELTA_E_CEIL = 22.0
MIN_CELL_COVERAGE = 0.2  # ignore cells that are mostly transparent background
# Foreground connected to the match that lies outside the matched box, as a
# share of what lies inside it. An exact copy sits near 0; a joined-on body
# is usually above 0.5.
ATTACHED_RATIO = 0.35
_ASSET_MIN_SIDE = 256
_ASSET_MAX_SIDE = 1200
MAX_ASPECT = 8.0  # wider than a long wordmark is not artwork we can match
MIN_REGISTER_SIDE = 64
# Exact copies score about 0.99; similar marks and recoloured copies 0.76 to
# 0.82 on synthetic tests, so those are left to the vision model's imitation check.
TEMPLATE_SCORE = 0.85
MIN_JUDGE_SIDE = 100  # matched copies smaller than this are located, not judged
_TEMPLATE_SCENE_SIDE = 900


@dataclass
class PreparedAsset:
    asset_id: int
    rgb: np.ndarray
    gray: np.ndarray
    mask: np.ndarray  # True where the asset has artwork (not background)
    keypoints: tuple
    descriptors: np.ndarray | None


@dataclass
class AssetMatch:
    asset_id: int
    found: bool
    inliers: int = 0
    box: tuple[int, int, int, int] | None = None  # in the scene image's pixels
    similarity: float | None = None  # mean SSIM over artwork cells
    colour_delta: float | None = None  # mean Lab distance over artwork
    altered_cells: list[dict] = field(default_factory=list)
    attached_ratio: float | None = None  # foreground around the match / match box

    @property
    def altered(self) -> bool:
        return bool(self.altered_cells)


def _sift():
    return cv2.SIFT_create(nfeatures=3000)


def _artwork_mask(rgba: Image.Image) -> np.ndarray:
    if rgba.mode == "RGBA" and np.asarray(rgba.split()[3]).min() < 250:
        return np.asarray(rgba.split()[3]) > 16
    rgb = np.asarray(rgba.convert("RGB")).astype(np.int16)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    return np.abs(rgb - bg).sum(axis=2) > 30


def check_registrable(img: Image.Image) -> str | None:
    """Why an image can't be an official asset, or None."""
    if min(img.size) < MIN_REGISTER_SIDE:
        return f"artwork must be at least {MIN_REGISTER_SIDE} px on each side"
    if max(img.size) / min(img.size) > MAX_ASPECT:
        return f"artwork is more than {MAX_ASPECT:.0f} times wider than it is tall (or the reverse)"
    return None


def prepare(asset_id: int, img: Image.Image) -> PreparedAsset:
    """Keypoints and artwork mask for one official asset. Cache it: this is the slow part."""
    why = check_registrable(img)
    if why:
        raise ValueError(why)
    img = shrink(img, _ASSET_MAX_SIDE)
    if min(img.size) < _ASSET_MIN_SIDE:
        # Upscale small artwork for SIFT, but never past the max side: the
        # aspect cap above keeps this bounded.
        scale = min(_ASSET_MIN_SIDE / min(img.size), _ASSET_MAX_SIDE / max(img.size))
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    mask = _artwork_mask(img.convert("RGBA") if img.mode != "RGBA" else img)
    rgb = np.asarray(_on_white(img))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    kp, des = _sift().detectAndCompute(gray, mask.astype(np.uint8) * 255)
    return PreparedAsset(asset_id, rgb, gray, mask, tuple(kp), des)


def _on_white(img: Image.Image) -> Image.Image:
    if img.mode == "RGBA":
        base = Image.new("RGB", img.size, "white")
        base.paste(img, mask=img.split()[3])
        return base
    return img.convert("RGB")


@dataclass
class SceneFeatures:
    rgb: np.ndarray
    gray: np.ndarray
    keypoints: tuple
    descriptors: np.ndarray | None


def scene_features(scene_img: Image.Image) -> SceneFeatures:
    """Compute once per image and share across every asset. Blocking."""
    rgb = np.asarray(shrink(scene_img).convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    kp, des = _sift().detectAndCompute(gray, None)
    return SceneFeatures(rgb, gray, tuple(kp), des)


def flat(asset: PreparedAsset) -> bool:
    """Too few keypoints for SIFT; matched by template instead."""
    return asset.descriptors is None or len(asset.keypoints) < MIN_INLIERS * 3


def match(asset: PreparedAsset, scene_img: Image.Image | SceneFeatures) -> AssetMatch:
    """Blocking; call through asyncio.to_thread."""
    feats = scene_img if isinstance(scene_img, SceneFeatures) else scene_features(scene_img)
    miss = AssetMatch(asset.asset_id, False)
    if asset.descriptors is not None and len(asset.keypoints) >= MIN_INLIERS and feats.descriptors is not None \
            and len(feats.keypoints) >= MIN_INLIERS:
        found = _sift_match(asset, feats.keypoints, feats.descriptors)
        if not isinstance(found, AssetMatch):
            return _from_homography(asset, feats.rgb, *found)
        miss = found
    if flat(asset):
        placed = _template_match(asset, feats.gray)
        if placed is not None:
            return _from_homography(asset, feats.rgb, _refine(asset, feats.gray, placed[0]), 0)
    return miss


def _sift_match(asset: PreparedAsset, kp, des) -> tuple[np.ndarray, int] | AssetMatch:
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(asset.descriptors, des, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < MIN_INLIERS:
        return AssetMatch(asset.asset_id, False, inliers=len(good))
    src = np.float32([asset.keypoints[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None:
        return AssetMatch(asset.asset_id, False, inliers=0)
    inliers = int(inlier_mask.sum())
    if inliers < MIN_INLIERS or inliers / len(good) < MIN_INLIER_RATIO or not _plausible(H):
        return AssetMatch(asset.asset_id, False, inliers=inliers)
    return H, inliers


def _template_match(asset: PreparedAsset, scene_gray: np.ndarray) -> tuple[np.ndarray, int] | None:
    """Best unrotated placement of flat artwork at any scale, as a homography, or None.

    Matched on the artwork mask so the asset's own background doesn't have
    to match the scene's.
    """
    k = min(1.0, _TEMPLATE_SCENE_SIDE / max(scene_gray.shape))
    small = cv2.resize(scene_gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else scene_gray
    sh, sw = small.shape
    ah, aw = asset.gray.shape
    mask = asset.mask.astype(np.uint8) * 255
    best = (0.0, None, None)
    for frac in np.geomspace(0.06, 0.95, 18):
        s = frac * min(sw / aw, sh / ah)
        tw, th = int(aw * s), int(ah * s)
        if tw < 16 or th < 16 or tw > sw or th > sh:
            continue
        tpl = cv2.resize(asset.gray, (tw, th), interpolation=cv2.INTER_AREA)
        m = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_NEAREST)
        if m.mean() < 8:
            continue
        res = _valid(cv2.matchTemplate(small, tpl, cv2.TM_CCOEFF_NORMED, mask=m))
        _, score, _, at = cv2.minMaxLoc(res)
        if score > best[0]:
            best = (score, s, at)
    score, s, at = best
    if score < TEMPLATE_SCORE or s is None:
        return None
    # The coarse pass is a few pixels and a few percent of scale out, enough
    # for the cell comparison to call an exact copy altered. Refine at full
    # resolution in a window around the hit.
    fs, (fx, fy) = s / k, (at[0] / k, at[1] / k)
    pad = 0.12 * max(ah, aw) * fs
    x0, y0 = max(0, int(fx - pad)), max(0, int(fy - pad))
    x1 = min(scene_gray.shape[1], int(fx + aw * fs * 1.1 + pad))
    y1 = min(scene_gray.shape[0], int(fy + ah * fs * 1.1 + pad))
    roi = scene_gray[y0:y1, x0:x1]
    fine = (score, fs, (fx, fy))
    for t in fs * np.linspace(0.9, 1.1, 21):
        tw, th = int(round(aw * t)), int(round(ah * t))
        if tw < 16 or th < 16 or tw > roi.shape[1] or th > roi.shape[0]:
            continue
        tpl = cv2.resize(asset.gray, (tw, th), interpolation=cv2.INTER_AREA)
        m = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_NEAREST)
        res = _valid(cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED, mask=m))
        _, sc, _, loc = cv2.minMaxLoc(res)
        if sc > fine[0]:
            fine = (sc, tw / aw, (x0 + loc[0], y0 + loc[1]))
    _, fs, (fx, fy) = fine
    return np.array([[fs, 0, fx], [0, fs, fy], [0, 0, 1]], dtype=np.float64), 0


def _refine(asset: PreparedAsset, scene_gray: np.ndarray, H: np.ndarray) -> np.ndarray:
    """Sub-pixel alignment of a template placement (ECC, affine), or the placement unchanged.

    Template search moves in whole pixels and scale steps; at small sizes one
    pixel across a high-contrast edge reads as a colour change. SIFT
    placements don't need this: RANSAC over many keypoints is already sub-pixel.
    """
    warp = H[:2].astype(np.float32)
    try:
        _, warp = cv2.findTransformECC(asset.gray.astype(np.float32), scene_gray.astype(np.float32), warp,
                                       cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), None, 5)
    except cv2.error:
        return H
    refined = np.vstack([warp, [0, 0, 1]]).astype(np.float64)
    # Accept only a small correction; a large jump means ECC wandered off.
    if np.abs(refined[:2, 2] - H[:2, 2]).max() > 0.05 * max(asset.gray.shape) * H[0, 0] or not _plausible(refined):
        return H
    return refined


def _valid(res: np.ndarray) -> np.ndarray:
    """Masked correlation divides by almost nothing over flat patches; those scores are noise, not matches."""
    res[~np.isfinite(res) | (res > 1.0)] = 0.0
    return res


def _from_homography(asset: PreparedAsset, scene: np.ndarray, H: np.ndarray, inliers: int) -> AssetMatch:
    h, w = asset.gray.shape
    corners = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2), H)
    xs, ys = corners[:, 0, 0], corners[:, 0, 1]
    box = (max(0, int(xs.min())), max(0, int(ys.min())), min(scene.shape[1], int(xs.max())),
           min(scene.shape[0], int(ys.max())))

    aligned = cv2.warpPerspective(scene, np.linalg.inv(H), (w, h), flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REPLICATE)
    cells, sims, deltas = _compare(asset, aligned, _as_seen(asset.rgb, box))
    if min(box[2] - box[0], box[3] - box[1]) < MIN_JUDGE_SIDE:
        cells = []  # too few pixels left to tell a change from resampling; the vision model judges
    attached = _attached_ratio(scene, box)
    return AssetMatch(
        asset.asset_id, True, inliers, box,
        similarity=round(float(np.mean(sims)), 3) if sims else None,
        colour_delta=round(float(np.mean(deltas)), 2) if deltas else None,
        altered_cells=cells, attached_ratio=attached,
    )


def _plausible(H: np.ndarray) -> bool:
    """Reject degenerate fits: mirrored, collapsed or wildly sheared."""
    det = float(np.linalg.det(H[:2, :2]))
    return 0.005 < det < 200 and abs(H[2, 0]) < 0.005 and abs(H[2, 1]) < 0.005


def _lab(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    return lab


def _ssim_map(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Wang et al. (2004) SSIM with a Gaussian window, on 8-bit grey."""
    a, b = a.astype(np.float32), b.astype(np.float32)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    blur = lambda x: cv2.GaussianBlur(x, (11, 11), 1.5)  # noqa: E731
    mu_a, mu_b = blur(a), blur(b)
    var_a = blur(a * a) - mu_a**2
    var_b = blur(b * b) - mu_b**2
    cov = blur(a * b) - mu_a * mu_b
    return ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a**2 + mu_b**2 + c1) * (var_a + var_b + c2))


def _as_seen(rgb: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """The official artwork as it would look after being shrunk to the matched size and warped back.

    A small copy loses fine edges to resampling; comparing it with the crisp
    original reads that blur as a change. Below full size, both sides go
    through the same resampling.
    """
    h, w = rgb.shape[:2]
    bw, bh = max(1, box[2] - box[0]), max(1, box[3] - box[1])
    if bw >= 0.8 * w and bh >= 0.8 * h:
        return rgb
    small = cv2.resize(rgb, (bw, bh), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _compare(asset: PreparedAsset, aligned: np.ndarray,
             reference: np.ndarray | None = None) -> tuple[list[dict], list[float], list[float]]:
    ref = asset.rgb if reference is None else reference
    ssim = _ssim_map(cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY), cv2.cvtColor(aligned, cv2.COLOR_RGB2GRAY))
    delta = cv2.GaussianBlur(np.linalg.norm(_lab(ref) - _lab(aligned), axis=2), (7, 7), 2.0)
    h, w = asset.gray.shape
    # Score only the artwork's interior. Anti-aliased outlines blend with
    # whatever background the scene has, which is not a change to the asset.
    interior = cv2.erode(asset.mask.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    cells, sims, deltas = [], [], []
    for r in range(GRID):
        for c in range(GRID):
            ys, xs = slice(r * h // GRID, (r + 1) * h // GRID), slice(c * w // GRID, (c + 1) * w // GRID)
            m = interior[ys, xs]
            if m.mean() < MIN_CELL_COVERAGE:
                continue
            s = float(ssim[ys, xs][m].mean())
            d = float(np.percentile(delta[ys, xs][m], 90))
            sims.append(s)
            deltas.append(d)
            if s < CELL_SSIM_FLOOR or d > CELL_DELTA_E_CEIL:
                cells.append({"row": r, "col": c, "ssim": round(s, 3), "delta_e": round(d, 1),
                              "change": "shape" if s < CELL_SSIM_FLOOR else "colour"})
    return cells, sims, deltas


def _attached_ratio(scene: np.ndarray, box: tuple[int, int, int, int]) -> float | None:
    """Foreground joined to the match outside its box, over the part inside it.

    Works on flat or simple backgrounds (stickers, posts, ads), where the
    background is the border's dominant colour. On busy photos there is no
    reliable foreground, so the ratio is None and the vision model decides.
    """
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return None
    lab = _lab(scene)
    border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    bg = np.median(border, axis=0)
    if np.median(np.linalg.norm(border - bg, axis=1)) > 12:
        return None
    fg = (np.linalg.norm(lab - bg, axis=2) > 18).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    _, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    inside_labels = labels[y0:y1, x0:x1]
    ids, counts = np.unique(inside_labels[inside_labels > 0], return_counts=True)
    if not len(ids):
        return None
    main = ids[np.argmax(counts)]
    total = float(stats[main, cv2.CC_STAT_AREA])
    if total > 0.9 * fg.size:
        return None
    inside = float((inside_labels == main).sum())
    return round((total - inside) / max(1.0, inside), 2)
