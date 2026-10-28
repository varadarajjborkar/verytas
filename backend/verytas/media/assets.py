"""Brand-asset matching: is the official artwork here, unchanged, and only the approved part?

Three questions per official asset, answered from pixels alone:

1. Where is it? SIFT keypoints matched with Lowe's ratio test and a RANSAC
   homography find the asset even scaled, rotated or slightly in perspective.
2. Is it the real thing? The scene is warped back into the asset's frame and
   compared cell by cell on a grid: structural similarity (SSIM) for shape and
   detail, Lab colour distance for colour. AI redraws tend to keep the overall
   look and get small things wrong (an eye, a stripe, a shade), which shows up
   as a few bad cells rather than a low global score.
3. Is it drawn in proportion? Warping the scene back into the asset's frame
   undoes any stretch, so a squashed logo would compare as a perfect copy.
   The homography's local shape at the asset's centre says how it was placed:
   rotation and uniform scale are a layout choice, unequal scale (stretched,
   squashed), shear (skewed) and a flip (mirrored) are distortions brand books
   forbid. A mirrored copy doesn't match at all (SIFT is not mirror
   invariant), so a flipped copy of the artwork is matched as well.
4. Is anything attached to it? When the asset is registered as only a part
   (a mascot's face), the foreground shape containing the match is measured.
   If it extends well past the matched box, something (usually a body) has
   been joined on. This is a geometric signal; the vision model confirms it.

Flat artwork (a plain circle, a two-colour icon) has too few SIFT keypoints
to match. For those, step 1 falls back to multi-scale template matching on
the artwork mask, which finds unrotated copies at any size; steps 2 and 3
are the same.

Compact flat artwork (an app icon) has a second fallback, for when none of that finds it: a hue swap
reverses the light and dark of its regions, which destroys the grey pattern both steps rely on. It is
then located by outline (media/shape.py) and verified by palette, and step 2 judges its colours.

Thresholds were set on synthetic tests (resized, recompressed and recoloured
copies); calibrate them per brand from reviewer decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from verytas.media import shape
from verytas.media.files import shrink

GRID = 6
MIN_INLIERS = 10
MIN_INLIER_RATIO = 0.25
# A match found only on the flipped artwork is called mirrored only above these (see _mirror_sure).
MIRROR_MIN_INLIERS = 15
MIRROR_MIN_SIMILARITY = 0.85
MIRROR_CLEAR_GAIN = 0.15
CELL_SSIM_FLOOR = 0.45  # below this a cell's structure has changed
# Colour is scored by the 90th percentile of a lightly blurred Lab distance,
# so a small strongly recoloured feature (an eye) counts while edge
# misalignment, which is thin and scattered, does not.
CELL_DELTA_E_CEIL = 22.0
MIN_CELL_COVERAGE = 0.2  # ignore cells that are mostly transparent background
# The image's damage, given to the official artwork before comparing (see _compare).
JPEG_QUALITIES = (95, 85, 75, 60, 40)
REGISTER_SLACK = 1  # pixels of misregistration forgiven
EDGE_STRENGTH = 60  # Sobel response of an edge whose anti-aliased rim is not compared for colour
EDGE_RIM = 2  # pixels either side of such an edge
OUT_OF_FRAME = 0.5  # a cell with under this share of its pixels inside the image is outside it
# How far past the limits a flagged cell with no flagged neighbour must be to count.
LONE_CELL_SSIM = 0.15
LONE_CELL_DELTA = 1.5
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
# Width-to-height scale ratios tried for flat artwork, which template matching otherwise finds only in
# proportion: a stretched two-colour logo would be missed rather than reported. 1.0 first, so an
# undistorted copy is never beaten by a near tie at another aspect.
_TEMPLATE_ASPECTS = (1.0, 0.8, 1.25, 0.67, 1.5)
ASPECT_MARGIN = 0.03  # correlation another aspect must add over in proportion to be believed
# Unequal scale beyond this (8%) is a stretch, not resampling or the fit's own error, which stays under
# 3% on resized, rotated and recompressed copies; shear beyond this many degrees is a skew.
STRETCH_TOLERANCE = 0.08
SHEAR_TOLERANCE_DEG = 6.0
# Corner-to-corner variation in the fit's area scale above which the artwork was photographed at an
# angle, and its proportions are not judged (a 12% keystone already reads as a 10% stretch).
PERSPECTIVE_LIMIT = 0.12
ECC_PAD = 0.3  # window around the placement, as a share of the artwork's longer side
ECC_BELOW_INLIERS = 40  # keypoint fits with fewer inliers than this are aligned by ECC as well
ECC_ITERATIONS = 80
ECC_MIN_LEVEL_SIDE = 40  # pyramid levels whose artwork would be thinner than this are skipped
ECC_MIN_NCC = 0.6  # the aligned artwork must correlate at least this well with the scene
ECC_MIN_GAIN = 0.01  # and better than the placement it started from
MAX_ANISOTROPY = 3.0  # longest over shortest axis scale of a believable placement
AFFINE_PREFERRED = 0.85  # an affine fit with this share of the homography's inliers is the one believed


@dataclass
class PreparedAsset:
    asset_id: int
    rgb: np.ndarray
    gray: np.ndarray
    mask: np.ndarray  # True where the asset has artwork (not background)
    keypoints: tuple
    descriptors: np.ndarray | None
    channels: np.ndarray | None = None  # which colour channel (see _channels) each keypoint came from
    # The artwork flipped left to right, matched only when the artwork itself isn't found, so symmetric
    # artwork (which the unflipped match finds first) is never called mirrored.
    mirror: PreparedAsset | None = None
    # Present for compact flat artwork (an app icon): what the shape-first fallback needs (see shape.py).
    outline: shape.ShapeModel | None = None


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
    # Where in the scene the evidence lies: the box around the keypoints that agree with the fit (the
    # whole match for a template placement). A match whose evidence lies inside another artwork's match
    # is that artwork being seen, not this one (see prism.agents._explained).
    core: tuple[int, int, int, int] | None = None
    # How the artwork was placed, read from the fit at its centre. stretch is its width scale over its
    # height scale (1.0 in proportion, 1.3 stretched wide, 0.75 squashed); shear and rotation in degrees.
    stretch: float | None = None
    shear_deg: float | None = None
    rotation_deg: float | None = None
    mirrored: bool = False
    # Found by outline alone, because the grey keypoints did not match: the artwork is there in other
    # colours (or a plain copy the keypoints missed). palette_swap lists (official, found) hex colours for
    # each region that changed.
    by_shape: bool = False
    palette_swap: list[tuple[str, str]] = field(default_factory=list)

    @property
    def altered(self) -> bool:
        return bool(self.altered_cells)

    @property
    def distortions(self) -> list[str]:
        """What is wrong with how the artwork was placed, in words, worst first."""
        out = []
        if self.mirrored:
            out.append("mirrored (flipped left to right)")
        # Which axis was changed can't be told from the image, only that the two disagree.
        if self.stretch is not None and abs(self.stretch - 1) > STRETCH_TOLERANCE:
            out.append(f"out of proportion: {self.stretch - 1:.0%} too wide for its height" if self.stretch > 1
                       else f"out of proportion: {1 / self.stretch - 1:.0%} too tall for its width")
        if self.shear_deg is not None and abs(self.shear_deg) > SHEAR_TOLERANCE_DEG:
            out.append(f"skewed by {abs(self.shear_deg):.0f} degrees")
        return out


def _sift():
    return cv2.SIFT_create(nfeatures=3000)


def _channels(rgb: np.ndarray) -> list[np.ndarray]:
    """Lightness, red-green and blue-yellow. SIFT sees one channel; on lightness alone a red logo on a
    green photo all but disappears (both mid-grey), while a chroma channel shows it in full. Chroma spans
    about half the 8-bit range, so it is stretched to give SIFT comparable contrast."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    chroma = [np.clip((lab[..., i].astype(np.int16) - 128) * 2 + 128, 0, 255).astype(np.uint8) for i in (1, 2)]
    return [lab[..., 0], *chroma]


