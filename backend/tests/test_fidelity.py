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
