"""Artwork across a video's frames: each frame judged as its own picture, findings merged over time,
and the frames the matcher could not afford reported as partial coverage rather than a pass."""

from __future__ import annotations

import asyncio
import dataclasses
from types import SimpleNamespace

from PIL import Image

from tests.helpers import make_ctx, rule, system_rule_views
from tests.test_asset_geometry import _asset, _run
from verytas.checks.base import RawFinding, Source
from verytas.media import assets as asset_match
from verytas.media import video
from verytas.prism import agents

BOX = (0, 0, 50, 50)


def _frame(t: int) -> tuple[float, Image.Image]:
    """A frame unlike its neighbours (a block that moves), tagged with its time."""
    img = Image.new("RGB", (100, 100), "white")
    img.paste((0, 0, 0), ((t * 7) % 70, 0, (t * 7) % 70 + 25, 25))
    img.info["t"] = t
    return float(t), img


def _samples(n: int) -> list[tuple[float, Image.Image]]:
    return [_frame(t) for t in range(n)]


def _with_matcher(monkeypatch, shown: dict[int, set[int]]) -> list[int]:
    """Replace the pixel matcher: `shown` maps an asset id to the frame times where it is on screen."""
    seen: list[int] = []
    monkeypatch.setattr(agents.asset_match, "scene_features", lambda img: img)

    def fake(prepared, feats):
        t = feats.info["t"]
        seen.append(t)
        logo = prepared.asset_id == 1
        return asset_match.AssetMatch(prepared.asset_id, t in shown.get(prepared.asset_id, ()), 50, BOX,
                                      similarity=0.95 if logo else 0.6)

    monkeypatch.setattr(agents.asset_match, "match", fake)
    return seen


def _assets():
    out = []
    for a in (_asset(1, "Kitepath logo"), _asset(3, "StudyMax logo", kind="competitor")):
        out.append(dataclasses.replace(a, prepared=SimpleNamespace(asset_id=a.id)))
    return out


def _video_run(assets, timeout=180.0):
    run, node = _run(assets)
    run.media_timeout_s = timeout
    return run, node


def _match(run, node, samples, keys):
    return asyncio.run(agents._match_video_frames(run, node, "vid:x", keys, samples))


def test_a_rivals_mark_later_in_the_video_is_not_explained_by_the_logo_shown_earlier(monkeypatch):
    # Pooled into one picture, the logo at 3 s (same box, fits better) explained the rival's mark at 6 s
    # away, and the finding was lost.
    _with_matcher(monkeypatch, {1: {3}, 3: {6, 7}})
    samples = _samples(10)
    run, node = _video_run(_assets())
    per_frame = _match(run, node, samples, [samples[0], samples[3]])
    [f] = agents._frame_findings(run, "vid:x", {"video": "vid:x"}, per_frame)
    assert f.rule_code == "VIS-COMPETITOR-MARK" and f.locator["time"] == [6.0, 7.0]
    assert run.partial == set() and node.detail["frames_not_matched"] == 0


def test_the_same_defect_in_separate_stretches_is_two_findings_with_their_own_ranges():
    def hit(rule_code):
        return RawFinding("v", "visual", "Old logo", "x", 0.9, "assets", rule_code=rule_code)

    frames = [(float(t), [(1, hit("VIS-ASSET-RETIRED"))] if t in (1, 2, 5) else []) for t in range(7)]
    found = agents._merge_over_time(frames)
    assert [f.locator["time"] for f in found] == [[1.0, 2.0], [5.0, 5.0]]


def test_a_frame_never_matched_splits_a_range_instead_of_claiming_it_was_checked():
    # The matcher skipped 5 s (budget or cap); a defect at 3 s and 7 s is not "3 to 7 s".
    def hit():
        return RawFinding("v", "visual", "Old logo", "x", 0.9, "assets", rule_code="VIS-ASSET-RETIRED")

    frames = [(3.0, [(1, hit())]), (5.0, []), (7.0, [(1, hit())])]
    assert [f.locator["time"] for f in agents._merge_over_time(frames)] == [[3.0, 3.0], [7.0, 7.0]]


def test_frames_the_budget_cannot_cover_are_partial_coverage_not_a_pass(monkeypatch):
    seen = _with_matcher(monkeypatch, {})
    samples = _samples(40)
    # 3 s of matching budget at 0.5 s a frame is 6 frames; the shot starts and the sample after each
    # come first, then the rest spread over the video.
    run, node = _video_run(_assets(), timeout=6.0)
    keys = [samples[0], samples[20]]
    per_frame = _match(run, node, samples, keys)
    # Unmatched frames are kept with no matches, so they split time ranges; only six were matched.
    matched = {t for t, found in per_frame.items() if found}
    assert len(matched) == 6 and {0.0, 1.0, 20.0, 21.0} <= matched and len(per_frame) == 40
    assert max(per_frame) > 30  # spread to the end, not truncated
    assert "visual" in run.partial and node.detail["frames_not_matched"] == 34
    assert "6 of 40 distinct frames" in run.notes[0]
    assert len(seen) == 12  # two assets per matched frame, nothing else