def _features(rgb: np.ndarray, mask: np.ndarray | None) -> tuple[tuple, np.ndarray | None, np.ndarray | None]:
    """Keypoints, descriptors and channel per keypoint, over every channel. Matching keeps each channel to
    its own: a lightness edge and a chroma edge are not the same feature."""
    kps: list = []
    des, chans = [], []
    m = None if mask is None else mask.astype(np.uint8) * 255
    for i, channel in enumerate(_channels(rgb)):
        kp, d = _sift().detectAndCompute(channel, m)
        if d is None or not kp:
            continue
        kps += kp
        des.append(d)
        chans.append(np.full(len(kp), i, np.int8))
    if not des:
        return (), None, None
    return tuple(kps), np.vstack(des), np.concatenate(chans)


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
    prepared = PreparedAsset(asset_id, rgb, gray, mask, *_features(rgb, mask), outline=shape.build(rgb, mask))
    f_mask = np.ascontiguousarray(mask[:, ::-1])
    f_rgb = np.ascontiguousarray(rgb[:, ::-1])
    f_gray = np.ascontiguousarray(gray[:, ::-1])
    prepared.mirror = PreparedAsset(asset_id, f_rgb, f_gray, f_mask, *_features(f_rgb, f_mask))
    return prepared


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
    channels: np.ndarray | None = None
    # Original pixels per working pixel: matching runs on a copy at most WORK_SIDE wide, and boxes are
    # reported back in the original's pixels, where OCR boxes and the layout already are.
    scale: float = 1.0
    # Edge-direction fields for the shape fallback, built on first use and shared by every asset.
    outline: shape.SceneShape | None = None


