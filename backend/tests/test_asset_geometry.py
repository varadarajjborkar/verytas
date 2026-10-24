"""Artwork placed out of proportion, skewed or mirrored, and the findings for retired and competitors' marks.

Warping a match back into the artwork's frame undoes a stretch, so before these checks a squashed logo
compared as a perfect copy, and a mirrored one wasn't found at all.
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from tests.helpers import make_ctx, system_rule_views
from verytas.media import assets as asset_match
from verytas.prism import agents
from verytas.prism.agents import AgentTree, OfficialAsset, ReviewRun
from verytas.prism.governor import Governor
from verytas.providers.offline import OfflineJudge, OfflineLLM
from verytas.showcase import _kit

_FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def _wordmark(text: str) -> Image.Image:
    """Lettering with plenty of keypoints and no symmetry: what a brand's wordmark is to the matcher."""
    path = next((f for f in _FONTS if Path(f).is_file()), None)
    font = ImageFont.truetype(path, 96) if path else ImageFont.load_default(96)
    img = Image.new("RGBA", (560, 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((20, 20), text, font=font, fill=(20, 60, 140, 255))
    d.rectangle((20, 135, 380, 145), fill=(240, 130, 40, 255))
    return img


def _scene(art: Image.Image, *, wide: float = 1.0, tall: float = 1.0, shear: float = 0.0, mirror: bool = False,
           rotate: float = 0.0) -> Image.Image:
    """The artwork on a busy background, placed the way a creator might have."""
    rnd = random.Random(3)
    bg = Image.new("RGB", (1000, 750), (235, 232, 225))
    d = ImageDraw.Draw(bg)
    for _ in range(30):
        x, y, r = rnd.randint(-80, 1000), rnd.randint(-80, 750), rnd.randint(20, 150)
        d.ellipse((x, y, x + r, y + r * rnd.uniform(.5, 1.5)), fill=tuple(rnd.randint(40, 230) for _ in range(3)))
    bg = bg.filter(ImageFilter.GaussianBlur(2))
    a = art.convert("RGBA")
    if mirror:
        a = a.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    a = a.resize((int(a.width * wide * 0.8), int(a.height * tall * 0.8)), Image.LANCZOS)
    if shear:
        k = np.tan(np.radians(shear))
        a = a.transform((int(a.width + k * a.height), a.height), Image.Transform.AFFINE,
                        (1, k, -k * a.height, 0, 1, 0), Image.BICUBIC)
    if rotate:
        a = a.rotate(rotate, Image.BICUBIC, expand=True)
    bg.paste(a, (120, 120), a)
    return bg


def _icon() -> Image.Image:
    """Flat two-tone artwork in greys, so no colour channel adds keypoints either: found by template."""
    icon = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(icon)
    d.rounded_rectangle((10, 10, 290, 290), 60, fill=(50, 50, 55, 255))
    d.polygon([(90, 210), (150, 80), (210, 210)], fill=(215, 215, 210, 255))
    return icon


@pytest.fixture(scope="module")
def wordmark():
    return asset_match.prepare(1, _wordmark("Kitepath"))


@pytest.mark.parametrize("how", [{}, {"rotate": 10}, {"wide": 0.5, "tall": 0.5}])
def test_artwork_resized_or_rotated_in_proportion_is_not_distorted(wordmark, how):
    m = asset_match.match(wordmark, _scene(_wordmark("Kitepath"), **how))
    assert m.found and not m.distortions and not m.mirrored


@pytest.mark.parametrize(("how", "says"), [
    ({"wide": 1.3}, "too wide for its height"),
    ({"wide": 0.75}, "too tall for its width"),
    ({"tall": 1.2}, "too tall for its width"),
    ({"shear": 12}, "skewed by 12 degrees"),
    ({"mirror": True}, "mirrored"),
])
def test_stretched_skewed_and_mirrored_artwork_is_named(wordmark, how, says):
    m = asset_match.match(wordmark, _scene(_wordmark("Kitepath"), **how))
    assert m.found and any(says in d for d in m.distortions), m.distortions


def test_the_measured_stretch_is_close_to_the_real_one(wordmark):
    m = asset_match.match(wordmark, _scene(_wordmark("Kitepath"), wide=1.3))
    assert m.stretch == pytest.approx(1.3, abs=0.06)


def test_the_character_stretched_or_squashed_is_measured_not_mirrored():
    """Few keypoints on a rounded emblem let a homography bend around the distortion, or a flipped fit
    stand in for it; the affine fit and the pixel alignment keep it a proportion error."""
    kit = asset_match.prepare(2, _kit())
    for how, expect in (({"wide": 1.3}, 1.3), ({"wide": 0.75}, 0.75)):
        m = asset_match.match(kit, _scene(_kit(), **how))
        assert m.found and not m.mirrored and m.stretch == pytest.approx(expect, abs=0.08), (how, m.stretch)


def test_a_fit_no_layout_could_produce_is_no_match():
    """A dozen keypoints can be fitted by a map that squeezes one axis 20 times; that is a coincidence,
    not artwork, and accusing it of being out of proportion would be a false alarm."""
    assert not asset_match._plausible(np.array([[20.0, 0, 0], [0, 1.0, 0], [0, 0, 1]]))
    assert asset_match._plausible(np.array([[1.3, 0, 0], [0, 1.0, 0], [0, 0, 1]]))


def test_a_mirrored_character_is_found_and_called_mirrored():
    m = asset_match.match(asset_match.prepare(2, _kit()), _scene(_kit(), mirror=True))
    assert m.found and m.mirrored


def test_flat_artwork_found_by_template_is_measured_too():
    prepared = asset_match.prepare(3, _icon())
    assert asset_match.flat(prepared)
    right = asset_match.match(prepared, _scene(_icon()))
    wide = asset_match.match(prepared, _scene(_icon(), wide=1.3))
    assert right.found and not right.distortions
    assert wide.found and wide.stretch == pytest.approx(1.3, abs=0.06)


def test_a_logo_as_bright_as_its_background_is_found_by_its_colour():
    # Red lettering on a green field: nearly the same grey, so on lightness alone there is little to
    # match. The chroma channels see it in full.
    mark = Image.new("RGBA", (560, 160), (0, 0, 0, 0))
    path = next((f for f in _FONTS if Path(f).is_file()), None)
    font = ImageFont.truetype(path, 96) if path else ImageFont.load_default(96)
    ImageDraw.Draw(mark).text((20, 20), "Vipera", font=font, fill=(205, 70, 50, 255))
    scene = Image.new("RGB", (1000, 750), (95, 160, 90))
    scene.paste(mark, (200, 250), mark)
    m = asset_match.match(asset_match.prepare(4, mark), scene)
    assert m.found and not m.distortions


def _run(assets: list[OfficialAsset]) -> tuple[ReviewRun, agents.AgentNode]:
    rules = system_rule_views()
    run = ReviewRun(base=make_ctx("x", rules), llm=OfflineLLM(), judge=OfflineJudge(), vision=OfflineLLM(),
                    governor=Governor(1, 1), tree=AgentTree(8, 10), rule_by_code={r.code: r for r in rules},
                    assets=assets, content_tier_rank=0, allow_cloud_vision=False, semantic_threshold=0.6,
                    ocr_min_confidence=0.8)
    return run, run.tree.nodes.setdefault("a1", agents.AgentNode("a1", "image", "img", None, 0))


def _asset(id_: int, name: str, kind: str = "logo", retired: bool = False) -> OfficialAsset:
    return OfficialAsset(id_, name, kind, "full", False, None, None, "", retired=retired)


def test_a_distorted_logo_is_a_finding_with_its_box():
    hit = asset_match.AssetMatch(1, True, 40, (10, 10, 210, 90), similarity=0.97, stretch=1.3)
    run, node = _run([_asset(1, "Kitepath logo")])
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [hit], None)
    [f] = run.findings
    assert f.rule_code == "VIS-ASSET-DISTORTED" and "too wide" in f.explanation
    assert f.locator["box"] == [10, 10, 210, 90]


def test_an_old_logo_is_reported_as_retired_not_as_an_altered_current_one():
    # The 2024 logo matches where it is, and the current logo matches the same spot less well.
    old = asset_match.AssetMatch(2, True, 60, (10, 10, 210, 90), similarity=0.98)
    current = asset_match.AssetMatch(1, True, 30, (12, 11, 208, 92), similarity=0.7,
                                     altered_cells=[{"row": 0, "col": 1, "change": "shape"}])
    run, node = _run([_asset(1, "Kitepath logo"), _asset(2, "Kitepath logo (2024)", retired=True)])
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [current, old], None)
    assert [f.rule_code for f in run.findings] == ["VIS-ASSET-RETIRED"]


