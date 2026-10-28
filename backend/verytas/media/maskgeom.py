"""Shape of a cut-out against the shape of the artwork: silhouette alignment and stretch.

Both inputs are boolean masks, so this is plain numpy and OpenCV and runs wherever `fidelity` does.

Silhouette alignment
    A cut-out is the artwork under some similarity (shift, scale, rotation) if its silhouette lines up
    with the artwork's once both are brought to unit area at their centroids and one is turned to the
    best angle. `similarity_iou` is that best overlap. Leaked background or a clipped limb lowers it.

Stretch
    A stretched redraw is the artwork under a *linear* map that is not a similarity. Whitening a mask by
    its covariance (second-order moments) makes any two masks related by a linear map differ only by a
    rotation, so the map is `A = C_c^(1/2) R C_a^(-1/2)` with `C` the covariances of candidate and
    artwork and `R` the rotation found by lining the whitened silhouettes up. The singular values of `A`
    are the scale along and across the stretch axis; their ratio is the anisotropy (1.0 for a similarity,
    1.35 for a body 35% wider than the artwork's proportions) and the leading left singular vector is the
    stretch direction in the cut-out's frame. `eigenvalue_stretch` is the cheaper moment-only reading
    that assumes the principal axes correspond; `fit_stretch` does not.

The overlap of the artwork under `A` with the cut-out says whether a stretch explains the difference at
all: a missing tail or a leaked background patch changes the moments too, but no linear map brings the
silhouettes together, so `Stretch.fit` stays low and the caller does not call it a stretch.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

GRID = 64  # canonical raster side for aligning silhouettes
SPAN = 3.4  # half-width of the canonical raster, in standard deviations of the whitened mask
ANGLE_STEP = 3  # degrees, coarse rotation search
MIN_PIXELS = 64  # a mask smaller than this has no usable second moments


@dataclass(frozen=True)
class Stretch:
    anisotropy: float  # >= 1: how much longer the stretch axis is than the one across it
    direction: float  # degrees from the horizontal of the stretched axis in the cut-out's frame, 0 to 90
    fit: float  # overlap (IoU) of the artwork under the fitted map with the cut-out, 0 to 1
    matrix: tuple[float, float, float, float]  # A, row-major, artwork pixels to cut-out pixels

    @property
    def wider(self) -> bool:
        """True when the stretch axis is nearer horizontal than vertical."""
        return self.direction < 45


def moments(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Centroid (x, y) and 2 x 2 covariance of a mask's pixel coordinates (pixel centres)."""
    ys, xs = np.nonzero(mask)
    if len(xs) < MIN_PIXELS:
        raise ValueError("mask too small for moments")
    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    mu = pts.mean(axis=0)
    c = np.cov((pts - mu).T, bias=True) + np.eye(2) / 12.0  # a pixel is a unit square, not a point
    return mu, c


def _sqrtm(c: np.ndarray, inverse: bool = False) -> np.ndarray:
    w, v = np.linalg.eigh(c)
    w = np.clip(w, 1e-9, None)
    return (v * (w ** (-0.5 if inverse else 0.5))) @ v.T


def _canonical(mask: np.ndarray, mu: np.ndarray, linear: np.ndarray) -> np.ndarray:
    """The mask raster after x -> linear (x - mu), placed so the origin is the raster's centre."""
    scale = GRID / (2 * SPAN)
    m = np.zeros((2, 3))
    m[:, :2] = linear * scale
    m[:, 2] = GRID / 2 - (linear * scale) @ mu
    out = cv2.warpAffine(mask.astype(np.float32), m, (GRID, GRID), flags=cv2.INTER_LINEAR)
    return out >= 0.5


def _rotate(raster: np.ndarray, degrees: float) -> np.ndarray:
    m = cv2.getRotationMatrix2D((GRID / 2 - 0.5, GRID / 2 - 0.5), degrees, 1.0)
    return cv2.warpAffine(raster.astype(np.float32), m, (GRID, GRID), flags=cv2.INTER_LINEAR) >= 0.5


def _overlap(a: np.ndarray, b: np.ndarray) -> float:
    u = int(np.logical_or(a, b).sum())
    return float(np.logical_and(a, b).sum()) / u if u else 0.0


def _best_turn(art: np.ndarray, cand: np.ndarray) -> tuple[float, float]:
    """(angle in degrees, IoU) that turns `art` onto `cand`, coarse search refined around the best."""
    scored = [(_overlap(_rotate(art, a), cand), a) for a in range(0, 360, ANGLE_STEP)]
    best, angle = max(scored)
    for a in np.arange(angle - ANGLE_STEP, angle + ANGLE_STEP + 0.01, 1.0):
        s = _overlap(_rotate(art, float(a)), cand)
        if s > best:
            best, angle = s, float(a)
    return angle % 360, best


def similarity_iou(art: np.ndarray, cand: np.ndarray) -> float:
    """Best overlap of two silhouettes after centring, scaling to equal area and turning one.

    The ground for choosing among candidate cut-outs: it is blind to size, place and tilt, which are not
    the character's fault, and sees leaked background, clipped limbs and a different outline."""
    ma, ca = moments(art)
    mc, cc = moments(cand)
    # Isotropic scale: unit area on both sides, so only shape is compared.
    ka, kc = 1 / np.sqrt(np.sqrt(np.linalg.det(ca))), 1 / np.sqrt(np.sqrt(np.linalg.det(cc)))
    ra = _canonical(art, ma, np.eye(2) * ka)
    rc = _canonical(cand, mc, np.eye(2) * kc)
    return _best_turn(ra, rc)[1]


def fit_stretch(art: np.ndarray, cand: np.ndarray) -> Stretch:
    """The linear map that best takes the artwork's silhouette to the cut-out's, read as a stretch."""
    ma, ca = moments(art)
    mc, cc = moments(cand)
    wa, wc = _sqrtm(ca, inverse=True), _sqrtm(cc, inverse=True)
    ra, rc = _canonical(art, ma, wa), _canonical(cand, mc, wc)
    angle, fit = _best_turn(ra, rc)
    # cv2 rotates counter-clockwise on screen (y down): x' = R x with R built from the same angle.
    t = np.radians(angle)
    rot = np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])
    a = _sqrtm(cc) @ rot @ wa
    u, s, _ = np.linalg.svd(a)
    direction = float(np.degrees(np.arctan2(abs(u[1, 0]), abs(u[0, 0]))))
    return Stretch(float(s[0] / s[1]), direction, fit, (a[0, 0], a[0, 1], a[1, 0], a[1, 1]))


def eigenvalue_stretch(art: np.ndarray, cand: np.ndarray) -> float:
    """The moment-only reading: the ratio of the two masks' principal-axis spreads, >= 1.

    Principal axes are matched in order (longest to longest), which is right for a stretch along or
    across the body's long axis and blind to one that turns a tall body into a wide one: its longest
    axis changes sides. It needs no alignment search, so it is the cheap first test."""
    la = np.sort(np.linalg.eigvalsh(moments(art)[1]))[::-1]
    lc = np.sort(np.linalg.eigvalsh(moments(cand)[1]))[::-1]
    r = float(np.sqrt((lc[0] / lc[1]) / (la[0] / la[1])))
    return max(r, 1 / r)