def scene_features(scene_img: Image.Image) -> SceneFeatures:
    """Compute once per image and share across every asset. Blocking."""
    work = shrink(scene_img)
    rgb = np.asarray(work.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return SceneFeatures(rgb, gray, *_features(rgb, None), scale=scene_img.width / work.width)


def flat(asset: PreparedAsset) -> bool:
    """Too few keypoints for SIFT; matched by template instead. Counted per channel, not summed: the
    chroma channels see the same few corners of a simple shape again, which adds no distinctiveness."""
    if asset.descriptors is None:
        return True
    if asset.channels is None:
        return len(asset.keypoints) < MIN_INLIERS * 3
    return int(np.bincount(asset.channels.astype(np.int64)).max()) < MIN_INLIERS * 3


def match(asset: PreparedAsset, scene_img: Image.Image | SceneFeatures) -> AssetMatch:
    """Blocking; call through asyncio.to_thread. Boxes are in the scene image's own pixels."""
    feats = scene_img if isinstance(scene_img, SceneFeatures) else scene_features(scene_img)
    return _to_scene(_best(asset, feats), feats.scale)


def _to_scene(m: AssetMatch, scale: float) -> AssetMatch:
    if scale != 1.0:
        m.box = _scaled(m.box, scale)
        m.core = _scaled(m.core, scale)
    return m


def _scaled(box: tuple[int, int, int, int] | None, scale: float) -> tuple[int, int, int, int] | None:
    return None if box is None else tuple(round(v * scale) for v in box)  # type: ignore[return-value]


def _best(asset: PreparedAsset, feats: SceneFeatures) -> AssetMatch:
    found = _match(asset, feats)
    # Flat artwork is matched by template, a second full search per image for a rare mistake on simple
    # shapes; keypoint artwork is where a flip is cheap to try and where it matters (wordmarks, mascots).
    # A nearly symmetric character can match its own mirror image weakly (a few keypoints, many changed
    # cells), so a weak match is checked against the flip too, which wins only by fitting clearly better.
    weak = found.found and (found.inliers < 3 * MIN_INLIERS or (found.similarity or 0) < 0.9)
    if (not found.found or weak) and asset.mirror is not None and not flat(asset):
        flipped = _match(asset.mirror, feats)
        # A plain match with no comparable cells has no similarity to beat, so only inliers can decide.
        gain = (flipped.similarity or 0) - (found.similarity or 0) if found.similarity is not None else 0.0
        # Clearly better means more of the artwork fits (half again the inliers), or it looks much more alike.
        if flipped.found and _mirror_sure(flipped) and (not found.found or gain >= MIRROR_CLEAR_GAIN or (
                flipped.inliers >= 1.5 * found.inliers and gain > 0)):
            flipped.mirrored = True
            # Cells were compared in the flipped artwork's frame; name them as they sit in the official one.
            for cell in flipped.altered_cells:
                cell["col"] = GRID - 1 - cell["col"]
            return flipped
    return found if found.found or asset.outline is None else _by_shape(asset, feats, found)


def _by_shape(asset: PreparedAsset, feats: SceneFeatures, miss: AssetMatch) -> AssetMatch:
    """Fallback for compact flat artwork the keypoints did not find: look for its outline instead, then let
    the usual comparison judge the colours. A hue swap turns an icon's light regions dark and its dark regions
    light, which is exactly what keypoints on grey cannot survive and edge directions can."""
    if feats.outline is None:
        feats.outline = shape.SceneShape(feats.rgb)
    placed = shape.locate(asset.outline, asset.rgb, feats.outline)
    if placed is None:
        return miss
    x, y, w, h = placed.box
    ah, aw = asset.gray.shape
    H = np.array([[w / aw, 0, x], [0, h / ah, y], [0, 0, 1.0]])
    got = _from_homography(asset, feats.rgb, H, 0)
    got.by_shape, got.palette_swap = True, placed.swapped
    return got


def _mirror_sure(m: AssetMatch) -> bool:
    """A match found only by flipping must also look like the artwork once un-flipped. Symmetric shapes (a
    kite emblem, a rounded icon) and other artwork nearby supply enough keypoints for a weak flipped fit:
    on the demo posters every such false "mirrored" scored 0.83 or less or had under 15 inliers, while
    every real mirrored copy in the 1,200-scene benchmark scored 0.94 or more with 19 or more."""
    if m.similarity is None:  # too small to compare: only a fit with many inliers is believed
        return m.inliers >= 3 * MIN_INLIERS
    return m.inliers >= MIRROR_MIN_INLIERS and m.similarity >= MIRROR_MIN_SIMILARITY


def _match(asset: PreparedAsset, feats: SceneFeatures) -> AssetMatch:
    miss = AssetMatch(asset.asset_id, False)
    by_keypoints = None
    if asset.descriptors is not None and len(asset.keypoints) >= MIN_INLIERS and feats.descriptors is not None \
            and len(feats.keypoints) >= MIN_INLIERS:
        found = _sift_match(asset, feats)
        if not isinstance(found, AssetMatch):
            H, inliers, core = found
            if inliers < ECC_BELOW_INLIERS and _perspective(H, *asset.gray.shape[::-1]) < 0.02:
                # A few keypoints fix the position well and the proportions badly; the pixels settle it.
                refined = _fit_affine(asset, feats.gray, H)
                H = H if refined is None else refined
            by_keypoints = _from_homography(asset, feats.rgb, H, inliers, core)
            if not flat(asset):
                return by_keypoints
        else:
            miss = found
    if flat(asset):
        # Flat artwork can still give a keypoint fit, on a dozen points, and a fit that is a pixel or a
        # degree out turns every edge cell into a "colour change". Both are tried and the better fit is
        # kept: the template wins on copies in proportion, keypoints on rotated ones.
        placed = _template_match(asset, feats.gray)
        if placed is not None:
            by_template = _from_homography(
                asset, feats.rgb, _fit_affine_or_refine(asset, feats.gray, placed[0]), 0)
            if by_keypoints is None or (by_template.similarity or 0) >= (by_keypoints.similarity or 0):
                return by_template
    return by_keypoints or miss


def _sift_match(asset: PreparedAsset, feats: SceneFeatures) -> tuple[np.ndarray, int, tuple] | AssetMatch:
    # Lowe's ratio test within each channel, then one geometric fit over all of them: the artwork is one
    # object wherever its features were seen.
    src_pts, dst_pts = [], []
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    for c in np.unique(asset.channels):
        a_idx = np.flatnonzero(asset.channels == c)
        s_idx = np.flatnonzero(feats.channels == c)
        if len(a_idx) < 2 or len(s_idx) < 2:
            continue
        pairs = matcher.knnMatch(asset.descriptors[a_idx], feats.descriptors[s_idx], k=2)
        for m, n in (p for p in pairs if len(p) == 2):
            if m.distance < 0.75 * n.distance:
                src_pts.append(asset.keypoints[a_idx[m.queryIdx]].pt)
                dst_pts.append(feats.keypoints[s_idx[m.trainIdx]].pt)
    good = src_pts
    if len(good) < MIN_INLIERS:
        return AssetMatch(asset.asset_id, False, inliers=len(good))
    src = np.float32(src_pts).reshape(-1, 1, 2)
    dst = np.float32(dst_pts).reshape(-1, 1, 2)
    H, inlier_mask = _fit(src, dst)
    if H is None:
        return AssetMatch(asset.asset_id, False, inliers=0)
    inliers = int(inlier_mask.sum())
    if inliers < MIN_INLIERS or inliers / len(good) < MIN_INLIER_RATIO or not _plausible(H):
        return AssetMatch(asset.asset_id, False, inliers=inliers)
    agreed = dst.reshape(-1, 2)[inlier_mask.ravel().astype(bool)]
    core = (int(agreed[:, 0].min()), int(agreed[:, 1].min()), int(agreed[:, 0].max()) + 1, int(agreed[:, 1].max()) + 1)
    return H, inliers, core


def _fit(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None]:
    """RANSAC fit of matched keypoints, as a 3x3 matrix and its inlier mask.

    Artwork is placed flat far more often than photographed at an angle, so an affine fit (six numbers) is
    preferred whenever it explains nearly as many points as a homography (eight). A homography fitted to
    a dozen or two points has the freedom to bend itself around a stretched or skewed copy, reading the
    distortion as perspective, which the placement check then ignores; the affine cannot, and a copy
    really photographed at an angle still gains enough inliers from the projective terms to win.
    """
    H, hmask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    M, amask = cv2.estimateAffine2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=5.0)
    if M is None or amask is None:
        return H, hmask
    affine = np.vstack([M, [0, 0, 1]]).astype(np.float64)
    if H is None or hmask is None or not _plausible(H):
        return affine, amask
    kept, held = int(amask.sum()), int(hmask.sum())
    # The affine only takes over when it would pass the same gates the homography passes (a match is never
    # lost to it), and not when many points agree on a real tilt: a homography with that much support is a
    # photograph taken at an angle, whose keystone would otherwise read as a stretched copy.
    passes = kept >= max(4, MIN_INLIERS) and kept / len(src) >= MIN_INLIER_RATIO
    if passes and kept >= AFFINE_PREFERRED * held and not _tilted(src, dst, H, affine, hmask):
        return affine, amask
    return H, hmask


