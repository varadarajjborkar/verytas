"""Redrawn mascots (prism/characters.py), with the vision worker replaced by fixed answers so the
decisions are tested exactly and offline."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from PIL import Image

from verytas.prism.characters import NAMED, SURE, characters_agent, named_in_brief
from verytas.vision.client import Character, VisionUnavailable

RULES = {code: SimpleNamespace(code=code, category=cat, text=f"[{code}]")
         for code, cat in (("VIS-ASSET-ALTERED", "visual"), ("CONF-LEAK", "legal"))}
EXTRA_EYE = [{"kind": "parts", "text": "3 black #151722 shapes where the artwork has 2"}]


class FakeClient:
    def __init__(self, per_frame=None, fail=False):
        self.per_frame, self.fail, self.calls = per_frame or [], fail, 0

    async def characters(self, scenes, references):
        self.calls += 1
        if self.fail:
            raise VisionUnavailable("vision worker unreachable (ConnectError)")
        return self.per_frame[:len(scenes)]


def _asset(id_, name, restricted=False, kind="mascot"):
    return SimpleNamespace(id=id_, name=name, kind=kind, restricted=restricted, image=Image.new("RGBA", (8, 8)))


def _run(client, assets, brief=""):
    found = []
    run = SimpleNamespace(characters=client, assets=assets, brief=brief, rule_by_code=RULES, notes=[], glance=[],
                          partial=set(), findings=found)
    run.add = lambda node, worker, out: found.extend(out)
    return run


def _ch(likeness, differences=(), compared=("1",)):
    return Character([10, 10, 50, 60], 0.9, likeness, {ref: list(differences) for ref in compared})


def _check(run, frames, skip=frozenset()):
    node = SimpleNamespace(note=None, status="ok", detail={})
    asyncio.run(characters_agent(run, node, frames, "img:ad", {"image": "ad"}, set(skip)))
    return node


IMAGE = [(None, Image.new("RGB", (64, 64)))]


def test_a_mascot_redrawn_with_an_extra_eye_is_altered_with_its_box():
    run = _run(FakeClient([[_ch({"1": SURE + 0.02}, EXTRA_EYE)]]), [_asset(1, "Kit")])
    _check(run, IMAGE)
    [f] = run.findings
    assert f.rule_code == "VIS-ASSET-ALTERED" and f.title == "Kit is drawn differently from its artwork"
    assert "3 black #151722 shapes" in f.explanation and f.locator["box"] == [10, 10, 50, 60]


def test_a_faithful_mascot_is_noted_at_a_glance_not_flagged():
    run = _run(FakeClient([[_ch({"1": SURE + 0.02})]]), [_asset(1, "Kit")])
    _check(run, IMAGE)
    assert run.findings == [] and run.glance == ["Kit appears, in its official colours and parts"]


def test_moderate_likeness_counts_only_when_the_brief_names_the_mascot():
    answer = [[_ch({"1": NAMED + 0.01}, EXTRA_EYE)]]
    unnamed = _run(FakeClient(answer), [_asset(1, "Kit")], brief="A fox waves at the camera")
    _check(unnamed, IMAGE)
    assert unnamed.findings == []
    named = _run(FakeClient(answer), [_asset(1, "Kit")], brief="Kit waves at the camera")
    _check(named, IMAGE)
    assert [f.rule_code for f in named.findings] == ["VIS-ASSET-ALTERED"]


def test_a_named_mascot_nobody_resembles_is_a_weak_warning():
    run = _run(FakeClient([[_ch({"1": 0.6})]]), [_asset(1, "Kit")], brief="Kit waves")
    _check(run, IMAGE)
    [f] = run.findings
    assert "beyond recognition" in f.title and f.confidence < 0.6


def test_a_restricted_mascot_is_a_leak_whatever_its_quality():
    run = _run(FakeClient([[_ch({"1": SURE + 0.03})]]), [_asset(1, "Nova", restricted=True)])
    _check(run, IMAGE)
    [f] = run.findings
    assert f.rule_code == "CONF-LEAK" and "Nova" not in f.explanation + f.title


def test_video_frames_with_the_same_defect_merge_into_time_ranges():
    ok, bad = [_ch({"1": 0.95})], [_ch({"1": 0.95}, EXTRA_EYE)]
    frames = [(float(t), Image.new("RGB", (64, 64))) for t in range(6)]
    run = _run(FakeClient([ok, bad, bad, ok, bad, ok]), [_asset(1, "Kit")])
    _check(run, frames)
    assert [f.locator["time"] for f in run.findings] == [[1.0, 2.0], [4.0, 4.0]]
    assert "from 1.0 s to 2.0 s" in run.findings[0].explanation


def test_an_unreachable_worker_leaves_visual_partial_not_passed():
    run = _run(FakeClient(fail=True), [_asset(1, "Kit")])
    node = _check(run, IMAGE)
    assert node.status == "not_checked" and "visual" in run.partial and run.findings == []


def test_no_worker_or_no_mascots_skips_without_calling():
    client = FakeClient([[_ch({"1": 0.95}, EXTRA_EYE)]])
    unconfigured = _run(None, [_asset(1, "Kit")])
    assert _check(unconfigured, IMAGE).note.startswith("the vision worker isn't configured")
    assert "visual" in unconfigured.partial  # not looked for is never a pass
    assert _check(_run(client, [_asset(1, "Logo", kind="logo")]), IMAGE).note == "no mascot artwork to compare with"
    # A copy pixel matching already found is judged by the pixels.
    assert _check(_run(client, [_asset(1, "Kit")]), IMAGE, skip={1}).note == "no mascot artwork to compare with"
    assert client.calls == 0


def test_brief_names_need_a_capitalised_name_or_the_full_name():
    assert named_in_brief("Kit the fox", "Kit waves at 0:03")
    assert named_in_brief("Kit the fox", "here kit the fox dances")
    assert not named_in_brief("Kit the fox", "grab the starter kit today")
    assert not named_in_brief("Kit", "")
    assert not named_in_brief("Blue the whale", "Blue skies and a sale")


def test_a_restricted_mascot_is_never_named_in_the_agent_tree():
    run = _run(FakeClient([[_ch({"1": SURE + 0.03})]]), [_asset(1, "Nova", restricted=True)])
    node = _check(run, IMAGE)
    assert node.detail["mascots_seen"] == ["asset #1"]


def test_the_identified_mascots_own_comparison_is_used():
    # Kit (1) is named in the brief and passes the named bar; Pip (2) looks slightly more alike. The
    # finding must come from the comparison with Kit, and a mascot never compared is never "faithful".
    ch = Character([0, 0, 9, 9], 0.9, {"1": NAMED + 0.01, "2": NAMED + 0.04},
                   {"1": EXTRA_EYE, "2": []})
    run = _run(FakeClient([[ch]]), [_asset(1, "Kit"), _asset(2, "Pip")], brief="Kit waves")
    _check(run, IMAGE)
    assert [f.title for f in run.findings] == ["Kit is drawn differently from its artwork"]
    uncompared = _run(FakeClient([[_ch({"1": 0.95}, compared=())]]), [_asset(1, "Kit")])
    _check(uncompared, IMAGE)
    assert uncompared.findings == [] and uncompared.glance == [] and "too small to compare" in uncompared.notes[0]


def test_video_frames_cover_the_whole_video_not_just_its_start():
    from verytas.prism.characters import MAX_VIDEO_FRAMES, pick_frames

    img = Image.new("RGB", (4, 4))
    samples = [(float(t), img) for t in range(300)]  # a five-minute video sampled every second
    keys = [(float(t), img) for t in range(0, 40, 2)]  # twenty quick cuts early on
    picked = [t for t, _ in pick_frames(keys, samples)]
    assert len(picked) == MAX_VIDEO_FRAMES and picked == sorted(picked)
    assert picked[-1] >= 290 and sum(t < 40 for t in picked) <= MAX_VIDEO_FRAMES // 2 + 1


def test_a_mascot_too_small_to_count_parts_is_not_called_complete():
    ch = Character([0, 0, 9, 9], 0.9, {"1": 0.95}, {"1": []}, uncounted=["1"])
    run = _run(FakeClient([[ch]]), [_asset(1, "Kit")])
    _check(run, IMAGE)
    assert run.glance == ["Kit appears, in its official colours (too small here to check its parts)"]
