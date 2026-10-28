"""Silhouette alignment and stretch, on small synthetic masks: no models, no images."""

import cv2
import numpy as np
import pytest

from verytas.media import maskgeom


def body(w: int = 200, h: int = 200) -> np.ndarray:
    """A lopsided character: a round body, a head bump and an arm on one side, so it has no symmetry that
    would let a wrong rotation line up."""
    m = np.zeros((h, w), np.uint8)
    cv2.circle(m, (w // 2, h // 2 + 10), 60, 1, -1)
    cv2.circle(m, (w // 2, h // 2 - 55), 25, 1, -1)
    cv2.ellipse(m, (w // 2 + 80, h // 2 + 10), (35, 14), -30, 0, 360, 1, -1)
    return m.astype(bool)


def warp(mask: np.ndarray, matrix: np.ndarray, size: tuple[int, int] = (500, 500)) -> np.ndarray:
    """The mask under a 2 x 2 linear map, placed away from the origin."""
    m = np.zeros((2, 3))
    m[:, :2] = matrix
    m[:, 2] = (150, 120)
    return cv2.warpAffine(mask.astype(np.uint8), m, size, flags=cv2.INTER_NEAREST).astype(bool)


def scale(sx: float, sy: float) -> np.ndarray:
    return np.diag([sx, sy])


def rotation(deg: float) -> np.ndarray:
    t = np.radians(deg)
    return np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])


def test_similarity_is_blind_to_size_place_and_tilt():
    art = body()
    cand = warp(art, 0.7 * rotation(25))
    assert maskgeom.similarity_iou(art, cand) > 0.93


def test_similarity_drops_for_a_different_outline():
    art = body()
    clipped = art.copy()
    clipped[:, 140:] = False  # the arm cut off
    assert maskgeom.similarity_iou(art, clipped) < maskgeom.similarity_iou(art, warp(art, rotation(10)))


def test_a_similarity_is_not_a_stretch():
    art = body()
    s = maskgeom.fit_stretch(art, warp(art, 0.8 * rotation(35)))
    assert s.anisotropy == pytest.approx(1.0, abs=0.05)
    assert s.fit > 0.93


@pytest.mark.parametrize("sx,sy,wider", [(1.35, 1.0, True), (1.0, 1.35, False), (0.75, 1.0, False)])
def test_stretch_is_read_with_its_direction(sx, sy, wider):
    art = body()
    s = maskgeom.fit_stretch(art, warp(art, scale(sx, sy)))
    assert s.anisotropy == pytest.approx(max(sx / sy, sy / sx), rel=0.06)
    assert s.wider is wider
    assert s.fit > 0.9


def test_stretch_survives_a_rotation_of_the_stretched_body():
    """A stretched body that is also tilted is the same stretch: the reading must not depend on which way
    the cut-out is turned."""
    art = body()
    plain = maskgeom.fit_stretch(art, warp(art, scale(1.35, 1.0)))
    tilted = maskgeom.fit_stretch(art, warp(art, rotation(30) @ scale(1.35, 1.0)))
    assert tilted.anisotropy == pytest.approx(plain.anisotropy, rel=0.06)


def test_a_missing_part_does_not_fit_a_linear_map():
    """Losing the arm changes the moments, but no stretch of the artwork gives the result: the fit says
    so, and the caller must not call it a stretch."""
    art = body()
    armless = art.copy()
    armless[:, 130:] = False
    assert maskgeom.fit_stretch(art, armless).fit < maskgeom.fit_stretch(art, warp(art, scale(1.35, 1.0))).fit


def test_eigenvalue_stretch_reads_a_stretch_along_the_long_axis():
    art = body()
    assert maskgeom.eigenvalue_stretch(art, warp(art, rotation(40))) == pytest.approx(1.0, abs=0.05)
    assert maskgeom.eigenvalue_stretch(art, warp(art, scale(1.0, 1.4))) > 1.2


def test_a_mask_too_small_has_no_moments():
    tiny = np.zeros((50, 50), bool)
    tiny[20:23, 20:23] = True
    with pytest.raises(ValueError):
        maskgeom.moments(tiny)