TILT_FIT_GAIN = 0.75  # the homography's mean error under this share of the affine's: the tilt is real


def _tilted(src: np.ndarray, dst: np.ndarray, H: np.ndarray, A: np.ndarray, mask: np.ndarray) -> bool:
    """Whether the points show a real camera tilt. Both fits can keep every point of a poster shot at an angle,
    but only the homography follows its narrowing: its error on those points is clearly smaller. On a flat but
    stretched copy the two fit alike, and the affine (which cannot bend around the stretch) is the one to keep."""
    keep = mask.ravel().astype(bool)
    if keep.sum() < 3 * MIN_INLIERS:
        return False  # too few points for the comparison to mean anything; a dozen can fit either way
    s, d = src[keep], dst[keep].reshape(-1, 2)
    err_h = float(np.linalg.norm(cv2.perspectiveTransform(s, H).reshape(-1, 2) - d, axis=1).mean())
    err_a = float(np.linalg.norm(cv2.transform(s, A[:2]).reshape(-1, 2) - d, axis=1).mean())
    return err_a > 0.5 and err_h < TILT_FIT_GAIN * err_a


def _template_match(asset: PreparedAsset, scene_gray: np.ndarray) -> tuple[np.ndarray, int] | None:
    """Best unrotated placement of flat artwork at any scale and aspect, as an affine homography, or None.

    Matched on the artwork mask so the asset's own background doesn't have
    to match the scene's.
    """
    k = min(1.0, _TEMPLATE_SCENE_SIDE / max(scene_gray.shape))
    small = cv2.resize(scene_gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else scene_gray
    ah, aw = asset.gray.shape
    mask = asset.mask.astype(np.uint8) * 255

    def search(img: np.ndarray, origin: tuple[int, int], aspects, scales) -> tuple[float, float, float, tuple]:
        """(score, scale, aspect, top-left in img's frame plus origin) of the best placement."""
        top = (0.0, 0.0, 1.0, (0, 0))
        for aspect in aspects:
            for sc in scales:
                tw, th = int(round(aw * sc * aspect)), int(round(ah * sc))
                if tw < 16 or th < 16 or tw > img.shape[1] or th > img.shape[0]:
                    continue
                tpl = cv2.resize(asset.gray, (tw, th), interpolation=cv2.INTER_AREA)
                m = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_NEAREST)
                if m.mean() < 8:
                    continue
                res = _valid(cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED, mask=m))
                _, score, _, at = cv2.minMaxLoc(res)
                if score > top[0]:
                    top = (score, sc, aspect, (origin[0] + at[0], origin[1] + at[1]))
        return top

    def window(img: np.ndarray, at: tuple, sc: float, aspect: float, grow: float) -> tuple[np.ndarray, tuple]:
        pad = grow * max(ah, aw * aspect) * sc
        x0, y0 = max(0, int(at[0] - pad)), max(0, int(at[1] - pad))
        x1 = min(img.shape[1], int(at[0] + aw * aspect * sc + pad))
        y1 = min(img.shape[0], int(at[1] + ah * sc + pad))
        return img[y0:y1, x0:x1], (x0, y0)

    # Size and place first, in proportion, over the whole image. A stretched copy still correlates best
    # where it is, so the other aspects are tried only in a window around that hit: a stretched logo is
    # measured for little more than the cost of finding it. A near-exact copy in proportion ends there.
    score, sc, aspect, at = search(small, (0, 0), (1.0,), np.geomspace(0.06, 0.95, 18) * min(
        small.shape[1] / aw, small.shape[0] / ah))
    if sc and score < 0.95:
        # In proportion is searched again on the same fine grid, so another aspect can't win only because
        # its grid happened to land nearer the true scale; and it has to win clearly, since a wrong aspect
        # at a compensating scale scores within noise of the right one on recompressed copies.
        roi, origin = window(small, at, sc, 1.0, 0.4)
        scales = sc * np.geomspace(0.7, 1.4, 9)
        level = search(roi, origin, (1.0,), scales)
        other = search(roi, origin, _TEMPLATE_ASPECTS[1:], scales)
        score, sc, aspect, at = other if other[0] > max(level[0], score) + ASPECT_MARGIN else max(
            level, (score, sc, aspect, at), key=lambda r: r[0])
    if score < TEMPLATE_SCORE or not sc:
        return None
    # The coarse pass is a few pixels and a few percent of scale and aspect out, enough for the cell
    # comparison to call an exact copy altered. Refine at full resolution in a window around the hit.
    fs, full_at = sc / k, (at[0] / k, at[1] / k)
    roi, origin = window(scene_gray, full_at, fs, aspect, 0.12)
    aspects = (aspect,) if aspect == 1.0 else aspect * np.array([0.92, 0.96, 1.0, 1.04, 1.08])
    fine = search(roi, origin, aspects, fs * np.linspace(0.9, 1.1, 21))
    if fine[0] > score:
        _, fs, aspect, full_at = fine
    fx, fy = full_at
    return np.array([[fs * aspect, 0, fx], [0, fs, fy], [0, 0, 1]], dtype=np.float64), 0


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


