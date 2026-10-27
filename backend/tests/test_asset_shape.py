"""Shape-first location: a recoloured app icon is found by its outline, and nothing else is.

The grey keypoints of a small flat icon do not survive a hue swap (light regions turn dark and the other way
round), so the icon was never found and the recolouring went unreported. The fallback in `media/shape.py` finds
it by edge direction and verifies the palette; these tests pin what it must find and what it must leave alone.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from tests.helpers import make_ctx, system_rule_views
from verytas.media import assets as asset_match
from verytas.media import shape
from verytas.prism import agents
from verytas.prism.agents import AgentTree, OfficialAsset, ReviewRun
from verytas.prism.governor import Governor
from verytas.providers.offline import OfflineJudge, OfflineLLM

TILE, EMBLEM = (255, 70, 20), (20, 120, 230)


def _icon(tile=TILE, emblem=EMBLEM) -> Image.Image:
    """A rounded tile, a hexagon and a white bar: three flat regions, no keypoint-rich texture."""
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 299, 299), 66, fill=tile)
    d.polygon([(150, 50), (235, 100), (235, 200), (150, 250), (65, 200), (65, 100)], fill=emblem)
    d.rectangle((120, 90, 180, 110), fill=(255, 255, 255))
    d.rectangle((140, 90, 160, 210), fill=(255, 255, 255))
    return img


def _swapped(img: Image.Image) -> Image.Image:
    """The generator's recolour: every coloured pixel's hue rotated, white left alone."""
    hsv = np.asarray(img.convert("RGB").convert("HSV")).astype(int)
    hsv[..., 0] = np.where(hsv[..., 1] > 64, (hsv[..., 0] + 100) % 256, hsv[..., 0])
    out = Image.fromarray(hsv.astype("uint8"), "HSV").convert("RGB")
    out.putalpha(img.getchannel("A"))
    return out


def _scene(art: Image.Image, width: int = 480, at=(300, 400), busy: bool = False) -> tuple[Image.Image, list[int]]:
    bg = Image.new("RGB", (1000, 1000), (232, 240, 226))
    if busy:
        rnd = random.Random(5)
        d = ImageDraw.Draw(bg)
        for _ in range(40):
            x, y, r = rnd.randint(-80, 1000), rnd.randint(-80, 1000), rnd.randint(20, 150)
            d.ellipse((x, y, x + r, y + r * rnd.uniform(.5, 1.5)), fill=tuple(rnd.randint(40, 230) for _ in range(3)))
        bg = bg.filter(ImageFilter.GaussianBlur(2))
    a = art.resize((width, width), Image.LANCZOS)
    bg.paste(a, at, a)
    return bg, [at[0], at[1], at[0] + width, at[1] + width]


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


@pytest.fixture(scope="module")
def icon():
    return asset_match.prepare(1, _icon())


def test_only_compact_flat_artwork_gets_a_shape_model(icon):
    assert icon.outline is not None and 2 <= len(icon.outline.palette) <= shape.MAX_REGIONS
    wide = Image.new("RGBA", (800, 200), (0, 0, 0, 0))
    ImageDraw.Draw(wide).rectangle((0, 0, 799, 199), fill=(200, 30, 30, 255))
    assert asset_match.prepare(2, wide).outline is None  # a wordmark or lockup is not an icon
    rnd = np.random.default_rng(1)
    noisy = Image.fromarray(rnd.integers(0, 255, (300, 300, 3), dtype=np.uint8))
    assert asset_match.prepare(3, noisy).outline is None  # a photograph has no flat regions to swap


@pytest.mark.parametrize("busy", [False, True])
def test_a_recoloured_icon_is_found_by_shape_and_its_colours_called_swapped(icon, busy):
    scene, box = _scene(_swapped(_icon()), busy=busy)
    m = asset_match.match(icon, scene)
    assert m.found and m.by_shape and _iou(m.box, box) > 0.85, (m.found, m.box, box)
    assert m.altered and any(c["change"] == "colour" for c in m.altered_cells)
    assert m.palette_swap and all(old != new for old, new in m.palette_swap)
    assert not m.distortions  # in proportion: the outline fit is a uniform scale


def test_the_keypoints_alone_do_not_find_it():
    """The premise: without the fallback a hue swap loses this icon. If this ever starts passing, the
    fallback is no longer what the benchmark's 'recoloured icon' row depends on."""
    prepared = asset_match.prepare(1, _icon())
    prepared.outline = None
    scene, _ = _scene(_swapped(_icon()))
    assert not asset_match.match(prepared, scene).found


