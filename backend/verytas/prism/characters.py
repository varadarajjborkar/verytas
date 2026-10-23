"""Brand mascots an AI has redrawn: found by the vision worker, compared with their artwork.

Pixel matching recognises copies of the artwork; this step covers characters drawn anew (new pose, new
style) that may carry a wrong colour or an extra limb. The worker finds each character, measures its
likeness to every mascot in the library and lists how it differs from the closest one. This module
decides what that means.

Who a character is, from the mascot benchmark (evals/mascots, 425 scenes): likeness alone separates a
brand's mascot from other cartoon characters only at a high bar (0.90 accepts 0.4% of other mascots but
only a third of genuine ones). The creator's brief lowers the bar: a mascot the brief names is taken at
0.83, where most genuine renderings pass. Below that, down to 0.70, the character the named mascot
clearly leads for is taken as probably it, and its differences are reported as "if this is Kit". Only
when no character qualifies is the mascot reported as possibly redrawn beyond recognition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from PIL import Image

from verytas.checks.base import RawFinding
from verytas.vision.client import Character, VisionUnavailable

# Likeness (DINOv2 cosine) at which a character is the mascot on looks alone, and when the brief names it.
SURE = 0.90
NAMED = 0.83
# Below NAMED, a character the brief's mascot is the clear favourite for (this far ahead of any other
# registered mascot) is taken as probably that mascot: a heavy AI redraw lands here. Its differences are
# reported framed as "if this is Kit", at lower confidence, instead of a bare "redrawn beyond recognition"
# that tells the creator nothing to fix. The worker compares from vision.chain.COMPARE_FROM, which is
# at or below PROBABLE, so the differences exist.
PROBABLE = 0.70
PROBABLE_LEAD = 0.03
# A video's frames sent for characters: enough to see a morph within a shot, few enough for a CPU.
MAX_VIDEO_FRAMES = 12
# First words of a mascot's name that don't name it on their own ("Blue the whale" is not named by "blue").
_NOT_A_NAME = {"the", "a", "an", "our", "my", "little", "big", "mr", "mrs", "miss", "captain", "doctor", "dr",
               "blue", "red", "green", "yellow", "orange", "purple", "pink", "black", "white", "brown", "grey",
               "gray", "golden", "silver", "happy", "super", "baby", "lucky", "mini"}


@dataclass
class Sighting:
    """One frame's view of one mascot."""

    time: float | None
    character: Character