def _masked_ncc(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    """Zero-mean normalised correlation of two grey images over the mask."""
    m = mask > 0
    if m.sum() < 50:
        return -1.0
    x, y = a[m].astype(np.float64), b[m].astype(np.float64)
    x -= x.mean()
    y -= y.mean()
    d = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / d) if d > 1e-6 else -1.0


def _fit_affine(asset: PreparedAsset, scene_gray: np.ndarray, H: np.ndarray) -> np.ndarray | None:
    """Affine alignment of the artwork inside a padded window around its placement, or None.

    ECC (enhanced correlation coefficient) maximises the correlation between the artwork and the scene
    under a full affine warp, so scale along each axis and shear are free, which template matching (a
    scale and an aspect from a short list) and a handful of keypoints cannot measure. It runs coarse to
    fine because the correlation is only smooth near the answer, and only over the artwork's own pixels
    (the scene behind a logo is anything). The start is the placement already found; the result is kept
    only if it correlates clearly better than the start and has not wandered to an implausible shape.
    """
    A, t = H[:2, :2], H[:2, 2]
    scale = float(np.sqrt(abs(np.linalg.det(A))))
    ah, aw = asset.gray.shape
    if scale < 0.03 or not np.isfinite(scale):
        return None
    tw, th = max(16, round(aw * scale)), max(16, round(ah * scale))
    if min(tw, th) > 700:
        return None
    tpl = cv2.resize(asset.gray, (tw, th), interpolation=cv2.INTER_AREA)
    tmask = (cv2.resize(asset.mask.astype(np.uint8) * 255, (tw, th), interpolation=cv2.INTER_AREA) > 127
             ).astype(np.uint8) * 255
    if tmask.mean() < 8:
        return None
    to_tpl = np.diag([tw / aw, th / ah])  # asset pixels to template pixels
    lin = A @ np.linalg.inv(to_tpl)  # template pixels to scene pixels
    corners = (lin @ np.array([[0, tw, tw, 0], [0, 0, th, th]], dtype=np.float64)).T + t
    pad = ECC_PAD * max(tw, th)
    x0, y0 = max(0, int(corners[:, 0].min() - pad)), max(0, int(corners[:, 1].min() - pad))
    x1, y1 = min(scene_gray.shape[1], int(corners[:, 0].max() + pad)), min(scene_gray.shape[0],
                                                                         int(corners[:, 1].max() + pad))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    roi = scene_gray[y0:y1, x0:x1].astype(np.float32)
    start = np.hstack([lin, (t - [x0, y0]).reshape(2, 1)]).astype(np.float32)

    def score(w: np.ndarray) -> float:
        seen = cv2.warpAffine(roi, w, (tw, th), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
        return _masked_ncc(tpl, seen, tmask)

    before = score(start)
    warp = start.copy()
    for f in (0.25, 0.5, 1.0):
        if f < 1.0 and min(tw, th) * f < ECC_MIN_LEVEL_SIDE:
            continue
        sz = (max(8, round(tw * f)), max(8, round(th * f)))
        t_f = cv2.resize(tpl, sz, interpolation=cv2.INTER_AREA).astype(np.float32)
        r_f = cv2.resize(roi, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1.0 else roi
        # The window's mask in the scene's frame; ECC reads it as which scene pixels are valid.
        w_f = warp.copy()
        w_f[:, 2] *= f
        valid = cv2.warpAffine(cv2.resize(tmask, sz, interpolation=cv2.INTER_NEAREST), w_f, r_f.shape[::-1],
                               flags=cv2.INTER_NEAREST)
        try:
            _, w_f = cv2.findTransformECC(t_f, r_f, w_f, cv2.MOTION_AFFINE,
                                          (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, ECC_ITERATIONS, 1e-4),
                                          valid, 5)
        except cv2.error:
            # Not converging is common from a poor start at a coarse level; a finer one may still settle, and a
            # finest level that fails keeps what the coarser ones found (the score below still has to agree).
            continue
        warp = w_f.copy()
        warp[:, 2] /= f
    # The artwork's centre may move a little, never out of the window it was looked for in: past that the fit
    # has locked onto something else nearby.
    centre = np.array([tw / 2, th / 2, 1.0])
    if np.linalg.norm(warp @ centre - start @ centre) > pad:
        return None
    after = score(warp)
    if after < ECC_MIN_NCC or after < before + ECC_MIN_GAIN:
        return None
    out = np.vstack([np.hstack([warp[:, :2] @ to_tpl, (warp[:, 2] + [x0, y0]).reshape(2, 1)]), [0, 0, 1]])
    return out.astype(np.float64) if _plausible(out) else None


def _fit_affine_or_refine(asset: PreparedAsset, scene_gray: np.ndarray, H: np.ndarray) -> np.ndarray:
    fitted = _fit_affine(asset, scene_gray, H)
    return _refine(asset, scene_gray, H) if fitted is None else fitted


def _valid(res: np.ndarray) -> np.ndarray:
    """Masked correlation divides by almost nothing over flat patches; those scores are noise, not matches."""
    res[~np.isfinite(res) | (res > 1.0)] = 0.0
    return res


def _from_homography(asset: PreparedAsset, scene: np.ndarray, H: np.ndarray, inliers: int,
                     core: tuple[int, int, int, int] | None = None) -> AssetMatch:
    h, w = asset.gray.shape
    corners = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2), H)
    xs, ys = corners[:, 0, 0], corners[:, 0, 1]
    box = (max(0, int(xs.min())), max(0, int(ys.min())), min(scene.shape[1], int(xs.max())),
           min(scene.shape[0], int(ys.max())))

    cells, sims, deltas = _connected(*_compare(asset, scene, H, box))
    if min(box[2] - box[0], box[3] - box[1]) < MIN_JUDGE_SIDE:
        cells = []  # too few pixels left to tell a change from resampling; the vision model judges
    attached = _attached_ratio(scene, box)
    stretch, shear, rotation = _placement(H, w, h)
    if _perspective(H, w, h) > PERSPECTIVE_LIMIT:
        # Photographed at an angle (a poster on a wall, a pack on a shelf): the local shape then mixes the
        # camera's tilt into the artwork's proportions, and the two can't be told apart from one fit.
        stretch, shear = None, None
    return AssetMatch(
        asset.asset_id, True, inliers, box,
        similarity=round(float(np.mean(sims)), 3) if sims else None,
        colour_delta=round(float(np.mean(deltas)), 2) if deltas else None,
        altered_cells=cells, attached_ratio=attached,
        stretch=None if stretch is None else round(stretch, 3), shear_deg=None if shear is None else round(shear, 1),
        rotation_deg=round(rotation, 1), core=core or box,
    )


