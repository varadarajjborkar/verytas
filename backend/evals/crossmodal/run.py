"""Cross-source benchmark: figures that read differently between the parts of one post.

Each case is a post: a caption plus a poster, or a short reel with a voice-over and on-screen text.
Some cases plant a contradiction (the caption says 50% off, the poster 30%; the voice says 499 rupees,
the screen Rs 999); the controls hold figures that agree, agree under a bound ("up to 50%" with 30%),
belong to a price list, or are about different things (a 7-day trial and a 30-day guarantee). Every case
goes through the production review path with local OCR and local Whisper, so the score includes what
reading the pixels and the audio gets wrong, not only the comparison.

    .venv/bin/python -m evals.crossmodal.run --out evals/results/crossmodal.jsonl
    .venv/bin/python -m evals.crossmodal.run --report evals/results/crossmodal.jsonl
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Black.ttf",
         "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"]
BACKS = [((250, 245, 235), (20, 20, 20)), ((20, 40, 90), (255, 255, 255)), ((230, 60, 60), (255, 255, 255))]
VOICES = ["Rishi", "Tara", "Aman"]

# (id, caption, poster lines, planted?)
POSTERS = [
    ("p-off-50-30", "Flat 50% off all courses this week. Enrol now.", ["30% OFF", "ALL COURSES"], True),
    ("p-off-40-25", "Festive sale: 40% off every plan!", ["FESTIVE SALE", "25% OFF EVERY PLAN"], True),
    ("p-off-20-15", "Save 20% on your first month.", ["SAVE 15%", "on your first month"], True),
    ("p-price-499-999", "Enrol for just Rs 499.", ["FULL COURSE", "ONLY Rs 999"], True),
    ("p-price-1499-1999", "The bootcamp is Rs 1,499 for everyone.", ["BOOTCAMP", "Rs 1,999"], True),
    ("p-price-rupee", "Get the pass for ₹2,999.", ["ANNUAL PASS", "₹3,499"], True),
    ("p-month-299-399", "Plans at Rs 299/month.", ["PLANS AT", "Rs 399 per month"], True),
    ("p-trial-7-14", "Start a 7-day free trial today.", ["14-DAY FREE TRIAL", "No card needed"], True),
    ("p-cashback-10-5", "Pay with the app and get 10% cashback.", ["5% CASHBACK", "on every payment"], True),
    ("p-count-learners", "Join 50,000+ learners across India.", ["JOIN 5,000 LEARNERS", "across India"], True),
    ("c-same-off", "Flat 50% off all courses this week.", ["50% OFF", "ALL COURSES"], False),
    ("c-same-price-format", "The annual plan is Rs 4,999 a year.", ["ANNUAL PLAN", "Rs 4999/year"], False),
    ("c-up-to", "Up to 50% off courses this week.", ["30% OFF", "SELECTED COURSES"], False),
    ("c-from", "Courses from Rs 499.", ["DATA SCIENCE", "Rs 999"], False),
    ("c-price-list", "Plans from Rs 299/month.", ["BASIC Rs 299/month", "PRO Rs 599/month"], False),
    ("c-trial-vs-guarantee", "Start a 7-day free trial.", ["30-DAY MONEY-BACK", "GUARANTEE"], False),
    ("c-off-vs-cashback", "50% off for new learners.", ["10% CASHBACK", "with the app"], False),
    ("c-plus-bound", "Join 10,000+ learners.", ["12,000 LEARNERS", "and counting"], False),
    ("c-different-nouns", "340 courses for you.", ["9 LANGUAGES", "One app"], False),
    ("c-no-figures", "Our new course is out: 30% off for the first week.", ["LEARN PYTHON", "Real mentors"], False),
]

# (id, caption, [(t0, t1, on-screen text)], (delay_s, spoken line), planted?)
REELS = [
    ("v-price", "Our new course is out", [(0, 4, "FULL COURSE RS 999"), (4, 8, "Link in bio")],
     (0.8, "And the full course is just four hundred and ninety nine rupees."), True),
    ("v-off", "The sale starts today", [(0, 4, "25% OFF TODAY"), (4, 8, "Shop now")],
     (0.6, "Get forty percent off today only."), True),
    ("v-trial", "Try it free", [(0, 4, "7-DAY FREE TRIAL"), (4, 8, "Sign up today")],
     (0.6, "Start your fourteen day free trial today."), True),
    ("v-flat", "Big savings this week", [(0, 4, "FLAT 30% OFF"), (4, 8, "This week only")],
     (0.6, "Flat fifty percent off, this week only."), True),
    ("v-same", "The sale starts today", [(0, 4, "40% OFF TODAY"), (4, 8, "Shop now")],
     (0.6, "Get forty percent off today only."), False),
    ("v-same-price", "Our new course is out", [(0, 4, "FULL COURSE RS 499"), (4, 8, "Link in bio")],
     (0.8, "The full course is just four hundred and ninety nine rupees."), False),
    ("v-up-to", "Big savings this week", [(0, 4, "30% OFF SHOES"), (4, 8, "This week only")],
     (0.6, "Up to fifty percent off, this week only."), False),
    ("v-far-apart", "Two offers", [(0, 3, "20% OFF BAGS"), (3, 12, "New arrivals")],
     (8.0, "And shoes are forty percent off."), False),
]


def _font(i: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONTS[i % len(FONTS)], size)


def poster(lines: list[str], i: int) -> bytes:
    bg, fg = BACKS[i % len(BACKS)]
    img = Image.new("RGB", (1080, 1080), bg)
    d = ImageDraw.Draw(img)
    d.rectangle((60, 60, 1020, 1020), outline=fg, width=6)
    y = 300
    for j, line in enumerate(lines):
        f = _font(i + j, 96 if j == 0 else 64)
        w = d.textlength(line, font=f)
        d.text(((1080 - w) / 2, y), line, fill=fg, font=f)
        y += 170
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def reel(cues: list[tuple[float, float, str]], speech: tuple[float, str], i: int, work: Path) -> bytes:
    seconds = max(b for _, b, _ in cues)
    fps = 5
    frames = work / f"f{i}"
    frames.mkdir(parents=True, exist_ok=True)
    for k in range(int(seconds * fps)):
        t = k / fps
        img = Image.new("RGB", (720, 1280), BACKS[i % len(BACKS)][0] if t < seconds / 2 else (40, 40, 60))
        d = ImageDraw.Draw(img)
        txt = next((c for a, b, c in cues if a <= t < b), "")
        if txt:
            f = _font(i, 64)
            w = d.textlength(txt, font=f)
            d.rectangle((40, 820, 680, 940), fill="black")
            d.text(((720 - w) / 2, 845), txt, fill="white", font=f)
        img.save(frames / f"{k:04d}.png")
    aiff, wav, mp4 = work / f"s{i}.aiff", work / f"s{i}.wav", work / f"v{i}.mp4"
    subprocess.run(["say", "-v", VOICES[i % len(VOICES)], "-r", "170", "-o", str(aiff), speech[1]], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)],
                   check=True)
    ms = int(speech[0] * 1000)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames / "%04d.png"),
                    "-i", str(wav), "-filter_complex", f"[1:a]adelay={ms}:all=1,apad[a]", "-map", "0:v", "-map",
                    "[a]", "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(mp4)],
                   check=True)
    return mp4.read_bytes()


def _mismatches(review: dict) -> list[dict]:
    return [f for f in review["findings"] if f["checker"] == "crosscheck"]


def run(out: Path) -> None:
    from fastapi.testclient import TestClient

    from verytas.config import Settings
    from verytas.main import create_app

    work = Path(tempfile.mkdtemp(prefix="crossmodal-"))
    settings = Settings(database_url=f"sqlite+aiosqlite:///{work / 'bench.db'}", llm_mode="offline",
                        keys_dir=work / "keys", faces_enabled=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    with TestClient(create_app(settings)) as c, out.open("w") as fh:
        admin = c.post("/bootstrap", json={"workspace_name": "Bench", "admin_email": "a@bench.example",
                                           "admin_name": "A"}).json()["token"]
        creator = c.post("/users", headers={"Authorization": f"Bearer {admin}"},
                         json={"email": "c@bench.example", "name": "C", "role": "creator"}).json()["token"]
        h = {"Authorization": f"Bearer {creator}"}

        def submit(body: str, attachments: dict, brief: str = "") -> tuple[dict, float]:
            started = time.monotonic()
            res = c.post("/contents?wait=true", headers=h, json={
                "title": "Bench", "channel": "instagram", "tier": "public", "body": body,
                "attachments": attachments, "creator_notes": {"brief": brief} if brief else {}})
            res.raise_for_status()
            review = c.get(f"/reviews/{res.json()['review_id']}", headers=h).json()
            return review, time.monotonic() - started

        for i, (cid, body, lines, planted) in enumerate(POSTERS):
            data = base64.b64encode(poster(lines, i)).decode()
            review, secs = submit(body, {"images": [{"id": "poster", "alt": "Sale poster with the offer",
                                                     "data_base64": data}]})
            _write(fh, cid, "poster", planted, review, secs)
        for i, (cid, body, cues, speech, planted) in enumerate(REELS):
            clip = reel(cues, speech, i, work)
            blob = c.post("/media", headers=h, files={"file": (f"{cid}.mp4", clip, "video/mp4")}).json()
            review, secs = submit(body, {"videos": [{"id": "reel", "blob_id": blob["id"]}]},
                                  brief="A short reel about the offer; I speak over it.")
            _write(fh, cid, "reel", planted, review, secs)


def _write(fh, cid: str, kind: str, planted: bool, review: dict, secs: float) -> None:
    found = _mismatches(review)
    texts = {s["id"]: s["text"][:200] for s in review["coverage"]["sources"]}
    row = {"id": cid, "kind": kind, "planted": planted, "caught": bool(found), "seconds": round(secs, 1),
           "findings": [{"title": f["title"], "level": f["level"], "source": f["source"],
                         "evidence": (f["locator"] or {}).get("evidence")} for f in found],
           "read": texts}
    fh.write(json.dumps(row) + "\n")
    fh.flush()
    print(f"{cid:24s} planted={planted!s:5s} caught={bool(found)!s:5s} {[f['title'] for f in found]}")


# The two figures each planted case contradicts, as digits: a catch has to name both, not merely fire.
FIGURES = {
    "p-off-50-30": ("50", "30"), "p-off-40-25": ("40", "25"), "p-off-20-15": ("20", "15"),
    "p-price-499-999": ("499", "999"), "p-price-1499-1999": ("1499", "1999"), "p-price-rupee": ("2999", "3499"),
    "p-month-299-399": ("299", "399"), "p-trial-7-14": ("7", "14"), "p-cashback-10-5": ("10", "5"),
    "p-count-learners": ("50000", "5000"), "v-price": ("999", "499"), "v-off": ("25", "40"),
    "v-trial": ("7", "14"), "v-flat": ("30", "50"),
}


def _named(row: dict) -> bool:
    want = FIGURES.get(row["id"])
    return bool(want) and any(set(want) <= set(re.findall(r"\d+", f["title"].replace(",", "")))
                              for f in row["findings"])


def report(path: Path) -> str:
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    lines = ["# Cross-source benchmark", "",
             "Planted contradictions between the parts of one post, and controls that must stay quiet. Every case "
             "runs through the production review with local OCR and local Whisper.", "",
             "| Cases | Planted, caught | Caught naming both planted figures | Controls, false alarms |",
             "|---|---|---|---|"]
    for kind in ("poster", "reel"):
        rs = [r for r in rows if r["kind"] == kind]
        planted = [r for r in rs if r["planted"]]
        controls = [r for r in rs if not r["planted"]]
        lines.append(f"| {kind} ({len(rs)}) | {sum(r['caught'] for r in planted)}/{len(planted)} | "
                     f"{sum(_named(r) for r in planted)}/{len(planted)} | "
                     f"{sum(r['caught'] for r in controls)}/{len(controls)} |")
    missed = [r for r in rows if r["planted"] and not r["caught"]]
    alarms = [r for r in rows if not r["planted"] and r["caught"]]
    for title, rs in (("Missed", missed), ("False alarms", alarms)):
        if rs:
            lines += ["", f"## {title}", ""]
            for r in rs:
                read = "; ".join(f"{k}: {v!r}" for k, v in r["read"].items() if k != "body")
                lines.append(f"- `{r['id']}`: {[f['title'] for f in r['findings']] or 'nothing'}. Read: {read}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("evals/results/crossmodal.jsonl"))
    ap.add_argument("--report", type=Path, help="write the summary for an existing results file and stop")
    args = ap.parse_args()
    if args.report:
        md = report(args.report)
        args.report.with_suffix(".md").write_text(md)
        print(md)
        return
    run(args.out)
    md = report(args.out)
    args.out.with_suffix(".md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