def test_a_held_frame_costs_no_match_and_is_not_reported_as_skipped(monkeypatch):
    seen = _with_matcher(monkeypatch, {})
    held = Image.new("RGB", (100, 100), "white")
    held.info["t"] = 0
    samples = [(float(t), held) for t in range(20)] + [_frame(30)]
    chosen, over = video.match_frames([samples[0]], samples, limit=50)
    assert [t for t, _ in chosen] == [0.0, 30.0] and over == []
    run, node = _video_run(_assets())
    _match(run, node, samples, [samples[0]])
    assert run.partial == set() and len(seen) == 4


def test_a_small_mark_arriving_on_a_still_shot_is_not_taken_for_the_same_frame():
    base = Image.new("RGB", (400, 400), "white")
    with_mark = base.copy()
    with_mark.paste((0, 0, 0), (300, 300, 340, 340))  # 1% of the frame
    chosen, _ = video.match_frames([(0.0, base)], [(0.0, base), (1.0, base), (2.0, with_mark)], limit=10)
    assert [t for t, _ in chosen] == [0.0, 2.0]


# --- lettering inside matched artwork -----------------------------------------------------------

def _casing_run(art_sources):
    rules = [rule("TERM-NAME", {"type": "casing", "terms": ["Kitepath"]}), *system_rule_views()]
    run, _ = _run([_asset(1, "Kitepath logo")])
    run.base = make_ctx("x", rules)
    run.rule_by_code = {r.code: r for r in rules}
    run.sources.extend(art_sources)
    return run


def _casing(source_id, quote, at):
    return RawFinding("u", "terminology", "Write Kitepath", "x", 0.9, "deterministic", rule_code="TERM-NAME",
                      quote=quote, span_start=at, span_end=at + len(quote), source=source_id)


def test_casing_is_not_judged_on_lettering_inside_a_matched_logo():
    text = "Learn Python\nKITEPATH\nkitepath"
    src = Source("img:a:ocr", "ocr", text, "ocr:local", regions=[
        (0, 12, (10, 10, 300, 40), None, None),       # headline, outside the logo
        (13, 21, (40, 300, 160, 330), None, None),    # lettering of the logo
        (22, 30, (10, 500, 100, 520), None, None),    # the brand name typed in a sticker
    ])
    run = _casing_run([src])
    run.findings.extend([_casing("img:a:ocr", "KITEPATH", 13), _casing("img:a:ocr", "kitepath", 22)])
    agents._drop_artwork_lettering(run, "img:a:ocr", lambda *_: [(20, 280, 200, 360)])
    assert [f.quote for f in run.findings] == ["kitepath"] and run.findings[0].span_start == 22


def test_only_artwork_on_screen_while_the_line_is_shown_excuses_it():
    src = Source("vid:v:captions", "captions", "KITEPATH", "ocr:frames",
                 regions=[(0, 8, (40, 300, 160, 330), 10.0, 12.0)])
    run = _casing_run([src])
    run.findings.append(_casing("vid:v:captions", "KITEPATH", 0))
    elsewhere = {3.0: [(20, 280, 200, 360)]}  # the logo was matched at 3 s, not while the line was up
    agents._drop_artwork_lettering(run, "vid:v:captions", lambda t0, t1: [
        b for t, boxes in elsewhere.items() if t0 - 1e-6 <= t <= t1 for b in boxes])
    assert len(run.findings) == 1
    on_screen = {11.0: [(20, 280, 200, 360)]}
    agents._drop_artwork_lettering(run, "vid:v:captions", lambda t0, t1: [
        b for t, boxes in on_screen.items() if t0 - 1e-6 <= t <= t1 for b in boxes])
    assert run.findings == []


def test_an_alteration_seen_in_one_frame_only_is_advisory_and_says_so():
    def hit(code):
        return RawFinding("v", "visual", "Logo differs", "Pixels differ.", 0.9, "assets", rule_code=code)

    frames = [(1.0, [(1, hit("VIS-ASSET-ALTERED")), (2, hit("VIS-COMPETITOR-MARK"))]), (2.0, []),
              (4.0, [(1, hit("VIS-ASSET-ALTERED"))]), (5.0, [(1, hit("VIS-ASSET-ALTERED"))])]
    found = {(f.rule_code, tuple(f.locator["time"])): f for f in agents._merge_over_time(frames)}
    brief = found[("VIS-ASSET-ALTERED", (1.0, 1.0))]
    assert brief.level_cap == "advisory" and "one sampled frame" in brief.explanation
    assert found[("VIS-ASSET-ALTERED", (4.0, 5.0))].level_cap is None
    assert found[("VIS-COMPETITOR-MARK", (1.0, 1.0))].level_cap is None
