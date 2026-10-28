"""Reclaiming clipped parts and judging a cut-out, on synthetic scenes: no models, no images."""

import cv2
import numpy as np
import pytest

from verytas.media import maskcheck

RED, YELLOW, GREY = (200, 30, 30), (240, 200, 20), (120, 130, 140)
PALETTE = [(RED, 0.8), (YELLOW, 0.2)]


def scene(h: int = 240, w: int = 320) -> tuple[np.ndarray, np.ndarray]:
    """A grey street, a red body and the mask SAM would give for it."""
    rgb = np.full((h, w, 3), GREY, np.uint8)
    cv2.circle(rgb, (150, 120), 60, RED, -1)
    mask = np.zeros((h, w), np.uint8)
    cv2.circle(mask, (150, 120), 60, 1, -1)
    return rgb, mask.astype(bool)


def test_a_clipped_appendage_in_the_artworks_colour_is_taken_back():
    rgb, mask = scene()
    rgb[110:130, 212:232] = YELLOW  # a tail just off the body, which the mask dropped
    out = maskcheck.reclaim(rgb, mask, PALETTE)
    assert out[120, 222] and out.sum() > mask.sum()
    assert out[mask].all()  # nothing the segmenter chose is taken away


def test_a_shape_that_floats_a_little_off_the_body_still_belongs_to_it():
    rgb, mask = scene()
    rgb[110:130, 218:238] = YELLOW  # a gap of a few pixels, as an antenna or tail piece may have
    assert maskcheck.reclaim(rgb, mask, PALETTE)[120, 228]


def test_background_in_other_colours_is_left_out():
    rgb, mask = scene()
    rgb[40:80, 215:260] = (30, 160, 60)  # a green hedge against the body: not one of the artwork's colours
    assert maskcheck.reclaim(rgb, mask, PALETTE).sum() == mask.sum()


def test_a_large_region_in_a_palette_colour_is_background_not_a_part():
    rgb, mask = scene()
    rgb[:, 215:] = YELLOW  # a yellow wall: far bigger than any part
    assert maskcheck.reclaim(rgb, mask, PALETTE).sum() == mask.sum()


def test_a_palette_coloured_shape_away_from_the_mask_is_left_out():
    rgb, mask = scene()
    rgb[20:40, 280:300] = YELLOW  # a yellow sign across the street
    assert maskcheck.reclaim(rgb, mask, PALETTE).sum() == mask.sum()


def test_an_empty_mask_stays_empty():
    rgb, _ = scene()
    empty = np.zeros(rgb.shape[:2], bool)
    assert not maskcheck.reclaim(rgb, empty, PALETTE).any()


# judge, on Kit (the showcase mascot) standing on a grey page: the segmenter's mask is the drawing's alpha,
# minus whatever a test says it clipped.

def _on_page(img):
    from PIL import Image

    small = img.resize((int(img.width * 0.75), int(img.height * 0.75)), Image.LANCZOS)
    rgba = np.asarray(small)
    h, w = rgba.shape[:2]
    page = np.full((h + 80, w + 80, 3), GREY, np.uint8)
    alpha = rgba[..., 3:] / 255.0
    page[40:40 + h, 40:40 + w] = (rgba[..., :3] * alpha + page[40:40 + h, 40:40 + w] * (1 - alpha)).astype(np.uint8)
    mask = np.zeros(page.shape[:2], bool)
    mask[40:40 + h, 40:40 + w] = rgba[..., 3] > 127
    return page, mask


def _orange(rgb):
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    return (r > 200) & (g > 100) & (g < 160) & (b < 80)


@pytest.fixture(scope="module")
def kit():
    from verytas.media.fidelity import official_reference
    from verytas.showcase import _kit

    return _kit(), official_reference(_kit())


def _clip_tail(rgb, mask):
    return mask & ~cv2.dilate(_orange(rgb).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)


def test_a_shortfall_the_mask_clipped_is_withdrawn(kit):
    from verytas.media.fidelity import compare

    img, official = kit
    rgb, mask = _on_page(img)
    clipped = _clip_tail(rgb, mask)
    assert any(d.shortfall for d in compare(official, (rgb, clipped)).differences)  # what a bare compare says
    assert maskcheck.judge(official, rgb, clipped).differences == []