def test_a_competitors_mark_is_a_finding_and_never_judged_as_ours():
    hit = asset_match.AssetMatch(3, True, 50, (0, 0, 100, 100), similarity=0.99, stretch=1.4)
    run, node = _run([_asset(3, "StudyMax logo", kind="competitor")])
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [hit], None)
    [f] = run.findings
    assert f.rule_code == "VIS-COMPETITOR-MARK" and "StudyMax" in f.title


def test_retired_and_competitor_artwork_is_not_shown_to_the_vision_model():
    run, _ = _run([_asset(1, "Logo"), _asset(2, "Old logo", retired=True), _asset(3, "Rival", kind="competitor")])
    assert [a.name for a in agents._shareable(run)] == ["Logo"]


def test_restricted_artwork_is_a_leak_unless_public_artwork_fits_far_better():
    from verytas.media.assets import AssetMatch

    public = AssetMatch(1, True, 60, (0, 0, 300, 120), similarity=0.95)
    secret = AssetMatch(2, True, 20, (0, 0, 300, 120), similarity=0.9, core=(10, 10, 120, 110))
    run, node = _run([_asset(1, "Logo"), OfficialAsset(2, "Logo 2027", "logo", "full", True, None, None, "")])
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [public, secret], None)
    assert [f.rule_code for f in run.findings] == ["CONF-LEAK"]  # 0.05 better is not far better
    secret.similarity = 0.6
    run, node = _run([_asset(1, "Logo"), OfficialAsset(2, "Logo 2027", "logo", "full", True, None, None, "")])
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [public, secret], None)
    assert run.findings == []