def test_the_same_icon_in_its_own_colours_is_found_and_raises_nothing(icon):
    scene, box = _scene(_icon(), busy=True)
    m = asset_match.match(icon, scene)
    assert m.found and _iou(m.box, box) > 0.85 and not m.altered and not m.distortions


def test_a_scene_without_the_icon_finds_nothing():
    prepared = asset_match.prepare(1, _icon())
    rnd = random.Random(9)
    bg = Image.new("RGB", (1000, 1000), (240, 236, 230))
    d = ImageDraw.Draw(bg)
    for _ in range(25):
        x, y, r = rnd.randint(0, 900), rnd.randint(0, 900), rnd.randint(30, 160)
        d.rounded_rectangle((x, y, x + r, y + r), r // 4, fill=tuple(rnd.randint(30, 230) for _ in range(3)))
    assert not asset_match.match(prepared, bg).found


def test_the_emblem_alone_on_a_plain_page_is_not_the_icon(icon):
    """A logo lockup carries the icon's emblem without its tile. Most of the icon's edges are there, and
    every region is flat; only the silhouette (nothing sets the tile apart from the page) says no."""
    emblem = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(emblem)
    d.polygon([(150, 50), (235, 100), (235, 200), (150, 250), (65, 200), (65, 100)], fill=(20, 120, 230))
    d.rectangle((120, 90, 180, 110), fill=(255, 255, 255))
    d.rectangle((140, 90, 160, 210), fill=(255, 255, 255))
    scene = Image.new("RGB", (1000, 1000), (232, 240, 226))
    for w, at in ((360, (80, 80)), (300, (500, 600))):
        a = emblem.resize((w, w), Image.LANCZOS)
        scene.paste(a, at, a)
        draw = ImageDraw.Draw(scene)
        draw.text((at[0] + w + 20, at[1] + w // 2), "Wordmark", font=ImageFont.load_default(40), fill=(20, 120, 230))
    # The shape fallback in isolation: the keypoints may still match the emblem on their own account.
    assert shape.locate(icon.outline, icon.rgb, shape.SceneShape(np.asarray(scene))) is None


def test_a_page_tile_the_colour_of_the_page_is_not_a_find(icon):
    # The icon's tile painted in the page's own colour: no silhouette to find, so the status quo (not found)
    # is kept rather than guessed at.
    scene, _ = _scene(_icon(tile=(232, 240, 226)))
    m = asset_match.match(icon, scene)
    assert not m.by_shape


def test_the_gates_are_the_ones_set_on_the_benchmark():
    assert shape.MIN_RECALL <= 0.85 and shape.MIN_SILHOUETTE >= 0.8 and shape.MIN_UNIFORMITY >= 0.9


def _run(assets: list[OfficialAsset]) -> tuple[ReviewRun, agents.AgentNode]:
    rules = system_rule_views()
    run = ReviewRun(base=make_ctx("x", rules), llm=OfflineLLM(), judge=OfflineJudge(), vision=OfflineLLM(),
                    governor=Governor(1, 1), tree=AgentTree(8, 10), rule_by_code={r.code: r for r in rules},
                    assets=assets, content_tier_rank=0, allow_cloud_vision=False, semantic_threshold=0.6,
                    ocr_min_confidence=0.8)
    return run, run.tree.nodes.setdefault("a1", agents.AgentNode("a1", "image", "img", None, 0))


def test_the_finding_says_the_palette_was_swapped():
    hit = asset_match.AssetMatch(1, True, 0, (10, 10, 210, 210), similarity=0.4, by_shape=True,
                                 altered_cells=[{"row": 1, "col": 1, "change": "colour"},
                                                {"row": 1, "col": 2, "change": "colour"}],
                                 palette_swap=[("#ff4614", "#14ff46"), ("#1478e6", "#e61478")])
    run, node = _run([OfficialAsset(1, "Kitepath app icon", "icon", "full", False, None, None, "")])
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [hit], None)
    [f] = run.findings
    assert f.rule_code == "VIS-ASSET-ALTERED" and "changed colours" in f.title
    assert "#ff4614 is now #14ff46" in f.explanation and "palette was swapped" in f.explanation
