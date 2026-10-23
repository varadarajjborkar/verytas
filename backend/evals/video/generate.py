"""A realistic marketing-video benchmark for the video review: reels and ads with planted problems.

Each video is a Hyperframes composition (HTML and GSAP, rendered to MP4 in headless Chrome) with the parts
real reels have: a hook, product and feature shots, a price tag, a call to action, an end card, a narrator,
a music bed and, in some, burned-in captions or a subtitle track. Brand artwork comes from the Kitepath
company and the generic kits of the artwork benchmark, so every logo is drawn in code and nobody's trademark
is used.

What is planted, and recorded with times in manifest.json:

- artwork used wrongly (stretched, recoloured, mirrored, the retired version, a competitor's mark), in a
  full grid of appearance length (0.5 s, 1 s, 2 s, 4 s, the whole shot) and placement (starting on a cut,
  or part-way through a shot), at three sizes;
- artwork used correctly, which must raise nothing;
- claims and leaks on screen and in speech, each in its own channel (burned in, spoken, subtitle track);
- clean videos: nothing wrong anywhere.

Narration is macOS `say` (Hyperframes' own Kokoro voice is a large download), the music bed is synthesised
with ffmpeg, and everything is derived from --seed, so a rerun gives the same plan. Nothing is written
inside the repo: --out holds the projects, renders and manifest.

    .venv/bin/python -m evals.video.generate --out /tmp/videobench --tools /tmp/hf-tools
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

HF = "hyperframes@0.8.143"  # pinned: supply-chain policy is versions at least two weeks old
FPS = 30
VARIANTS = ["stretched", "recoloured", "mirrored", "retired", "competitor"]
EXPECT = {
    "stretched": ["VIS-ASSET-DISTORTED"],
    "recoloured": ["VIS-ASSET-ALTERED"],
    "mirrored": ["VIS-ASSET-DISTORTED"],
    "retired": ["VIS-ASSET-RETIRED"],
    "competitor": ["VIS-COMPETITOR-MARK"],
}
ALLOWED_ROLES = {
    "stretched": ["logo", "wordmark", "pack", "icon"],
    "recoloured": ["logo", "wordmark", "pack", "icon"],
    "mirrored": ["logo", "wordmark"],
    "retired": ["retired"],
    "competitor": ["competitor"],
}
DURATIONS = [0.5, 1.0, 2.0, 4.0, "shot"]
SIZES = {"large": 0.56, "medium": 0.34, "small": 0.2}  # share of the shorter side
VOICES = ["Rishi", "Tara", "Aman"]

# Planted claims: the text shown, the sentence said, the rule codes that count as caught.
PLANTS = {
    "promise": {
        "on": ["Guaranteed results in 30 days", "100% placement for every learner", "Guaranteed job after the course"],
        "say": [
            "Join today and get guaranteed results in thirty days.",
            "We offer one hundred percent placement for every learner.",
            "Finish the course and get a guaranteed job.",
        ],
        "phrase": ["guaranteed results", "100% placement", "guaranteed job"],
        "expect": ["CLAIM-PROMISE"],
    },
    "rank": {
        "on": ["No. 1 app in India", "India's best learning app"],
        "say": ["We are the number one app in India.", "This is India's best learning app."],
        "phrase": ["no. 1 app", "india's best"],
        "expect": ["CLAIM-RANK", "CLAIM-UNSUPPORTED"],
    },
    "leak": {
        "on": ["Sneak peek: Project Falcon", "Coming soon: Project Kestrel"],
        "say": ["And watch out for Project Falcon, coming soon.", "Big news is coming with Project Kestrel."],
        "phrase": ["project falcon", "project kestrel"],
        "expect": ["CONF-LEAK"],
    },
    "free": {
        "on": ["100% free for everyone"],
        "say": ["It is completely free for everyone."],
        "phrase": ["100% free", "completely free"],
        "expect": ["LEGAL-FREE"],
    },
    "urgency": {
        "on": ["Hurry! Limited seats left"],
        "say": ["Hurry, limited seats, act now."],
        "phrase": ["hurry", "limited seats"],
        "expect": ["TONE-URGENCY"],
    },
    "rival": {
        "on": ["Why pay for {rival}?"],
        "say": ["Unlike {rival}, we teach with real people."],
        "phrase": ["{rival}"],
        "expect": ["MSG-COMPETITOR"],
    },
}
LINES = {  # clean copy, per brand voice
    "kitepath": {
        "hook": ["Stuck on maths?", "Learn Python in six weeks", "Board exams, sorted", "Your evening class, anywhere"],
        "sub": [
            "Short lessons. Real mentors.",
            "Practice that sticks",
            "Ask a mentor anything",
            "340 courses in 9 languages",
            "Rated 4.7 out of 5 by learners",
            "1,200 verified mentors",
        ],
        "cta": ["Download KiteLearn today", "Try a course free for 7 days"],
        "say": [
            "Learn a little every evening.",
            "Short lessons, real mentors and practice that sticks.",
            "Ask a mentor when you are stuck.",
            "Three hundred and forty courses in nine languages.",
            "Try a course free for seven days.",
        ],
        "end": "Download KiteLearn today.",
        "handle": "@kitepath",
    },
    "kit": {
        "hook": ["Fresh from our kitchen", "New season, new look", "Your daily essential", "Made with care"],
        "sub": ["Pure ingredients, simple goodness", "Now at a store near you", "Fresh every single day"],
        "cta": ["Order online today", "Find a store near you"],
        "say": [
            "Made fresh with simple ingredients.",
            "Now in stores near you.",
            "A small treat for every day.",
            "Pick up the new pack this week.",
        ],
        "end": "Order online today.",
        "handle": "@{name}",
    },
}


# --- brands and artwork --------------------------------------------------------------------------


@dataclass
class Brand:
    key: str
    name: str
    voice: str  # LINES key
    roles: dict[str, dict]  # role -> {name, kind, retired, wordmark, notes, img}
    primary: tuple[int, int, int]
    secondary: tuple[int, int, int]
    rival: str


def _rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA")


def kitepath_brand() -> Brand:
    from verytas.showcase import kitepath

    art = {a["name"]: a for a in kitepath.ARTWORK}

    def role(name: str, retired: bool = False) -> dict:
        a = art[name]
        return {
            "name": name,
            "kind": a["kind"],
            "part": a.get("part", "full"),
            "wordmark": a.get("wordmark"),
            "notes": a.get("notes"),
            "retired": retired,
            "img": _rgba(a["image"]()),
        }

    roles = {
        "logo": role("Kitepath logo"),
        "wordmark": role("Kitepath wordmark"),
        "icon": role("Kitepath app icon"),
        "pack": role("Learning kit box"),
        "retired": role("Kitepath logo 2024", True),
        "competitor": role("SkillSprint"),
        "reversed": role("Kitepath logo, reversed"),
        "mascot": role("Kit"),
    }
    return Brand("kitepath", "Kitepath", "kitepath", roles, kitepath.BLUE, kitepath.ORANGE, "SkillSprint")


def kit_brand(i: int, seed: int, faces: list[str]) -> Brand:
    from evals.assets import generate as g

    kit = g.random_kit(seed * 1000 + i, faces)
    rival = g.random_kit(seed * 1000 + (i + 1) % 5, faces)

    def mk(name, kind, img, **kw):
        return {
            "name": f"{kit.name} {name}",
            "kind": kind,
            "part": kw.get("part", "full"),  # noqa: E731
            "wordmark": kw.get("wordmark"),
            "notes": None,
            "retired": kw.get("retired", False),
            "img": _rgba(img),
        }

    roles = {
        "logo": mk("logo", "logo", g.logo(kit), wordmark=kit.name),
        "wordmark": mk("wordmark", "wordmark", g.wordmark(kit), part="wordmark", wordmark=kit.name),
        "icon": mk("app icon", "icon", g.icon(kit), part="icon"),
        "pack": mk("pack", "packaging", g.pack(kit, kit.seed)),
        "retired": mk("logo (old)", "logo", g.logo(kit, retired=True), retired=True, wordmark=kit.name.upper()),
        "competitor": {
            "name": f"{rival.name} logo",
            "kind": "competitor",
            "part": "full",
            "wordmark": rival.name,
            "notes": "A rival's mark.",
            "retired": False,
            "img": _rgba(g.logo(rival)),
        },
    }
    return Brand(f"k{i}", kit.name, "kit", roles, kit.primary, kit.secondary, rival.name)


def variant_image(img: Image.Image, variant: str) -> Image.Image:
    if variant == "stretched":
        return img.resize((round(img.width * 1.3), img.height), Image.LANCZOS)
    if variant == "mirrored":
        return img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if variant == "recoloured":
        from evals.assets.generate import _recolour

        return _recolour(img, 0.4)
    return img


# --- the plan ------------------------------------------------------------------------------------


@dataclass
class Shot:
    start: int
    end: int
    bg: str = ""
    lines: list[dict] = field(default_factory=list)  # narration to say here


def _combos(rnd: random.Random) -> list[tuple[str, object, str]]:
    out = [(v, d, p) for v in VARIANTS for d in DURATIONS if d != "shot" for p in ("cut", "mid")]
    out += [(v, "shot", "cut") for v in VARIANTS]
    rnd.shuffle(out)
    return out


def recipes(count: int, seed: int) -> list[dict]:
    """The deliberate mix: a grid of 45 misuse combinations spread over most videos, text and speech
    plants over others, and clean videos. Counts scale with --count; the grid is covered first."""
    rnd = random.Random(seed)
    combos = _combos(rnd)
    n_clean = max(2, round(count * 0.17))
    n_text_only = max(2, round(count * 0.17))
    n_asset = count - n_clean - n_text_only
    per = [len(combos) // n_asset + (1 if k < len(combos) % n_asset else 0) for k in range(n_asset)]
    plant_keys = list(PLANTS)
    out: list[dict] = []
    pos = 0
    for k in range(n_asset):
        out.append({"kind": "asset", "assets": combos[pos : pos + per[k]]})
        pos += per[k]
    for _ in range(n_text_only):
        out.append({"kind": "text", "assets": []})
    for _ in range(n_clean):
        out.append({"kind": "clean", "assets": []})
    rnd.shuffle(out)
    # Text and speech plants: every text-only video has one or two, a third of the asset videos one.
    cycle = [(k, ch) for k in plant_keys for ch in ("on", "say")]
    rnd.shuffle(cycle)
    ci = 0
    for r in out:
        r["plants"] = []
        take = 2 if r["kind"] == "text" else (1 if r["kind"] == "asset" and rnd.random() < 0.4 else 0)
        for _ in range(take):
            r["plants"].append(cycle[ci % len(cycle)])
            ci += 1
    # One video carries the claim only in its subtitle track.
    sub_target = next((r for r in out if r["kind"] == "text"), None)
    if sub_target is not None:
        sub_target["plants"] = [("promise", "srt")]
    for i, r in enumerate(out):
        r["orientation"] = "portrait" if i % 7 not in (2, 4, 6) else "landscape"
        r["captions"] = (
            rnd.choice(["burned", "none", "none"]) if not any(c == "say" for _, c in r["plants"]) else "none"
        )
        r["srt"] = "clean" if (r["kind"] == "clean" and i % 2 == 0) else None
        if r["plants"] and r["plants"][0][1] == "srt":
            r["srt"] = "plant"
    return out


def _shot_len(d, place, rnd) -> tuple[int, float]:
    """(shot length, appearance start offset) for an appearance of length `d`."""
    if d == "shot":
        return rnd.randint(3, 5), 0.0
    if place == "cut":
        return max(3, math.ceil(d) + 1), 0.0
    off = round(rnd.uniform(0.7, 1.4), 2)
    return math.ceil(off + d + 0.9), off


def _tts(text: str, voice: str, out: Path, rate: int = 172) -> float:
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "44100", "-ac", "1", str(out)], check=True
    )
    aiff.unlink()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(probe.stdout.strip())


def plan_video(i: int, recipe: dict, brand: Brand, seed: int, work: Path) -> dict:
    rnd = random.Random(seed * 7919 + i)
    portrait = recipe["orientation"] == "portrait"
    W, H = (1080, 1920) if portrait else (1920, 1080)
    vid = f"v{i:02d}"
    voice = rnd.choice(VOICES)
    lines = LINES[brand.voice]
    rival = brand.rival

    pools = {k: rnd.sample(v, len(v)) for k, v in lines.items() if isinstance(v, list)}

    def pick(ch: str) -> str:
        """Copy without repeating itself within a video, until the pool runs out."""
        if not pools[ch]:
            pools[ch] = rnd.sample(lines[ch], len(lines[ch]))
        return pools[ch].pop()

    shots: list[dict] = [{"len": 3, "kind": "hook", "appear": []}]
    # Asset appearances: each planted misuse gets a shot of its own, so truth intervals never overlap.
    items = [{"variant": v, "dur": d, "place": p, "plant": True} for v, d, p in recipe["assets"]]
    if recipe["kind"] != "asset":
        for _ in range(rnd.randint(2, 3) if recipe["kind"] == "clean" else 1):
            items.append(
                {
                    "variant": "correct",
                    "dur": rnd.choice(DURATIONS),
                    "place": rnd.choice(["cut", "mid"]),
                    "plant": False,
                }
            )
    if brand.voice == "kitepath" and i % 2 == 0:
        # The mascot is placed too, so the report can say which mascot moments exist; scoring them needs the
        # vision worker, which a local run lacks, so they count as not applicable.
        items.append(
            {
                "variant": "mascot",
                "dur": rnd.choice([0.5, 1.0, 2.0, 4.0]),
                "place": rnd.choice(["cut", "mid"]),
                "plant": False,
            }
        )
    for it in items:
        if it["variant"] == "mascot":
            it["role"] = "mascot"
        elif it["variant"] == "correct":
            it["role"] = rnd.choice(["logo", "wordmark", "icon", "pack", "logo"])
        else:
            it["role"] = rnd.choice([r for r in ALLOWED_ROLES[it["variant"]] if r in brand.roles])
        it["size"] = rnd.choices(["large", "medium", "small"], [0.55, 0.3, 0.15])[0]
        ln, off = _shot_len(it["dur"], it["place"], rnd)
        shots.append({"len": ln, "kind": "feature", "appear": [{**it, "off": off}]})
    for _ in range(
        max(
            0,
            (2 if recipe["kind"] == "clean" else 0)
            + (1 if recipe["plants"] else 0)
            - sum(1 for s in shots if not s["appear"] and s["kind"] == "feature"),
        )
    ):
        shots.insert(rnd.randint(1, len(shots)), {"len": rnd.randint(3, 5), "kind": "feature", "appear": []})
    if recipe["kind"] == "clean" and rnd.random() < 0.5:
        shots.insert(rnd.randint(1, len(shots)), {"len": rnd.randint(4, 6), "kind": "feature", "appear": []})
    shots.append({"len": 3, "kind": "end", "appear": []})
    while sum(s["len"] for s in shots) > 30:  # no longer than 30 s: drop a shot that has nothing planted in it
        spare = [s for s in shots if s["kind"] == "feature" and not s["appear"]]
        if not spare:
            break
        shots.remove(spare[-1])
    # Rough floor on length: a reel under 8 s is padded with one more feature shot.
    while sum(s["len"] for s in shots) < 8:
        shots.insert(1, {"len": 3, "kind": "feature", "appear": []})

    t = 0
    for s in shots:
        s["start"], s["end"] = t, t + s["len"]
        t = s["end"]
    spots = [s for s in shots if s["kind"] == "feature"]

    # Plants go into feature shots, preferring ones with no misuse in them.
    texts: list[dict] = []
    srt: list[dict] = []
    free_spots = sorted(spots, key=lambda s: (bool(s["appear"]), rnd.random()))
    for n, (key, ch) in enumerate(recipe["plants"]):
        spot = free_spots[n % len(free_spots)]
        pl = PLANTS[key]
        k = rnd.randrange(len(pl["on"]))
        fill = {"rival": rival}
        if ch == "on":
            slot = rnd.choice(["sticker", "sub", "caption"] if recipe["captions"] != "burned" else ["sticker", "sub"])
            texts.append(
                {
                    "slot": slot,
                    "text": pl["on"][k].format(**fill),
                    "t0": spot["start"] + 0.5,
                    "t1": min(spot["end"] - 0.3, spot["start"] + 3.3),
                    "plant": key,
                    "shot": spot,
                }
            )
        elif ch == "say":
            spot.setdefault("say_plant", []).append(
                {
                    "text": pl["say"][k].format(**fill),
                    "plant": key,
                    "phrase": pl["phrase"][k % len(pl["phrase"])].format(**fill),
                }
            )
        else:  # srt
            srt.append({"text": pl["on"][k], "t0": spot["start"] + 0.6, "t1": spot["end"] - 0.4, "plant": key})

    # Narration: one clean line per shot (more in long ones), the speech plants in place of one.
    cursor, narration = 0.0, []
    tts_dir = work / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    for _si, s in enumerate(shots):
        said = list(s.get("say_plant", []))
        if not said:
            text = lines["end"] if s["kind"] == "end" else pick("say")
            if s["kind"] == "hook":
                text = rnd.choice(
                    ["Here is something you will like.", "Meet the new way to do it.", "Ready for a change?"]
                )
            said = [{"text": text, "plant": None, "phrase": None}]
        for sp in said:
            start = max(s["start"] + 0.35, cursor + 0.2)
            wav = tts_dir / f"{vid}_{len(narration)}.wav"
            dur = _tts(sp["text"], voice, wav)
            narration.append(
                {
                    "text": sp["text"],
                    "t0": round(start, 2),
                    "t1": round(start + dur, 2),
                    "wav": str(wav),
                    "plant": sp["plant"],
                    "phrase": sp["phrase"],
                }
            )
            cursor = start + dur
    if cursor + 0.4 > shots[-1]["end"]:  # the voice-over runs long: the end card holds a little longer
        shots[-1]["len"] = math.ceil(cursor + 0.5) - shots[-1]["start"]
        shots[-1]["end"] = shots[-1]["start"] + shots[-1]["len"]
    D = shots[-1]["end"]
    end = shots[-1]
    end["appear"].append(
        {
            "variant": "correct",
            "role": "logo",
            "dur": round(end["len"] - 0.7, 2),
            "place": "mid",
            "plant": False,
            "size": "large",
            "off": 0.6,
            "plate": True,
        }
    )

    # Regular on-screen copy, skipping the slot a planted line uses in that shot.
    for s in shots:
        used = {x["slot"] for x in texts if x["shot"] is s}
        if s["kind"] == "hook":
            texts.append(
                {
                    "slot": "headline",
                    "text": pick("hook"),
                    "t0": s["start"] + 0.2,
                    "t1": s["end"] - 0.2,
                    "plant": None,
                    "shot": s,
                }
            )
        elif s["kind"] == "feature":
            texts.append(
                {
                    "slot": "headline",
                    "text": pick("hook"),
                    "t0": s["start"] + 0.15,
                    "t1": s["end"] - 0.15,
                    "plant": None,
                    "shot": s,
                }
            )
            if "sub" not in used and rnd.random() < 0.8:
                texts.append(
                    {
                        "slot": "sub",
                        "text": pick("sub"),
                        "t0": s["start"] + 0.9,
                        "t1": s["end"] - 0.2,
                        "plant": None,
                        "shot": s,
                    }
                )
        else:
            texts.append(
                {
                    "slot": "headline",
                    "text": rnd.choice(["Join us today", "Start now"]),
                    "t0": s["start"] + 0.2,
                    "t1": D - 0.1,
                    "plant": None,
                    "shot": s,
                }
            )
            texts.append(
                {"slot": "cta", "text": pick("cta"), "t0": s["start"] + 0.7, "t1": D - 0.1, "plant": None, "shot": s}
            )
            texts.append(
                {
                    "slot": "sub",
                    "text": lines["handle"].format(name=brand.name.lower()),
                    "t0": s["start"] + 0.9,
                    "t1": D - 0.1,
                    "plant": None,
                    "shot": s,
                }
            )
    if brand.voice == "kitepath":  # a price tag on the first feature shot, consistent with the registered fact
        feats = [s for s in shots if s["kind"] == "feature"]
        f = next((s for s in feats if not s["appear"]), feats[0])  # clear of any artwork on screen
        texts.append(
            {
                "slot": "price",
                "text": "Annual plan Rs 4,999",
                "t0": f["start"] + 0.4,
                "t1": f["end"] - 0.3,
                "plant": None,
                "shot": f,
            }
        )
    if recipe["captions"] == "burned":
        for nz in narration:
            words = nz["text"].split()
            chunks = [words[j : j + 4] for j in range(0, len(words), 4)]
            span = (nz["t1"] - nz["t0"]) / len(chunks)
            for j, ch in enumerate(chunks):
                texts.append(
                    {
                        "slot": "caption",
                        "text": " ".join(ch),
                        "t0": round(nz["t0"] + j * span, 2),
                        "t1": round(nz["t0"] + (j + 1) * span, 2),
                        "plant": None,
                        "caption": True,
                        "shot": None,
                    }
                )
    if recipe["srt"] == "clean":
        srt = [{"text": nz["text"], "t0": nz["t0"], "t1": nz["t1"], "plant": None} for nz in narration]
    elif recipe["srt"] == "plant":
        srt = [{"text": nz["text"], "t0": nz["t0"], "t1": nz["t1"], "plant": None} for nz in narration] + srt
        srt.sort(key=lambda c: c["t0"])

    return {
        "id": vid,
        "brand": brand.key,
        "orientation": recipe["orientation"],
        "w": W,
        "h": H,
        "duration": D,
        "kind": recipe["kind"],
        "voice": voice,
        "captions": recipe["captions"],
        "subtitle_track": recipe["srt"],
        "shots": shots,
        "texts": texts,
        "narration": narration,
        "srt": srt,
    }


# --- the composition -----------------------------------------------------------------------------


def _gradient_bg(rnd, W, H, base: tuple, style: str, project: Path, name: str) -> str:
    from evals.assets.generate import _background
    from verytas.showcase.art import gradient

    if style == "gradient":
        other = tuple(max(0, min(255, int(c * rnd.uniform(0.35, 1.5)))) for c in base)
        img = gradient((W // 2, H // 2), base, other).resize((W, H), Image.BICUBIC)
    else:
        img = _background(rnd, style, (W // 2, H // 2)).resize((W, H), Image.BICUBIC)
    img.save(project / name, quality=90)
    return name


def compose(video: dict, brand: Brand, project: Path, seed: int) -> str:
    rnd = random.Random(seed * 31 + int(video["id"][1:]))
    W, H, D = video["w"], video["h"], video["duration"]
    m = min(W, H)
    prim = f"rgb({brand.primary[0]},{brand.primary[1]},{brand.primary[2]})"
    sec = f"rgb({brand.secondary[0]},{brand.secondary[1]},{brand.secondary[2]})"
    parts: list[str] = []
    tw: list[str] = []  # GSAP tweens
    n = 0

    def nid(p: str) -> str:
        nonlocal n
        n += 1
        return f"{p}{n}"

    styles = ["gradient", "photo", "busy", "gradient"]
    palette = [brand.primary, brand.secondary, brand.primary, (25, 35, 60)]
    for si, s in enumerate(video["shots"]):
        if s["kind"] == "end":
            s["bg_css"] = f"background:linear-gradient(160deg,{prim},rgb(20,30,60));"
        else:
            bg = _gradient_bg(
                rnd, W, H, palette[(si + 1) % 4], styles[(si + int(video["id"][1:])) % 4], project, f"bg{si}.jpg"
            )
            s["bg_css"] = (
                f"background:linear-gradient(180deg,rgba(0,0,0,.5),rgba(0,0,0,.12) 40%,rgba(0,0,0,.5)),"
                f"url({bg}) center/cover;"
            )
        sid = nid("shot")
        parts.append(
            f'<div id="{sid}" class="clip shot" data-start="{s["start"]}" data-duration="{s["len"]}" '
            f'style="{s["bg_css"]}"></div>'
        )
        tw.append(f'tl.fromTo("#{sid}",{{scale:1.08}},{{scale:1,duration:.5,ease:"power2.out"}},{s["start"]});')
        for _ in range(2):  # drifting shapes, the motion graphics every reel has
            shape = nid("blob")
            size = rnd.randint(int(m * 0.12), int(m * 0.3))
            parts.append(
                f'<div id="{shape}" class="clip blob" data-start="{s["start"]}" data-duration="{s["len"]}" '
                f'style="left:{rnd.randint(0, W - size)}px;top:{rnd.randint(0, H - size)}px;width:{size}px;'
                f"height:{size}px;background:{rnd.choice([prim, sec])};"
                f'opacity:.22;border-radius:{rnd.choice(["50%", "18%"])}"></div>'
            )
            tw.append(
                f'tl.to("#{shape}",{{x:{rnd.randint(-120, 120)},y:{rnd.randint(-160, 160)},'
                f"rotation:{rnd.randint(-40, 40)},"
                f'duration:{s["len"]},ease:"none"}},{s["start"]});'
            )

    # Assets.
    manifest_assets = []
    img_n = 0
    for s in video["shots"]:
        for ap in s["appear"]:
            role = brand.roles[ap["role"]]
            img = variant_image(
                role["img"], "correct" if ap["variant"] in ("correct", "retired", "competitor") else ap["variant"]
            )
            fname = f"art{img_n}.png"
            img_n += 1
            img.save(project / fname)
            ar = img.height / img.width
            w = SIZES[ap["size"]] * m
            if w * ar > 0.28 * H:
                w = 0.28 * H / ar
            h = w * ar
            if ap["size"] == "small":
                x, y = (W - w - 0.14 * W, 0.33 * H) if W < H else (W - w - 0.05 * W, 0.06 * H)
            else:
                x, y = (W - w) / 2, (0.38 if ap.get("plate") else 0.5) * H - h / 2
            dur = s["len"] if ap["dur"] == "shot" else ap["dur"]
            t0 = s["start"] + ap["off"]
            t1 = t0 + dur
            eid = nid("art")
            if ap.get("plate"):  # an end card sets the logo on a white plate, as brand books do
                pid = nid("plate")
                parts.append(
                    f'<div id="{pid}" class="clip" data-start="{t0}" data-duration="{dur}" '
                    f'style="left:{x - w * 0.08:.0f}px;'
                    f"top:{y - h * 0.2:.0f}px;width:{w * 1.16:.0f}px;"
                    f'height:{h * 1.4:.0f}px;background:#fff;border-radius:{m * 0.03:.0f}px"></div>'
                )
                tw.append(f'tl.from("#{pid}",{{opacity:0,duration:.1}},{t0});')
            parts.append(
                f'<img id="{eid}" class="clip art" src="{fname}" alt="" data-start="{t0}" data-duration="{dur}" '
                f'style="left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;height:{h:.0f}px"/>'
            )
            if ap["place"] == "cut" or ap["dur"] == "shot":
                tw.append(f'tl.fromTo("#{eid}",{{scale:.96}},{{scale:1,duration:.3,ease:"power2.out"}},{t0});')
                vis = [t0, t1 - 0.1] if ap["dur"] != "shot" else [t0, t1]
            else:
                tw.append(
                    f'tl.fromTo("#{eid}",{{opacity:0,scale:.9}},{{opacity:1,scale:1,duration:.1,ease:"power2.out"}},{t0});'
                )
                tw.append(f'tl.to("#{eid}",{{opacity:0,duration:.1}},{t1 - 0.1});')
                vis = [t0 + 0.1, t1 - 0.1]
            manifest_assets.append(
                {
                    "role": ap["role"],
                    "asset": role["name"],
                    "variant": ap["variant"],
                    "plant": ap["plant"],
                    "expect": EXPECT.get(ap["variant"]) if ap["plant"] else None,
                    "t0": round(t0, 2),
                    "t1": round(t1, 2),
                    "visible": [round(vis[0], 2), round(vis[1], 2)],
                    "duration_class": ap["dur"],
                    "placement": "cut" if (ap["place"] == "cut" or ap["dur"] == "shot") else "mid",
                    "size": ap["size"],
                    "shot": [s["start"], s["end"]],
                    "applicable": ap["role"] != "mascot",
                }
            )
    video["assets"] = manifest_assets

    # Text.
    slot_css = {
        "headline": f"top:16%;font:900 {m * 0.085:.0f}px 'Arial Black',Impact,sans-serif;color:#fff;text-align:center;",
        "sticker": f"top:29%;font:800 {m * 0.05:.0f}px 'Arial Black',sans-serif;",
        "sub": f"top:66%;font:700 {m * 0.05:.0f}px 'Helvetica Neue',Arial,sans-serif;color:#fff;",
        "caption": f"top:72%;font:700 {m * 0.042:.0f}px 'Helvetica Neue',Arial,sans-serif;",
        "cta": f"top:64%;font:800 {m * 0.052:.0f}px 'Helvetica Neue',Arial,sans-serif;",
        "price": "top:60%;",
    }
    for tx in video["texts"]:
        eid = nid("tx")
        slot = tx["slot"]
        t0, t1 = round(tx["t0"], 2), round(tx["t1"], 2)
        dur = max(0.2, round(t1 - t0, 2))
        width = 0.86 * W if W < H else 0.7 * W
        box = f"left:{(W - width) / 2:.0f}px;width:{width:.0f}px;"
        if slot == "headline":
            words = "".join(f'<span class="w">{wd}</span> ' for wd in tx["text"].split())
            inner = f'<div class="hl" style="{slot_css[slot]}text-shadow:0 4px 18px rgba(0,0,0,.6);">{words}</div>'
            tw.append(
                f'tl.from("#{eid} .w",{{y:{m * 0.04:.0f},opacity:0,scale:.8,duration:.35,stagger:.08,'
                f'ease:"back.out(1.7)"}},{t0});'
            )
        elif slot == "sticker":
            inner = (
                f'<div style="{slot_css[slot]}display:inline-block;background:{sec};color:#fff;padding:.25em .7em;'
                f'border-radius:.4em;transform:rotate(-3deg);box-shadow:0 6px 18px rgba(0,0,0,.4);">{tx["text"]}</div>'
            )
            tw.append(f'tl.from("#{eid}",{{scale:.3,rotation:-20,opacity:0,duration:.35,ease:"back.out(2)"}},{t0});')
        elif slot == "sub":
            inner = f'<div style="{slot_css[slot]}text-shadow:0 3px 14px rgba(0,0,0,.7);">{tx["text"]}</div>'
            tw.append(f'tl.from("#{eid}",{{y:{m * 0.03:.0f},opacity:0,duration:.4,ease:"power2.out"}},{t0});')
        elif slot == "caption":
            inner = (
                f'<div style="{slot_css[slot]}display:inline-block;background:rgba(0,0,0,.62);color:#fff;'
                f'padding:.2em .6em;border-radius:.35em;">{tx["text"]}</div>'
            )
        elif slot == "cta":
            inner = (
                f'<div style="{slot_css[slot]}display:inline-block;background:{sec};color:#fff;padding:.3em 1em;'
                f'border-radius:2em;box-shadow:0 8px 24px rgba(0,0,0,.35);">{tx["text"]}</div>'
            )
            tw.append(f'tl.from("#{eid}",{{scale:.6,opacity:0,duration:.4,ease:"back.out(2)"}},{t0});')
            tw.append(
                f'tl.to("#{eid}",{{scale:1.06,duration:.5,yoyo:true,repeat:{max(1, int(dur / 1.0) - 1)},'
                f'ease:"sine.inOut"}},{t0 + 0.6});'
            )
        else:  # price tag
            d = m * 0.27
            inner = (
                f'<div style="position:absolute;right:{W * 0.06:.0f}px;top:0;width:{d:.0f}px;'
                f"height:{d:.0f}px;border-radius:50%;"
                f"background:#ffd23f;color:#1b1b1b;display:flex;align-items:center;justify-content:center;text-align:center;"
                f"font:900 {m * 0.045:.0f}px Arial,sans-serif;"
                f'transform:rotate(-8deg);box-shadow:0 6px 20px rgba(0,0,0,.4);">{tx["text"]}</div>'
            )
            tw.append(f'tl.from("#{eid}",{{scale:0,rotation:-60,duration:.45,ease:"back.out(2.2)"}},{t0});')
        top = slot_css[slot].split(";")[0] if slot != "price" else "top:42%"
        if tx["shot"] is not None and tx["shot"]["kind"] == "end" and slot == "sub":
            top = "top:57%"  # the handle sits between the logo plate and the button
        parts.append(
            f'<div id="{eid}" class="clip tx" data-start="{t0}" data-duration="{dur}" '
            f'style="{box}{top};text-align:center;">{inner}</div>'
        )
        if slot not in ("caption",) and dur > 0.6:
            tw.append(f'tl.to("#{eid}",{{opacity:0,duration:.12}},{t0 + dur - 0.12});')
        tx["t0"], tx["t1"] = t0, round(t0 + dur, 2)

    audio = f'<audio id="mix" src="mix.m4a" data-start="0" data-duration="{D}" data-volume="1"></audio>'
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width={W}, height={H}"/>
<script src="gsap.min.js"></script>
<style>
 body{{margin:0;background:#000}}
 #root{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:#000}}
 .clip{{position:absolute}}
 .shot{{left:0;top:0;width:{W}px;height:{H}px}}
 .tx{{height:{H * 0.12:.0f}px}}
 .w{{display:inline-block}}
 .art{{object-fit:fill}}
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{D}" data-width="{W}" data-height="{H}">
{chr(10).join(parts)}
{audio}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{paused:true}});
{chr(10).join(tw)}
window.__timelines["main"] = tl;
</script></body></html>"""
    return html


