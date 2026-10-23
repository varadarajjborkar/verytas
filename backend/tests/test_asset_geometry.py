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
