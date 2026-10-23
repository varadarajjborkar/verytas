"""Run the video benchmark through the production review path (offline models) and score it.

For each video: upload it with POST /media, submit it with POST /contents?wait=true (a brief, as production
requires), and read the review. The workspace is built the way a brand admin would: rules, facts, confidential
terms and every registered artwork (current, retired, competitor). Nothing leaves the machine: LLM mode is
offline, speech is faster-whisper and text is RapidOCR, all local.

The vision worker (the mascot chain) is not available locally, so mascot appearances are in the data but count
as not applicable, not as misses.

    .venv/bin/python -m evals.video.run --data /tmp/videobench/data --out evals/results/video.jsonl
    .venv/bin/python -m evals.video.run --data ... --resume --limit 5
    .venv/bin/python -m evals.video.run --data ... --report

Besides the review, each planted artwork appearance is probed: the production pixel path is run on the frames
a denser sampler would have read (every 1 s sample inside the appearance, and the middle of it). That separates
"the matcher cannot tell" from "the frame was never looked at", which is the keyframe-only question.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # models come from the local cache; a run must never need the network

SOURCE_OF = {"on_screen": ":captions", "speech": ":speech", "subtitles": ":subtitles"}
# Notes that are true of any narrated, vertical reel and say nothing about the planted problems: no caption file,
# reading grade of a spoken script, and the platform layout checks (safe zone, grid crop).
NOTE_CODES = {"A11Y-CAPTIONS", "A11Y-READ", "PRES-CROP", "PRES-SAFEZONE", "PRES-FOLD"}
TIME_TOL = {"visual": 0.5, "on_screen": 1.0, "speech": 1.5, "subtitles": 1.0}
# Rules a workspace needs for the planted claims; the rest of the checks are the built-in system rules.
RULE_CODES = ["CLAIM-PROMISE", "CLAIM-RANK", "LEGAL-FREE", "TONE-URGENCY", "TERM-NAME"]
KITE_FACTS = ("courses", "rating", "mentors", "languages", "annual plan price", "support days")


# --- the workspace --------------------------------------------------------------------------------


def _b64(path: Path) -> str:
    import base64

    return base64.b64encode(path.read_bytes()).decode()


def _setup(client, manifest: dict, data: Path, brand_key: str, first: bool, db_state: dict) -> dict:
    """One workspace per brand: admin, a creator, the rules, facts, terms and the artwork library."""
    from verytas.showcase import kitepath

    brand = manifest["brands"][brand_key]
    name = brand["name"]
    slug = brand_key
    if first:
        boot = client.post(
            "/bootstrap", json={"workspace_name": name, "admin_email": f"admin@{slug}.example", "admin_name": "Admin"}
        )
        boot.raise_for_status()
        admin = boot.json()["token"]
    else:
        from verytas.services.workspace import create_workspace

        db = client.app.state.db

        async def make() -> str:
            async with db.sessionmaker() as session:
                _, _, token = await create_workspace(
                    session, name=name, admin_email=f"admin@{slug}.example", admin_name="Admin"
                )
                await session.commit()
                return token

        admin = client.portal.call(make)
    h = {"Authorization": f"Bearer {admin}"}
    r = client.post(
        "/users",
        headers=h,
        json={"email": f"creator@{slug}.example", "name": "Creator", "role": "creator", "clearance": "internal"},
    )
    r.raise_for_status()
    creator = {"Authorization": f"Bearer {r.json()['token']}"}

    def post(path: str, body: dict) -> dict:
        res = client.post(path, headers=h, json=body)
        res.raise_for_status()
        return res.json()

    by_code = {r["code"]: r for r in kitepath.RULES}
    for code in RULE_CODES:
        if code == "TERM-NAME" and brand_key != "kitepath":
            continue
        rule = dict(by_code[code])
        rid = post("/rules", {"tier": "public", **rule})["id"]
        client.patch(f"/rules/{rid}", headers=h, json={"status": "active"}).raise_for_status()
    rival = brand["rival"]
    rid = post(
        "/rules",
        {"tier": "public", **{**by_code["MSG-COMPETITOR"], "pattern": {"type": "banned_terms", "terms": [rival]}}},
    )["id"]
    client.patch(f"/rules/{rid}", headers=h, json={"status": "active"}).raise_for_status()
    for term in ("Project Falcon", "Project Kestrel"):
        post("/confidential-terms", {"term": term, "note": "Codename, not public"})
    if brand_key == "kitepath":
        today = date.today()
        for f in kitepath.FACTS:
            if f.get("supersedes") is None and f.get("key", "").endswith("_old"):
                continue
            if f["subject"] not in KITE_FACTS or f["from"] > 0 or f.get("to", 1) is not None and f.get("to", 1) < 0:
                continue
            body = {k: v for k, v in f.items() if k not in ("key", "supersedes", "from", "to")}
            body["valid_from"] = str(today + timedelta(days=f["from"]))
            post("/facts", {"tier": "public", **body})
    for role, a in brand["assets"].items():
        if role == "reversed" and brand_key != "kitepath":
            continue
        post(
            "/brand-assets",
            {
                "name": a["name"],
                "kind": a["kind"],
                "part": a["part"],
                "retired": a["retired"],
                "wordmark": a["wordmark"],
                "notes": a["notes"],
                "data_base64": _b64(data / a["file"]),
            },
        )
    return {"creator": creator, "admin": h}


# --- one review -----------------------------------------------------------------------------------


def _codes(finding: dict) -> list[str]:
    return [c["label"].split(" ")[0] for c in finding["citations"] if c["kind"] == "rule"]


def _slim(finding: dict) -> dict:
    loc = finding.get("locator") or {}
    return {
        "codes": _codes(finding),
        "title": finding["title"][:140],
        "explanation": finding["explanation"][:300],
        "level": finding["level"],
        "source": finding["source"],
        "time": loc.get("time"),
        "quote": (finding.get("quote") or "")[:120],
        "checker": finding["checker"],
    }


def review_video(client, ws: dict, data: Path, v: dict) -> dict:
    t = time.perf_counter()
    raw = (data / v["file"]).read_bytes()
    up = client.post("/media", headers=ws["creator"], files={"file": (f"{v['id']}.mp4", raw, "video/mp4")})
    up.raise_for_status()
    brief = (
        "A short marketing reel for the brand: a hook, two or three feature shots with the logo and the product, "
        "a price or offer, a call to action and an end card. A narrator speaks over a music bed."
    )
    res = client.post(
        "/contents?wait=true",
        headers=ws["creator"],
        json={
            "title": v["id"],
            "channel": v.get("channel", "instagram"),
            "tier": "public",
            "body": "New reel, watch to the end.",
            "attachments": {"videos": [{"id": v["id"], "blob_id": up.json()["id"]}]},
            "creator_notes": {"brief": brief},
        },
    )
    res.raise_for_status()
    review = client.get(f"/reviews/{res.json()['review_id']}", headers=ws["creator"]).json()
    seconds = round(time.perf_counter() - t, 2)
    agents = review["coverage"].get("agents", [])
    node = next((a for a in agents if a["role"] == "video"), {})
    kf = next((a for a in agents if a["role"] == "keyframes"), {})
    return {
        "review_status": review["status"],
        "error": review.get("error"),
        "seconds": seconds,
        "findings": [_slim(f) for f in review["findings"]],
        "keyframes": (kf.get("detail") or {}).get("keyframes", []),
        "frames_sampled": (node.get("detail") or {}).get("frames_sampled"),
        "sample_every_s": (node.get("detail") or {}).get("sample_every_s"),
        "agents": [
            {"role": a["role"], "status": a.get("status"), "note": a.get("note"), "detail": a.get("detail")}
            for a in agents
            if a["role"] in ("captions", "speech", "subtitles", "keyframes", "characters", "video")
        ],
        "notes": review["coverage"].get("notes", []),
        "partial": review["coverage"].get("partial", []),
    }


# --- probes: the same pixel path on frames the sampler would have read ----------------------------


def _frame(path: Path, t: float):
    from PIL import Image

    from verytas.media.files import shrink

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "f.png"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", str(out)],
            check=True,
        )
        return shrink(Image.open(out).convert("RGB"), 960)


def _library(manifest: dict, data: Path, brand_key: str):
    from PIL import Image

    from verytas.media import assets as asset_match
    from verytas.prism.agents import OfficialAsset

    lib = []
    for n, (role, a) in enumerate(manifest["brands"][brand_key]["assets"].items(), start=1):
        if role == "reversed" and brand_key != "kitepath":
            continue
        img = Image.open(data / a["file"]).convert("RGBA")
        lib.append(
            OfficialAsset(
                n,
                f"{brand_key} {role}",
                a["kind"],
                a["part"],
                False,
                img,
                asset_match.prepare(n, img),
                a.get("wordmark") or "",
                retired=a["retired"],
            )
        )
    return lib


def probe(manifest: dict, data: Path, v: dict, lib: list) -> list[dict]:
    from evals.assets.run import _findings

    out = []
    path = data / v["file"]
    for k, a in enumerate(v["assets"]):
        lo, hi = a["visible"]
        grid = [float(s) for s in range(math.ceil(lo), int(hi) + 1) if lo <= s <= hi]
        times = {"mid": round((lo + hi) / 2, 2), **{f"s{int(s)}": s for s in grid}}
        got = {}
        for label, t in times.items():
            codes, _ = _findings(lib, _frame(path, t))
            got[label] = {"t": t, "codes": sorted({c for c, _ in codes})}
        out.append({"index": k, "frames": got})
    return out


def add_keyframe_probes(data: Path, out: Path) -> None:
    """Add, to each finished row, the pixel path run alone on every keyframe the review used.

    The review merges the best match per artwork across all keyframes and then judges them together; running
    each keyframe alone shows what that merge costs, without repeating the review (speech and OCR)."""
    manifest = json.loads((data / "manifest.json").read_text())
    videos = {v["id"]: v for v in manifest["videos"]}
    libs: dict[str, list] = {}
    from evals.assets.run import _findings

    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    for n, row in enumerate(rows, start=1):
        v = videos[row["id"]]
        lib = libs.get(v["brand"]) or libs.setdefault(v["brand"], _library(manifest, data, v["brand"]))
        row["key_probes"] = {}
        for t in row["keyframes"]:
            codes, _ = _findings(lib, _frame(data / v["file"], t))
            row["key_probes"][f"{t:.2f}"] = sorted({c for c, _ in codes})
        print(f"{n}/{len(rows)} {row['id']}", flush=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
    tmp.replace(out)


# --- driver ---------------------------------------------------------------------------------------


def run(data: Path, out: Path, resume: bool, limit: int | None, no_probe: bool, only: set[str] | None) -> None:
    from fastapi.testclient import TestClient

    from verytas.config import Settings
    from verytas.main import create_app

    manifest = json.loads((data / "manifest.json").read_text())
    done: set[str] = set()
    if resume and out.is_file():
        whole = []
        for line in out.read_text().splitlines():
            try:
                done.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                continue  # a torn last line from a killed run: dropped, and its video rerun
            whole.append(line + "\n")
        tmp = out.with_suffix(".tmp")
        tmp.write_text("".join(whole))
        tmp.replace(out)
    todo = [v for v in manifest["videos"] if v["id"] not in done and (not only or v["id"] in only)][:limit]
    if not todo:
        print("nothing to run")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    keys = Path(tempfile.mkdtemp(prefix="vidbench-keys-"))
    db = keys / "bench.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db}", llm_mode="offline", keys_dir=keys / "keys", faces_enabled=False
    )
    libs: dict[str, list] = {}
    with TestClient(create_app(settings)) as client, out.open("a" if resume else "w") as fh:
        spaces: dict[str, dict] = {}
        for n, v in enumerate(todo, start=1):
            brand = v["brand"]
            if brand not in spaces:
                spaces[brand] = _setup(client, manifest, data, brand, first=not spaces, db_state={})
            row = {"id": v["id"], "brand": brand, **review_video(client, spaces[brand], data, v)}
            if not no_probe:
                lib = libs.get(brand) or libs.setdefault(brand, _library(manifest, data, brand))
                row["probes"] = probe(manifest, data, v, lib)
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            print(f"{n}/{len(todo)} {v['id']} {row['seconds']} s, {len(row['findings'])} findings", flush=True)


# --- scoring --------------------------------------------------------------------------------------


def _overlap(span, t0: float, t1: float, tol: float) -> bool:
    if not span:
        return False
    return span[0] <= t1 + tol and span[1] >= t0 - tol


def score(manifest: dict, rows: dict[str, dict]) -> dict:
    items, falses = [], []
    for v in manifest["videos"]:
        r = rows.get(v["id"])
        if r is None:
            continue
        fs = r["findings"]
        visual = [f for f in fs if f["source"] == f"vid:{v['id']}"]
        planted_codes: set[str] = set()
        windows: list[tuple[float, float, str]] = []  # (t0, t1, why) where findings are explained
        sampled = r.get("sample_every_s") or 1.0
        for k, a in enumerate(v["assets"]):
            lo, hi = a["visible"]
            n_samples = sum(
                1 for s in range(math.ceil(lo / sampled), int(hi // sampled) + 1) if lo <= s * sampled <= hi
            )
            n_key = sum(1 for t in r["keyframes"] if lo <= t <= hi)
            if not a["plant"]:
                if a["role"] == "mascot":
                    windows.append((a["t0"], a["t1"], "mascot"))
                continue
            planted_codes.update(a["expect"])
            at_time = [f for f in visual if _overlap(f["time"], a["t0"], a["t1"], TIME_TOL["visual"])]
            hit_any = [f for f in visual if set(f["codes"]) & set(a["expect"])]
            hit_timed = [f for f in at_time if set(f["codes"]) & set(a["expect"])]
            pr = next((p for p in r.get("probes", []) if p["index"] == k), None)
            expect = set(a["expect"])
            kp = [codes for t, codes in (r.get("key_probes") or {}).items() if lo <= float(t) <= hi]
            key_alone = any(set(c) & expect for c in kp)
            mid = bool(pr and set(pr["frames"]["mid"]["codes"]) & expect)
            grid = [f for lab, f in (pr["frames"].items() if pr else []) if lab != "mid"]
            dense = any(set(f["codes"]) & expect for f in grid)
            items.append(
                {
                    "video": v["id"],
                    "channel": "visual",
                    "variant": a["variant"],
                    "role": a["role"],
                    "duration": a["duration_class"],
                    "placement": a["placement"],
                    "size": a["size"],
                    "orientation": v["orientation"],
                    "t0": a["t0"],
                    "t1": a["t1"],
                    "expect": a["expect"],
                    "caught_any": bool(hit_any),
                    "caught_timed": bool(hit_timed),
                    "detected_other": bool(at_time) and not hit_timed,
                    "other_codes": sorted({c for f in at_time for c in f["codes"]}),
                    "samples_in_window": n_samples,
                    "keyframes_in_window": n_key,
                    "key_alone": key_alone,
                    "key_probe_run": "key_probes" in r,
                    "mid_probe": mid,
                    "dense_probe": dense,
                    "probe_run": pr is not None,
                    "short": (a["visible"][1] - a["visible"][0]) < 1.0,
                    "dup_role_in_video": sum(1 for b in v["assets"] if b["role"] == a["role"] and b["plant"]) > 1,
                }
            )
        for t in v["texts"]:
            if t["plant"]:
                planted_codes.update(t["expect"])
                ch = "on_screen"
                pool = [f for f in fs if f["source"].endswith(SOURCE_OF[ch]) and set(f["codes"]) & set(t["expect"])]
                timed = [f for f in pool if _overlap(f["time"], t["t0"], t["t1"], TIME_TOL[ch])]
                anywhere = [f for f in fs if set(f["codes"]) & set(t["expect"])]
                items.append(
                    {
                        "video": v["id"],
                        "channel": ch,
                        "variant": t["plant"],
                        "text": t["text"],
                        "t0": t["t0"],
                        "t1": t["t1"],
                        "expect": t["expect"],
                        "caught_any": bool(pool),
                        "caught_timed": bool(timed),
                        "caught_other_channel": bool(anywhere) and not pool,
                        "duration": round(t["t1"] - t["t0"], 1),
                    }
                )
        for s in v["speech"]:
            if s["plant"]:
                planted_codes.update(s["expect"])
                pool = [f for f in fs if f["source"].endswith(":speech") and set(f["codes"]) & set(s["expect"])]
                timed = [f for f in pool if _overlap(f["time"], s["t0"], s["t1"], TIME_TOL["speech"])]
                anywhere = [f for f in fs if set(f["codes"]) & set(s["expect"])]
                items.append(
                    {
                        "video": v["id"],
                        "channel": "speech",
                        "variant": s["plant"],
                        "text": s["text"],
                        "t0": s["t0"],
                        "t1": s["t1"],
                        "expect": s["expect"],
                        "caught_any": bool(pool),
                        "caught_timed": bool(timed),
                        "caught_other_channel": bool(anywhere) and not pool,
                        "duration": round(s["t1"] - s["t0"], 1),
                    }
                )
        for c in v["subtitles"]:
            if c["plant"]:
                planted_codes.update(c["expect"])
                pool = [f for f in fs if f["source"].endswith(":subtitles") and set(f["codes"]) & set(c["expect"])]
                timed = [f for f in pool if _overlap(f["time"], c["t0"], c["t1"], TIME_TOL["subtitles"])]
                items.append(
                    {
                        "video": v["id"],
                        "channel": "subtitles",
                        "variant": c["plant"],
                        "text": c["text"],
                        "t0": c["t0"],
                        "t1": c["t1"],
                        "expect": c["expect"],
                        "caught_any": bool(pool),
                        "caught_timed": bool(timed),
                        "caught_other_channel": False,
                        "duration": round(c["t1"] - c["t0"], 1),
                    }
                )
        # A finding no planted item explains is a false alarm: its rule is not one planted here, it sits in no
        # mascot window, and it is not the captions policy note.
        for f in fs:
            codes = set(f["codes"]) or {"(no rule)"}
            if codes <= NOTE_CODES or codes & planted_codes:
                continue
            if f["source"] == f"vid:{v['id']}" and any(_overlap(f["time"], w[0], w[1], 0.5) for w in windows):
                continue
            falses.append(
                {
                    "video": v["id"],
                    "clean": v["clean"],
                    "kind": v["kind"],
                    "codes": sorted(codes),
                    "title": f["title"],
                    "source": f["source"].split(":")[-1] if ":" in f["source"] else f["source"],
                    "time": f["time"],
                    "level": f["level"],
                }
            )
    return {"items": items, "false": falses}


def _rate(xs: list[dict], key: str = "caught_timed") -> str:
    return f"{sum(bool(x[key]) for x in xs)}/{len(xs)} ({sum(bool(x[key]) for x in xs) / len(xs):.0%})" if xs else "n/a"


def _table(head: list[str], rows: list[list]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(map(str, r)) + " |" for r in rows),
    ]


def report(manifest: dict, rows: dict[str, dict]) -> str:
    sc = score(manifest, rows)
    items, falses = sc["items"], sc["false"]
    vis = [i for i in items if i["channel"] == "visual"]
    probed = any(i["key_probe_run"] for i in vis)  # keyframe probes are an optional second pass
    vids = [v for v in manifest["videos"] if v["id"] in rows]
    secs = [rows[v["id"]]["seconds"] for v in vids]
    bad = [v for v in vids if rows[v["id"]]["review_status"] != "done"]
    mascots = sum(1 for v in vids for a in v["assets"] if a["role"] == "mascot")
    clean = [v for v in vids if v["clean"]]
    kinds = Counter(v["kind"] for v in vids)
    out = [
        f"# Video benchmark ({len(vids)} videos, offline models, production review path)",
        "",
        f"Rendered with Hyperframes {manifest['hyperframes']}, 30 fps, "
        f"{Counter(v['orientation'] for v in vids)['portrait']} portrait and "
        f"{Counter(v['orientation'] for v in vids)['landscape']} landscape, "
        f"{sum(v['duration'] for v in vids):.0f} s in total. Seed {manifest['seed']}. "
        f"Videos: {kinds['asset']} with artwork misuse, {kinds['text']} with planted claims only, "
        f"{kinds['clean']} clean.",
        "",
        f"Planted items: {len(vis)} artwork misuses, "
        f"{sum(i['channel'] == 'on_screen' for i in items)} on-screen claims, "
        f"{sum(i['channel'] == 'speech' for i in items)} spoken claims, "
        f"{sum(i['channel'] == 'subtitles' for i in items)} "
        f"subtitle-track claims. {mascots} mascot appearances are in the videos and are not scored (no vision worker "
        f"locally: not applicable, not missed). Reviews that did not finish: {len(bad)}.",
        "",
        "A finding counts as caught when it has an expected rule code and its time range overlaps the planted one "
        "(0.5 s tolerance for visuals, 1 s for on-screen text, 1.5 s for speech). 'Any time' drops the time condition.",
        "",
        "## By channel",
        "",
    ]
    chan = []
    for label, ch in (
        ("Visuals (artwork misuse)", "visual"),
        ("On-screen text (OCR)", "on_screen"),
        ("Speech (Whisper)", "speech"),
        ("Subtitle track", "subtitles"),
    ):
        xs = [i for i in items if i["channel"] == ch]
        chan.append([label, len(xs), _rate(xs), _rate(xs, "caught_any")])
    out += _table(["Channel", "Planted", "Caught (right code, right time)", "Caught (right code, any time)"], chan)
    out += ["", "## Artwork misuse by appearance length", ""]
    rows_ = []
    for d in (0.5, 1.0, 2.0, 4.0, "shot"):
        xs = [i for i in vis if i["duration"] == d]
        rows_.append(
            [
                f"{d} s" if d != "shot" else "whole shot",
                len(xs),
                _rate(xs),
                _rate(xs, "caught_any"),
                _rate(xs, "dense_probe"),
                f"{sum(i['samples_in_window'] > 0 for i in xs)}/{len(xs)}",
                f"{sum(i['keyframes_in_window'] > 0 for i in xs)}/{len(xs)}",
            ]
        )
    out += _table(
        [
            "Appearance",
            "Items",
            "Caught",
            "Caught any time",
            "Caught if every 1 s sample were matched",
            "Has a 1 s sample inside",
            "Has a keyframe inside",
        ],
        rows_,
    )
    out += ["", "## Artwork misuse by placement, variant, size and orientation", ""]
    rows_ = []
    for label, key, vals in (
        ("Placement", "placement", ("cut", "mid")),
        ("Misuse", "variant", ("stretched", "recoloured", "mirrored", "retired", "competitor")),
        ("Size", "size", ("large", "medium", "small")),
        ("Orientation", "orientation", ("portrait", "landscape")),
    ):
        for val in vals:
            xs = [i for i in vis if i[key] == val]
            rows_.append(
                [
                    label,
                    val,
                    len(xs),
                    _rate(xs),
                    _rate(xs, "caught_any"),
                    _rate(xs, "mid_probe"),
                    _rate(xs, "dense_probe"),
                ]
            )
    out += _table(
        ["Dimension", "Value", "Items", "Caught", "Any time", "Matcher on the middle frame", "Matcher on 1 s samples"],
        rows_,
    )
    out += ["", "## Keyframe-only effect", ""]
    long = [i for i in vis if not i["short"]]
    n = len(vis)
    prod = sum(i["caught_timed"] for i in vis)
    out += _table(
        ["Question", "Items", "Result"],
        [
            ["Production: caught at the right time", n, f"{prod}/{n} ({prod / n:.0%})" if n else "n/a"],
            ["A 1 s sample falls inside the appearance", n, f"{sum(i['samples_in_window'] > 0 for i in vis)}/{n}"],
            ["A keyframe falls inside the appearance", n, f"{sum(i['keyframes_in_window'] > 0 for i in vis)}/{n}"],
            [
                "Matcher gets the right finding on the middle frame (upper bound, ignores sampling)",
                n,
                _rate(vis, "mid_probe"),
            ],
            [
                "Matcher on every 1 s sample inside it (what matching all samples would give)",
                n,
                _rate(vis, "dense_probe"),
            ],
            [
                "Missed in production but caught if every sample were matched",
                n,
                str(sum(i["dense_probe"] and not i["caught_timed"] for i in vis)),
            ],
            [
                "Caught in production although no keyframe is inside (credited to a nearby keyframe or a longer shot)",
                n,
                str(sum(i["caught_timed"] and i["keyframes_in_window"] == 0 for i in vis)),
            ],
            [
                "Matcher on each keyframe inside it, reviewed alone (no merge across keyframes)",
                n,
                _rate(vis, "key_alone") if probed else "not measured (run with --add-keyframe-probes)",
            ],
            [
                "A keyframe inside it gives the right finding when reviewed alone, yet the review missed it",
                n,
                str(sum(i["key_alone"] and not i["caught_timed"] for i in vis)) if probed else "not measured",
            ],
            ["Appearances 1 s or longer: production catch", len(long), _rate(long)],
        ],
    )
    out += ["", "## What a miss was called instead", ""]
    other = Counter(tuple(i["other_codes"]) for i in vis if i["detected_other"])
    silent = sum(1 for i in vis if not i["caught_any"] and not i["detected_other"])
    rows_ = [[", ".join(k), c] for k, c in other.most_common()] + [["(nothing at that time)", silent]]
    out += _table(["Findings at the planted time with another code", "Items"], rows_)
    out += ["", "## False alarms", ""]
    cl = [f for f in falses if f["clean"]]
    out += [
        f"Clean videos: {len(clean)}; with any finding other than the captions, reading-grade and layout notes: "
        f"{len({f['video'] for f in cl})}. Findings on clean videos: {len(cl)}. "
        f"Findings no planted item explains, on all "
        f"videos: {len(falses)} across {len({f['video'] for f in falses})} videos.",
        "",
    ]
    by = defaultdict(list)
    for f in falses:
        by[(tuple(f["codes"]), f["source"])].append(f)
    out += _table(
        ["Rule", "Channel", "Count", "Clean videos", "Example"],
        [
            [", ".join(k[0]), k[1], len(fs), sum(f["clean"] for f in fs), fs[0]["title"][:70]]
            for k, fs in sorted(by.items(), key=lambda kv: -len(kv[1]))
        ],
    )
    out += ["", "## Time", ""]
    if secs:
        out += [
            f"Review plus upload per video: median {statistics.median(secs):.1f} s, "
            f"p95 {sorted(secs)[int(0.95 * (len(secs) - 1))]:.1f} s, max {max(secs):.1f} s "
            f"(median video {statistics.median(v['duration'] for v in vids):.0f} s)."
        ]
    rend = [v["render_seconds"] for v in vids if v.get("render_seconds")]
    if rend:
        out += [f"Hyperframes render per video: median {statistics.median(rend):.0f} s, max {max(rend):.0f} s."]
    out += ["", "## Misses, with times", ""]
    miss = [i for i in items if not i["caught_timed"]]
    lines = []
    for i in sorted(miss, key=lambda i: (i["channel"], i["video"], i["t0"]))[:60]:
        what = f"{i['variant']} {i.get('role', '')}".strip() if i["channel"] == "visual" else f"'{i['text']}'"
        extra = (
            f"{i['duration']} s, {i['placement']}, {i['size']}, samples {i['samples_in_window']}, "
            f"keyframes {i['keyframes_in_window']}, "
            f"matcher on frame: {'yes' if i['dense_probe'] or i['mid_probe'] else 'no'}"
            if i["channel"] == "visual"
            else f"{i['duration']} s"
        )
        lines.append(f"- {i['video']} {i['channel']} {what} at {i['t0']}-{i['t1']} s ({extra})")
    out += lines or ["None."]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path, required=True, help="generate.py's --out directory")
    ap.add_argument("--out", type=Path, default=Path("evals/results/video.jsonl"))
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="comma-separated video ids")
    ap.add_argument("--no-probe", action="store_true", help="skip the per-frame probes")
    ap.add_argument("--add-keyframe-probes", action="store_true", help="probe each keyframe alone, in a finished file")
    ap.add_argument("--report", action="store_true", help="score an existing results file instead of running")
    args = ap.parse_args()
    if args.add_keyframe_probes:
        add_keyframe_probes(args.data, args.out)
        return
    if args.report:
        manifest = json.loads((args.data / "manifest.json").read_text())
        rows = {}
        for line in args.out.read_text().splitlines():
            try:
                row = json.loads(line)
                rows[row["id"]] = row
            except (ValueError, KeyError):
                continue
        text = report(manifest, rows)
        args.out.with_suffix(".md").write_text(text + "\n")
        print(text)
        return
    run(args.data, args.out, args.resume, args.limit, args.no_probe, set(args.only.split(",")) if args.only else None)


if __name__ == "__main__":
    main()