def test_a_partial_match_inside_better_artwork_raises_nothing():
    from verytas.media.assets import AssetMatch

    logo = AssetMatch(1, True, 60, (100, 100, 400, 200), similarity=0.96)
    pack = AssetMatch(2, True, 18, (40, 20, 470, 600), similarity=0.55, core=(110, 105, 390, 195),
                      altered_cells=[{"row": 4, "col": 2, "change": "shape"}])
    run, node = _run([_asset(1, "Logo"), _asset(2, "Pack", kind="packaging")])
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [logo, pack], None)
    assert run.findings == []


def test_boxes_are_in_the_images_own_pixels_on_large_images(wordmark):
    # Matching runs on a copy at most 2000 px wide; the box must still be where the artwork is in the
    # original, where OCR line boxes and the layout checks measure.
    art = _wordmark("Kitepath").resize((1680, 480), Image.LANCZOS)
    scene = Image.new("RGB", (4000, 3000), (235, 232, 225))
    scene.paste(art, (1000, 800), art)
    m = asset_match.match(wordmark, scene)
    assert m.found
    x0, y0, x1, y1 = m.box
    assert abs(x0 - 1000) < 120 and abs(y0 - 800) < 120 and abs(x1 - 2680) < 160 and abs(y1 - 1280) < 160, m.box


def test_an_altered_logo_says_where_in_plain_words():
    hit = asset_match.AssetMatch(1, True, 40, (10, 10, 210, 90), similarity=0.8,
                                 altered_cells=[{"row": 0, "col": 0, "change": "colour"},
                                                {"row": 5, "col": 5, "change": "shape"}])
    run, node = _run([_asset(1, "Kitepath logo")])
    agents._asset_findings(run, node, "img:x", {"image": "x"}, [hit], None)
    [f] = run.findings
    assert "colour differs at the top left" in f.explanation and "shape at the bottom right" in f.explanation
    assert "r1c1" not in f.explanation


@pytest.mark.parametrize("keystone", [0.10, 0.15, 0.25])
def test_artwork_photographed_at_an_angle_is_not_called_out_of_proportion(wordmark, keystone):
    """A poster shot from one side narrows towards its far edge. Many keypoints agree on that tilt, so the
    homography keeps it as perspective; preferring the flat (affine) fit read it as a stretched copy."""
    import cv2

    scene = np.asarray(_scene(_wordmark("Kitepath")))
    h, w = scene.shape[:2]
    pull = keystone * h / 2
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[0, 0], [w, pull], [w, h - pull], [0, h]])
    tilted = cv2.warpPerspective(scene, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(235, 232, 225))
    m = asset_match.match(wordmark, Image.fromarray(tilted))
    assert m.found and not any("proportion" in d for d in m.distortions), m.distortions