# --- audio ---------------------------------------------------------------------------------------


def mix_audio(video: dict, out: Path) -> None:
    D = video["duration"]
    ins, filt, labels = [], [], []
    for k, nz in enumerate(video["narration"]):
        ins += ["-i", nz["wav"]]
        ms = int(nz["t0"] * 1000)
        filt.append(f"[{k}:a]adelay={ms}|{ms},volume=1.0[n{k}]")
        labels.append(f"[n{k}]")
    f = (
        "0.05*(sin(2*PI*if(lt(mod(t,8),4),220,196)*t)+sin(2*PI*if(lt(mod(t,8),4),277.18,246.94)*t)"
        "+sin(2*PI*if(lt(mod(t,8),4),329.63,293.66)*t))*(0.6+0.4*sin(2*PI*1.5*t))"
    )
    ins += ["-f", "lavfi", "-i", f"aevalsrc='{f}':s=44100:d={D}"]
    k = len(video["narration"])
    filt.append(f"[{k}:a]lowpass=f=1800,afade=t=in:d=1,afade=t=out:st={max(0, D - 1.2)}:d=1.2[bed]")
    labels.append("[bed]")
    filt.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=0:{D},aresample=44100[m]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            *ins,
            "-filter_complex",
            ";".join(filt),
            "-map",
            "[m]",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out),
        ],
        check=True,
    )