def pick_frames(keys: list[tuple[float, Image.Image]], samples: list[tuple[float, Image.Image]],
                limit: int = MAX_VIDEO_FRAMES) -> list[tuple[float, Image.Image]]:
    """Frames to look for mascots in, spread over the whole video: up to half are shot starts, the rest
    evenly spaced samples (a mascot can morph within a shot), in time order."""
    def spread(items, n):
        if len(items) <= n:
            return list(items)
        return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)] if n > 1 else [items[0]]

    picked = dict(spread(keys, max(1, limit // 2)))
    # The remaining slots spread over the whole length, first sample to last; a sample that is also a
    # shot start doesn't use up a slot.
    keyed, n = dict(picked), limit - len(picked)
    while n <= len(samples):
        picked = keyed | dict(spread(samples, n))
        if len(picked) >= limit:
            break
        n += 1
    out = sorted(picked.items(), key=lambda p: p[0])
    while len(out) > limit:
        # Over by a frame or two: drop samples from the middle, keeping both ends and every shot start.
        middle = [i for i in range(1, len(out) - 1) if out[i][0] not in keyed]
        if not middle:
            break
        out.pop(middle[len(middle) // 2])
    return out[:limit]


def named_in_brief(name: str, brief: str) -> bool:
    """Whether the brief names the mascot: its full name, or its first word written as a name ("Kit
    waves", not "starter kit")."""
    if not brief or not name.strip():
        return False
    if re.search(rf"\b{re.escape(name.strip())}\b", brief, re.IGNORECASE):
        return True
    first = name.split()[0]
    if len(first) < 3 or not first[0].isupper() or first.casefold() in _NOT_A_NAME:
        return False
    return re.search(rf"\b{re.escape(first)}\b", brief) is not None


def _who(ch: Character, mascots: dict[str, Any], named: set[str]) -> str | None:
    """The mascot id this character is, or None when it is nobody the brand registered."""
    ranked = sorted(ch.likeness.items(), key=lambda kv: -kv[1])
    for ref, score in ranked:
        if ref in mascots and (score >= SURE or (ref in named and score >= NAMED)):
            return ref
    return None


def _runs(sightings: list[Sighting], order: list[float | None]) -> list[list[Sighting]]:
    """Consecutive frames (in `order`) where the mascot was seen with differences, as separate runs."""
    at = {s.time: s for s in sightings}
    runs: list[list[Sighting]] = []
    current: list[Sighting] = []
    for t in order:
        if t in at:
            current.append(at[t])
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


async def characters_agent(run: Any, node: Any, frames: list[tuple[float | None, Image.Image]], media_id: str,
                           locator: dict[str, Any], skip: set[int]) -> None:
    """Check the brand's mascots in an image (one frame, time None) or a video's frames.

    `skip` holds assets pixel matching already found: a copy of the artwork is judged by the pixels."""
    client = run.characters
    mascots = {str(a.id): a for a in run.assets if a.kind == "mascot" and a.official and a.id not in skip}
    if not mascots:
        node.note = "no mascot artwork to compare with"
        return
    if client is None:
        # Not a pass: the brand has mascots and nothing looked for redrawn ones, so visual is partial.
        node.note = "the vision worker isn't configured: redrawn mascots were not looked for"
        run.notes.append(f"{media_id}: redrawn mascots were not looked for (no vision worker)")
        run.partial.add("visual")
        return
    try:
        found = await client.characters([img for _, img in frames], [(i, a.image) for i, a in mascots.items()])
    except VisionUnavailable as exc:
        node.status, node.note = "not_checked", str(exc)
        run.notes.append(f"{media_id}: redrawn mascots were not looked for ({exc})")
        run.partial.add("visual")
        return
    named = {i for i, a in mascots.items() if named_in_brief(a.name, run.brief)}
    seen: dict[str, list[Sighting]] = {}
    for (t, _), characters in zip(frames, found, strict=True):
        for ch in characters:
            who = _who(ch, mascots, named)
            if who is not None:
                seen.setdefault(who, []).append(Sighting(t, ch))
    # Restricted artwork is named only by number: anyone who can read this review sees the agent tree.
    node.detail = {"frames": len(frames), "characters": sum(len(c) for c in found),
                   "mascots_seen": sorted(f"asset #{i}" if mascots[i].restricted else mascots[i].name
                                          for i in seen)}

    altered = run.rule_by_code.get("VIS-ASSET-ALTERED")
    leak = run.rule_by_code.get("CONF-LEAK")
    order = [t for t, _ in frames]
    out: list[RawFinding] = []
    for ref, sightings in seen.items():
        asset = mascots[ref]
        if asset.restricted:
            # Unreleased artwork appearing at all is the leak; whether it is drawn well doesn't matter.
            if leak:
                s = sightings[0]
                out.append(RawFinding(
                    unit_id=f"{media_id}:character{ref}", category=leak.category, title="Unreleased brand artwork",
                    explanation=f"A character here resembles official artwork restricted above this content's "
                                f"tier (asset #{asset.id}; an approver can see which). {leak.text}",
                    confidence=0.85, checker="characters", rule_code=leak.code, source=media_id,
                    locator=_where(locator, media_id, [s])))
            continue
        compared = [s for s in sightings if ref in s.character.differences]
        flagged = [s for s in compared if s.character.differences[ref]]
        if not compared:
            # Identified, but every cut-out was too small to compare: say neither faithful nor altered.
            run.notes.append(f"{media_id}: {asset.name} appears but was too small to compare with its artwork")
            continue
        if not flagged:
            if all(ref in s.character.uncounted for s in compared):
                run.glance.append(f"{asset.name} appears, in its official colours (too small here to check "
                                  "its parts)")
            else:
                run.glance.append(f"{asset.name} appears, in its official colours and parts")
            continue
        if altered is None:
            continue
        for part in _runs(flagged, order):
            first = part[0].character
            texts = list(dict.fromkeys(d["text"] for s in part for d in s.character.differences[ref]))[:4]
            when = _when(part)
            out.append(RawFinding(
                unit_id=f"{media_id}:character{ref}@{part[0].time if part[0].time is not None else 0}",
                category=altered.category, title=f"{asset.name} is drawn differently from its artwork",
                explanation=f"{altered.text} Compared with the official {asset.name}{when}: {'; '.join(texts)}.",
                confidence=0.85 if first.best()[1] >= SURE else 0.75, checker="characters",
                rule_code=altered.code, source=media_id, locator=_where(locator, media_id, part)))

    for ref in named - set(seen):
        asset = mascots[ref]
        if asset.restricted or altered is None or not any(found):
            continue
        likely = _probable(ref, mascots, frames, found)
        if likely is not None:
            t, ch = likely
            texts = [d["text"] for d in ch.differences.get(ref, [])][:4]
            if texts:
                part = [Sighting(t, ch)]
                out.append(RawFinding(
                    unit_id=f"{media_id}:character{ref}:probable", category=altered.category,
                    title=f"{asset.name} looks redrawn",
                    explanation=f"The brief says {asset.name} appears. The closest character here is only "
                                f"{ch.likeness[ref]:.0%} alike, so it may be a heavy redraw; if it is "
                                f"{asset.name}, it differs from the official artwork{_when(part)}: "
                                f"{'; '.join(texts)}. {altered.text}",
                    confidence=0.6, checker="characters", rule_code=altered.code, source=media_id,
                    locator=_where(locator, media_id, part)))
                continue
        out.append(RawFinding(
            unit_id=f"{media_id}:character{ref}:unrecognised", category=altered.category,
            title=f"{asset.name} may be redrawn beyond recognition",
            explanation=f"The brief says {asset.name} appears, but no character here looks enough like the "
                        f"official artwork to be sure it is {asset.name}. {altered.text}",
            confidence=0.55, checker="characters", rule_code=altered.code, source=media_id,
            locator={**locator, "image": media_id}))
    run.add(node, "media", out)


def _probable(ref: str, mascots: dict[str, Any], frames: list[tuple[float | None, Image.Image]],
              found: list[list[Character]]) -> tuple[float | None, Character] | None:
    """The character most like `ref` where `ref` clearly leads every other registered mascot, or None."""
    best: tuple[float | None, Character] | None = None
    for (t, _), characters in zip(frames, found, strict=True):
        for ch in characters:
            score = ch.likeness.get(ref, 0.0)
            rival = max((v for k, v in ch.likeness.items() if k != ref and k in mascots), default=0.0)
            if score >= PROBABLE and score - rival >= PROBABLE_LEAD and (
                    best is None or score > best[1].likeness[ref]):
                best = (t, ch)
    return best


def _when(part: list[Sighting]) -> str:
    if part[0].time is None:
        return ""
    a, b = part[0].time, part[-1].time
    return f" at {a:.1f} s" if a == b else f" from {a:.1f} s to {b:.1f} s"


def _where(locator: dict[str, Any], media_id: str, part: list[Sighting]) -> dict[str, Any]:
    where = {**locator, "image": media_id, "box": part[0].character.box}
    if part[0].time is not None:
        where["time"] = [part[0].time, part[-1].time]
    return where