def _perspective(H: np.ndarray, w: int, h: int) -> float:
    """How much the fit's scale varies across the artwork: the largest over the smallest local area scale
    at its corners, minus one. A flat placement (any affine fit) is 0; a keystone tilt is not."""
    def area_scale(x: float, y: float) -> float:
        d = H[2, 0] * x + H[2, 1] * y + H[2, 2]
        return abs(float(np.linalg.det(H))) / abs(d) ** 3 if d else float("inf")

    scales = [area_scale(x, y) for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
    return max(scales) / max(min(scales), 1e-9) - 1


def _placement(H: np.ndarray, w: int, h: int) -> tuple[float, float, float]:
    """(stretch, shear in degrees, rotation in degrees) of the fit at the artwork's centre.

    The local linear map J = R(rotation) @ [[sx, k], [0, sy]]: rotating J back leaves an upper triangular
    matrix whose diagonal is the scale along each of the artwork's own axes and whose corner is the shear.
    Taken at the centre so mild perspective, which varies the scale across the artwork, averages out.
    """
    def at(x: float, y: float) -> np.ndarray:
        p = H @ np.array([x, y, 1.0])
        return p[:2] / p[2]

    c = at(w / 2, h / 2)
    jx, jy = at(w / 2 + 1, h / 2) - c, at(w / 2, h / 2 + 1) - c
    theta = float(np.arctan2(jx[1], jx[0]))
    cos, sin = np.cos(-theta), np.sin(-theta)
    rot = np.array([[cos, -sin], [sin, cos]])
    (sx, k), (_, sy) = rot @ np.column_stack([jx, jy])
    if sy <= 0 or sx <= 0:
        return 1.0, 0.0, float(np.degrees(theta))
    return float(sx / sy), float(np.degrees(np.arctan2(k, sy))), float(np.degrees(theta))


def _plausible(H: np.ndarray) -> bool:
    """Reject degenerate fits: mirrored, collapsed, wildly sheared or stretched past any real layout."""
    det = float(np.linalg.det(H[:2, :2]))
    if not (0.005 < det < 200 and abs(H[2, 0]) < 0.005 and abs(H[2, 1]) < 0.005):
        return False
    # A dozen keypoints can be fitted by a very anisotropic affine map (3x to 40x) that no designer would
    # make; reporting that as "out of proportion" accuses a coincidence, so such a fit is no match at all.
    sv = np.linalg.svd(H[:2, :2], compute_uv=False)
    return bool(sv[0] <= MAX_ANISOTROPY * sv[1])


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


def _connected(cells: list[dict], sims: list[float],
               deltas: list[float]) -> tuple[list[dict], list[float], list[float]]:
    """A changed area spans neighbouring cells; one cell alone is a resampling or compression artefact more
    often than an edit, so it is kept only when a flagged neighbour (8-connected) backs it or it is far past
    the limits."""
    at = {(c["row"], c["col"]) for c in cells}
    keep = [c for c in cells
            if any((c["row"] + dr, c["col"] + dc) in at for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)
            or c["ssim"] < CELL_SSIM_FLOOR - LONE_CELL_SSIM or c["delta_e"] > CELL_DELTA_E_CEIL * LONE_CELL_DELTA]
    return keep, sims, deltas


def _half_chroma(rgb: np.ndarray) -> np.ndarray:
    """Colour at half resolution, as JPEG and 4:2:0 video store it, brightness untouched."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    h, w = lab.shape[:2]
    for i in (1, 2):
        half = cv2.resize(lab[..., i], (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
        lab[..., i] = cv2.resize(half, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def _jpeg(rgb: np.ndarray, quality: int) -> np.ndarray:
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.cvtColor(cv2.imdecode(buf, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def _compare(asset: PreparedAsset, scene: np.ndarray, H: np.ndarray,
             box: tuple[int, int, int, int]) -> tuple[list[dict], list[float], list[float]]:
    """Per-cell structure and colour of the placed artwork against the official one, in the image's own pixels.

    Warping the image back to the artwork's frame stretches its compression blocks and blurred edges over
    the comparison and reads them as changes (half the false alarms on a JPEG). So the official artwork goes
    the other way: warped forward onto the image, laid over the image's own background, put through the JPEG
    quality that brings it closest to what is there, and both sides have their colour halved as JPEG does.
    What is left to differ is what was changed. Within a pixel of misregistration and on the anti-aliased
    rims of strong edges nothing is counted, because a fit is never exact there.
    """
    h, w = asset.gray.shape
    sh, sw = scene.shape[:2]
    # The window around the placement starts on the 16-pixel grid JPEG blocks sit on, so recompressing the
    # artwork puts its blocks where the image's were.
    x0, y0 = max(0, box[0] - 8), max(0, box[1] - 8)
    x0, y0 = x0 - x0 % 16, y0 - y0 % 16
    x1, y1 = min(sw, box[2] + 8), min(sh, box[3] + 8)
    cw, ch = x1 - x0, y1 - y0
    if cw < 8 or ch < 8:
        return [], [], []
    seen = np.ascontiguousarray(scene[y0:y1, x0:x1])
    Hc = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1.0]]) @ H
    # Shrunk first with area averaging, as the copy in the image was, so a small placement isn't aliased.
    fx, fy = min(1.0, float(np.linalg.norm(H[:2, 0]))), min(1.0, float(np.linalg.norm(H[:2, 1])))
    art, S = asset.rgb, np.eye(3)
    if fx < 1 or fy < 1:
        tw, th = max(1, round(w * fx)), max(1, round(h * fy))
        art = cv2.resize(asset.rgb, (tw, th), interpolation=cv2.INTER_AREA)
        S = np.diag([tw / w, th / h, 1.0])
    warped = cv2.warpPerspective(art, Hc @ np.linalg.inv(S), (cw, ch),
                                 flags=cv2.INTER_LINEAR if fx < 1 or fy < 1 else cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
    # Score only the artwork's interior. Anti-aliased outlines blend with whatever background the scene
    # has, which is not a change to the asset.
    interior = cv2.erode(asset.mask.astype(np.uint8), np.ones((9, 9), np.uint8))
    cell_id = np.full((h, w), -1, np.int16)
    for r in range(GRID):
        for c in range(GRID):
            ys, xs = slice(r * h // GRID, (r + 1) * h // GRID), slice(c * w // GRID, (c + 1) * w // GRID)
            cell_id[ys, xs] = np.where(interior[ys, xs] > 0, r * GRID + c, -1)
    cells_at = cv2.warpPerspective(cell_id, Hc, (cw, ch), flags=cv2.INTER_NEAREST,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=-1)
    on = cells_at >= 0
    if not on.any():
        return [], [], []
    alpha = cv2.warpPerspective(asset.mask.astype(np.uint8) * 255, Hc, (cw, ch), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT).astype(np.float32)[..., None] / 255.0
    ref = (warped * alpha + seen * (1 - alpha)).astype(np.uint8)
    target = _lab(seen)[on]
    best = float(np.linalg.norm(_lab(ref)[on] - target, axis=1).mean())
    for quality in JPEG_QUALITIES:  # an image that was never a JPEG keeps the clean artwork
        candidate = _jpeg(ref, quality)
        d = float(np.linalg.norm(_lab(candidate)[on] - target, axis=1).mean())
        if d < best:
            ref, best = candidate, d
    ref, img = _half_chroma(ref), _half_chroma(seen)

    ref_gray, img_gray = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY), cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    ref_lab, img_lab = _lab(ref), _lab(img)
    ssim = _ssim_map(ref_gray, img_gray)
    delta = np.linalg.norm(ref_lab - img_lab, axis=2)
    for dy in range(-REGISTER_SLACK, REGISTER_SLACK + 1):
        for dx in range(-REGISTER_SLACK, REGISTER_SLACK + 1):
            if dx or dy:
                shift = np.float32([[1, 0, dx], [0, 1, dy]])
                moved = cv2.warpAffine(ref_lab, shift, (cw, ch), borderMode=cv2.BORDER_REPLICATE)
                delta = np.minimum(delta, np.linalg.norm(moved - img_lab, axis=2))
                moved_gray = cv2.warpAffine(ref_gray, shift, (cw, ch), borderMode=cv2.BORDER_REPLICATE)
                ssim = np.maximum(ssim, _ssim_map(moved_gray, img_gray))
    edges = np.zeros((ch, cw), bool)
    for g in (img_gray, ref_gray):
        edges |= (np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1))) > EDGE_STRENGTH
    rims = cv2.dilate(edges.astype(np.uint8), np.ones((2 * EDGE_RIM + 1,) * 2, np.uint8)) > 0
    delta = cv2.GaussianBlur(np.where(rims, 0.0, delta), (7, 7), 2.0)

    area_scale = abs(float(np.linalg.det(Hc[:2, :2]))) / float(Hc[2, 2]) ** 2
    cells, sims, deltas = [], [], []
    for r in range(GRID):
        for c in range(GRID):
            ys, xs = slice(r * h // GRID, (r + 1) * h // GRID), slice(c * w // GRID, (c + 1) * w // GRID)
            whole = interior[ys, xs].astype(bool)
            if whole.mean() < MIN_CELL_COVERAGE:
                continue
            m = cells_at == r * GRID + c
            if m.sum() < OUT_OF_FRAME * whole.sum() * area_scale:
                # Most of this part of the artwork would sit outside the image: nothing there looks like it.
                # Counted against the likeness, so a logo cut down to its wordmark is not taken for a good
                # copy of the logo, but not called a change: cropping is not editing.
                sims.append(0.0)
                continue
            if m.sum() < 16:
                continue
            s = float(ssim[m].mean())
            d = float(np.percentile(delta[m], 90))
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