def test_a_part_that_is_really_gone_is_still_reported(kit):
    img, official = kit
    a = np.array(img)
    a[_orange(a[..., :3]) & (a[..., 3] > 0)] = 0  # the tail pieces removed from the drawing itself
    from PIL import Image

    rgb, mask = _on_page(Image.fromarray(a, "RGBA"))
    assert any(d.shortfall for d in maskcheck.judge(official, rgb, mask).differences)


def test_reclaiming_never_hides_an_extra_part(kit):
    from PIL import ImageDraw

    img, official = kit
    img = img.copy()
    d = ImageDraw.Draw(img)
    d.ellipse((170, 60, 230, 115), fill="white")
    d.ellipse((186, 72, 214, 104), fill=(25, 35, 60))  # a third eye
    rgb, mask = _on_page(img)
    found = maskcheck.judge(official, rgb, _clip_tail(rgb, mask)).differences
    assert any(x.kind == "parts" and x.have > x.want for x in found)
    assert not any(x.shortfall for x in found)


def _alpha(img) -> np.ndarray:
    return np.asarray(img)[..., 3] > 127


def test_a_character_pulled_wider_is_named_as_stretched(kit):
    from PIL import Image

    img, official = kit
    wide = img.resize((int(img.width * 1.35), img.height), Image.LANCZOS)
    found = maskcheck.stretch(official[1], _alpha(wide))
    assert found is not None and found.kind == "shape" and "wider" in found.text
    tall = img.resize((img.width, int(img.height * 1.35)), Image.LANCZOS)
    assert "taller" in maskcheck.stretch(official[1], _alpha(tall)).text


def test_a_character_resized_or_turned_evenly_is_not_stretched(kit):
    from PIL import Image

    img, official = kit
    assert maskcheck.stretch(official[1], _alpha(img.resize((img.width // 2, img.height // 2), Image.LANCZOS))) is None
    assert maskcheck.stretch(official[1], _alpha(img.rotate(30, expand=True))) is None


def test_a_mask_too_small_for_moments_says_nothing(kit):
    _, official = kit
    tiny = np.zeros((40, 40), bool)
    tiny[10:14, 10:14] = True
    assert maskcheck.stretch(official[1], tiny) is None


def test_a_symmetric_body_turned_is_not_stretched():
    # An oval's rotation search cannot tell which way it faces; the unchanged ratio of its spreads says no.
    art = np.zeros((300, 300), np.uint8)
    cv2.ellipse(art, (150, 150), (100, 70), 0, 0, 360, 1, -1)
    for turn in (90, 30):
        cand = np.zeros((300, 300), np.uint8)
        cv2.ellipse(cand, (150, 150), (100, 70), turn, 0, 360, 1, -1)
        assert maskcheck.stretch(art.astype(bool), cand.astype(bool)) is None, turn
    wide = np.zeros((300, 400), np.uint8)
    cv2.ellipse(wide, (200, 150), (135, 70), 0, 0, 360, 1, -1)  # the same oval pulled 1.35x wider
    assert "wider" in maskcheck.stretch(art.astype(bool), wide.astype(bool)).text


def test_background_that_runs_out_of_view_is_not_reclaimed():
    rgb, mask = scene(400, 400)
    rgb[:, :] = GREY
    cv2.circle(rgb, (200, 200), 60, RED, -1)
    rgb[190:215, 255:] = YELLOW  # a yellow stripe touching the body that runs on far past the look window
    assert maskcheck.reclaim(rgb, mask_at(400, 400), PALETTE).sum() == mask_at(400, 400).sum()


def mask_at(h, w):
    m = np.zeros((h, w), np.uint8)
    cv2.circle(m, (200, 200), 60, 1, -1)
    return m.astype(bool)


def test_judge_withdraws_only_the_shortfall_clipping_explains(kit):
    from PIL import Image

    img, official = kit
    a = np.array(img).astype(int)
    blue = (a[..., 2] > 120) & (a[..., 0] < 100) & (a[..., 3] > 0)
    a[blue, :3] = (200, 40, 40)  # a real recolour: the brand blue is gone
    rgb, mask = _on_page(Image.fromarray(a.astype("uint8"), "RGBA"))
    found = maskcheck.judge(official, rgb, _clip_tail(rgb, mask)).differences
    assert any(d.kind == "colour_missing" for d in found)  # the recolour stays
    assert not any(d.kind == "parts" and d.shortfall and _orange(np.array([[d.colour]], np.uint8))[0, 0]
                   for d in found)  # the clipped tail does not