def write_srt(cues: list[dict], path: Path) -> None:
    def ts(x: float) -> str:
        return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x % 1 * 1000):03d}"

    path.write_text("".join(f"{i}\n{ts(c['t0'])} --> {ts(c['t1'])}\n{c['text']}\n\n" for i, c in enumerate(cues, 1)))


# --- driver --------------------------------------------------------------------------------------


def _b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def generate(out: Path, tools: Path, count: int, seed: int, only: set[str] | None, render: bool, workers: str) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    out.mkdir(parents=True, exist_ok=True)
    from evals.assets.generate import fonts

    faces = fonts()
    brands = [kitepath_brand(), *(kit_brand(i, seed, faces) for i in range(5))]
    lib_dir = out / "library"
    for b in brands:
        (lib_dir / b.key).mkdir(parents=True, exist_ok=True)
        for role, a in b.roles.items():
            a["file"] = f"library/{b.key}/{role}.png"
            a["img"].save(out / a["file"])
    # Kitepath carries a third of the videos (it has the facts and the richest artwork), the kits the rest.
    order = [brands[0], brands[1], brands[0], brands[2], brands[0], brands[3], brands[4], brands[5]]
    plans = recipes(count, seed)
    manifest = {
        "seed": seed,
        "hyperframes": HF,
        "fps": FPS,
        "brands": {
            b.key: {
                "name": b.name,
                "rival": b.rival,
                "assets": {r: {k: v for k, v in a.items() if k != "img"} for r, a in b.roles.items()},
            }
            for b in brands
        },
        "videos": [],
    }
    env = {**os.environ, "HYPERFRAMES_NO_UPDATE_CHECK": "1", "DO_NOT_TRACK": "1", "HYPERFRAMES_TELEMETRY": "0"}
    for i, recipe in enumerate(plans):
        vid = f"v{i:02d}"
        if only and vid not in only:
            continue
        brand = order[i % len(order)]
        file = out / "videos" / f"{vid}.mp4"
        cached = out / "plans" / f"{vid}.json"
        # A finished clip has its ground truth saved beside it, so a rerun after a kill or a wipe of the
        # scratch space re-does only what is missing (planning needs the narration, which is the slow part).
        # A clip without its plan was cut off mid-write and is rendered again.
        if render and file.exists() and cached.exists():
            manifest["videos"].append(json.loads(cached.read_text()))
            print(f"{vid} kept", flush=True)
            continue
        if render:
            file.unlink(missing_ok=True)
        work = out / "work" / vid
        project = out / "projects" / vid
        for d in (work, project):
            d.mkdir(parents=True, exist_ok=True)
        video = plan_video(i, recipe, brand, seed, work)
        shutil.copy(tools / "gsap.min.js", project / "gsap.min.js")
        html = compose(video, brand, project, seed)
        (project / "index.html").write_text(html)
        mix_audio(video, project / "mix.m4a")
        file.parent.mkdir(exist_ok=True)
        render_s = None
        if render and not file.exists():
            t = time.perf_counter()
            raw = out / "videos" / f"{vid}.raw.mp4"
            subprocess.run(
                [
                    "npx",
                    "-y",
                    HF,
                    "render",
                    str(project),
                    "--output",
                    str(raw),
                    "--fps",
                    str(FPS),
                    "--quality",
                    "standard",
                    "--workers",
                    workers,
                    "--quiet",
                ],
                cwd=tools,
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            render_s = round(time.perf_counter() - t, 1)
            if video["subtitle_track"]:
                srt = work / "cues.srt"
                write_srt(video["srt"], srt)
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-loglevel",
                        "error",
                        "-i",
                        str(raw),
                        "-i",
                        str(srt),
                        "-map",
                        "0",
                        "-map",
                        "1",
                        "-c",
                        "copy",
                        "-c:s",
                        "mov_text",
                        "-metadata:s:s:0",
                        "language=eng",
                        str(file),
                    ],
                    check=True,
                )
                raw.unlink()
            else:
                raw.replace(file)
        entry = _entry(video, file, render_s)
        manifest["videos"].append(entry)
        if render:
            cached.parent.mkdir(exist_ok=True)
            cached.write_text(json.dumps(entry, indent=1))
        print(
            f"{vid} {brand.key} {video['orientation']} {video['duration']}s "
            f"assets={len(video['assets'])} plants={sum(1 for a in video['assets'] if a['plant'])}"
            f"+{sum(1 for t in video['texts'] if t['plant'])}t+{sum(1 for n in video['narration'] if n['plant'])}s"
            f" render={render_s}",
            flush=True,
        )
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    if render:  # a partial run (--only) still leaves the manifest covering every finished clip
        manifest["videos"] = [json.loads(f.read_text()) for f in sorted((out / "plans").glob("v*.json"))]
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def _entry(v: dict, file: Path, render_s: float | None) -> dict:
    """The ground truth for one video, without the working fields."""
    from_plants = lambda k: PLANTS[k]["expect"]  # noqa: E731
    return {
        "id": v["id"],
        "file": f"videos/{file.name}",
        "brand": v["brand"],
        "orientation": v["orientation"],
        "channel": "instagram" if v["orientation"] == "portrait" else "youtube",
        "width": v["w"],
        "height": v["h"],
        "duration": v["duration"],
        "fps": FPS,
        "kind": v["kind"],
        "clean": v["kind"] == "clean",
        "captions": v["captions"],
        "subtitle_track": v["subtitle_track"],
        "voice": v["voice"],
        "render_seconds": render_s,
        "shots": [{"start": s["start"], "end": s["end"], "kind": s["kind"]} for s in v["shots"]],
        "assets": v["assets"],
        "texts": [
            {
                "text": t["text"],
                "slot": t["slot"],
                "t0": t["t0"],
                "t1": t["t1"],
                "caption": bool(t.get("caption")),
                "plant": t["plant"],
                "expect": from_plants(t["plant"]) if t["plant"] else None,
                "phrase": next((p.split("{")[0] for p in PLANTS[t["plant"]]["phrase"]), None) if t["plant"] else None,
            }
            for t in v["texts"]
        ],
        "speech": [
            {
                "text": n["text"],
                "t0": n["t0"],
                "t1": n["t1"],
                "plant": n["plant"],
                "expect": from_plants(n["plant"]) if n["plant"] else None,
                "phrase": n["phrase"],
            }
            for n in v["narration"]
        ],
        "subtitles": [
            {
                "text": c["text"],
                "t0": c["t0"],
                "t1": c["t1"],
                "plant": c["plant"],
                "expect": from_plants(c["plant"]) if c["plant"] else None,
            }
            for c in v["srt"]
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tools", type=Path, required=True, help="the npm project with hyperframes and gsap installed")
    ap.add_argument("--count", type=int, default=36)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", help="comma-separated video ids, e.g. v00,v05")
    ap.add_argument("--no-render", action="store_true", help="plan, compose and mix only")
    ap.add_argument("--workers", default="2")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    m = generate(args.out, args.tools, args.count, args.seed, only, not args.no_render, args.workers)
    print(f"{len(m['videos'])} videos in {args.out}")


if __name__ == "__main__":
    main()
