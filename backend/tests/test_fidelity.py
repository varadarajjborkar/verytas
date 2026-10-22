"""Fidelity of a redrawn brand character: what changed, named, without aligning pixels."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from verytas.checks.color import ciede2000, rgb_to_lab
from verytas.media.fidelity import _ciede2000, _lab, colour_name, compare, official_reference
from verytas.showcase import _kit


def _cut(img: Image.Image, scale: float = 0.75) -> tuple[np.ndarray, np.ndarray]:
    """The character as a segmenter would hand it over: smaller than the artwork, on a busy-free page."""
    small = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    rgba = np.asarray(small)
    return rgba[..., :3], rgba[..., 3] > 127


def _recolour(img: Image.Image) -> Image.Image:
    a = np.array(img).astype(int)
    blue = (a[..., 2] > 120) & (a[..., 0] < 100) & (a[..., 3] > 0)
    a[blue, :3] = (200, 40, 40)
    return Image.fromarray(a.astype("uint8"), "RGBA")


def _third_eye(img: Image.Image) -> Image.Image:
    img = img.copy()
    d = ImageDraw.Draw(img)
    d.ellipse((170, 60, 230, 115), fill="white")
    d.ellipse((186, 72, 214, 104), fill=(25, 35, 60))
    return img


def _no_tail(img: Image.Image) -> Image.Image:
    a = np.array(img)
    a[(a[..., 0] > 200) & (a[..., 1] > 100) & (a[..., 1] < 160) & (a[..., 2] < 80)] = 0  # the orange tail pieces
    return Image.fromarray(a, "RGBA")


@pytest.fixture(scope="module")
def official():
    return official_reference(_kit())


def test_the_official_artwork_at_another_size_is_faithful(official):
    assert compare(official, _cut(_kit())).faithful


def test_a_recolour_names_the_lost_brand_colour_and_the_new_one(official):
    found = compare(official, _cut(_recolour(_kit())))
    kinds = {d.kind for d in found.differences}
    assert {"colour_missing", "colour_new"} <= kinds
    assert any(d.text.startswith("red ") for d in found.differences if d.kind == "colour_new")


def test_an_extra_eye_is_counted(official):
    found = compare(official, _cut(_third_eye(_kit())))
    assert [d.text for d in found.differences] == ["3 dark navy #17223B shapes where the artwork has 2"]


def test_a_missing_tail_is_counted(official):
    found = compare(official, _cut(_no_tail(_kit())))
    assert any(d.kind == "parts" and "orange" in d.text and d.text.startswith("0 ") for d in found.differences)


def test_vectorised_ciede2000_matches_the_reference_implementation():
    rng = np.random.default_rng(1)
    a, b = rng.integers(0, 256, (20, 3)), rng.integers(0, 256, (20, 3))
    fast = _ciede2000(_lab(a), _lab(b))
    for i in range(20):
        for j in range(20):
            slow = ciede2000(rgb_to_lab(tuple(int(v) for v in a[i])), rgb_to_lab(tuple(int(v) for v in b[j])))
            assert abs(fast[i, j] - slow) < 0.05


def test_colour_names_read_plainly():
    assert [colour_name(c) for c in [(26, 95, 209), (240, 130, 40), (23, 34, 59), (250, 250, 250), (200, 40, 40)]] \
        == ["blue", "orange", "dark navy", "white", "red"]


def test_opaque_artwork_keeps_its_own_white_features():
    # errcheck 244: on a white page, eye whites were taken for background and a faithful copy then read
    # as "white, a colour the artwork doesn't use".
    flat = Image.new("RGB", (400, 400), "white")
    flat.paste(_kit(), (0, 0), _kit())
    official = official_reference(flat)
    assert official[1][150, 150]  # an eye white is inside the character
    assert compare(official, _cut(_kit())).faithful


def test_an_empty_or_vanishing_cut_out_is_refused_plainly():
    from verytas.media.fidelity import compare as cmp

    official = official_reference(_kit())
    blank = (np.zeros((50, 50, 3), np.uint8), np.zeros((50, 50), bool))
    with pytest.raises(ValueError, match="too small"):
        cmp(official, blank)


def _tail_pieces_kept(keep: int) -> Image.Image:
    import cv2

    a = np.array(_kit())
    tail = ((a[..., 0] > 200) & (a[..., 1] > 100) & (a[..., 1] < 160) & (a[..., 2] < 80)).astype(np.uint8)
    n, comp = cv2.connectedComponents(tail, connectivity=8)
    pieces = sorted(range(1, n), key=lambda k: -(comp == k).sum())
    assert len(pieces) >= 4
    for k in pieces[keep:]:
        a[comp == k] = 0
    return Image.fromarray(a, "RGBA")


@pytest.mark.parametrize("scale", [1.0, 0.5, 0.35])
@pytest.mark.parametrize("keep", [1, 2, 3])
def test_losing_some_tail_pieces_is_reported_at_the_sizes_cut_outs_come_in(keep, scale):
    # The missing pieces shrink the cut-out's box; the artwork must not shrink with it and hide them.
    official = official_reference(_kit())
    found = compare(official, _cut(_tail_pieces_kept(keep), scale=scale))
    assert any(d.kind == "parts" and "orange" in d.text for d in found.differences), found.differences


@pytest.mark.parametrize("scale", [0.5, 0.35, 0.3])
def test_the_official_artwork_drawn_smaller_is_faithful(scale):
    # Thin strokes blur away at these sizes; the artwork is compared at the same size, so no false parts.
    found = compare(official_reference(_kit()), _cut(_kit(), scale=scale))
    assert found.faithful and found.parts_checked


def test_a_tiny_character_is_compared_by_colour_only_and_says_so():
    found = compare(official_reference(_kit()), _cut(_kit(), scale=0.2))
    assert not found.parts_checked and not [d for d in found.differences if d.kind == "parts"]


def test_a_defect_still_shows_when_drawn_small():
    official = official_reference(_kit())
    found = compare(official, _cut(_third_eye(_kit()), scale=0.35))
    assert any(d.kind == "parts" and d.text.startswith("3 ") for d in found.differences)


def test_shifted_edge_colours_do_not_change_the_count():
    # A softened copy (as JPEG and rotation leave it): edge pixels drift past the strict colour cut, and
    # the count read at the looser cut keeps the parts.
    from PIL import ImageFilter

    official = official_reference(_kit())
    soft = _kit().filter(ImageFilter.GaussianBlur(1.6))
    for scale in (0.75, 0.5):
        assert not [d for d in compare(official, _cut(soft, scale=scale)).differences if d.kind == "parts"]
