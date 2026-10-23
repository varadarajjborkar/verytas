"""What if production told Whisper more? Not production code: a measurement to decide what to change.

`video.transcribe` lets Whisper detect the language and gives it no vocabulary. Two cheap changes are
tried here on the same clips and scored the same way as `evals.speech.run`, next to the production result
for those clips:

  hindi_forced     language="hi" for the Hindi and Hinglish clips (Whisper otherwise sometimes answers Hindi
                   speech in Urdu script or Roman letters)
  hinglish_en      language="en" for the Hinglish clips (Roman-letter output, as a Latin brand rule expects)
  brand_prompt     the brand names as initial_prompt for the English clips (a review knows the brand's own
                   names, so this costs nothing at run time). The test brands are the ones in the prompt,
                   as they would be for the brand being reviewed; unknown brands get no such help.
  brand_hotwords   the same names as hotwords, which production uses: an initial prompt is dropped after the
                   first 30 s window when previous text is not carried over, hotwords lead every window.

    .venv/bin/python -m evals.speech.whatif            # runs base and small, writes speech_whatif.{jsonl,md}
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import numpy as np

from evals.speech.generate import BRANDS_SPOKEN
from evals.speech.run import DEFAULT_DATA, RESULTS, grade, group_of, pct, stats

PROMPT = "Brands: " + ", ".join(BRANDS_SPOKEN) + "."
VARIANTS = {
    "hindi_forced": (lambda c: c["lang"] in ("hi", "hinglish"), {"language": "hi"}),
    "hinglish_en": (lambda c: c["lang"] == "hinglish", {"language": "en"}),
    "brand_prompt": (lambda c: c["lang"] == "en", {"initial_prompt": PROMPT}),
    "brand_hotwords": (lambda c: c["lang"] == "en", {"hotwords": PROMPT}),
}


def run(data: Path, out: Path, models: list[str], limit: int | None, only: list[str] | None = None) -> None:
    from verytas.media import video

    cases = [json.loads(line) for line in (data / "cases.jsonl").read_text().splitlines() if line.strip()]
    rows = []
    for model in models:
        video.transcribe(np.zeros(video.SAMPLE_RATE, dtype=np.float32), model)  # loads and caches the model
        whisper = video._asr_models[model]
        for name, (pick, extra) in VARIANTS.items():
            if only and name not in only:
                continue
            chosen = [c for c in cases if pick(c)][:limit]
            for n, case in enumerate(chosen, 1):
                pcm = video.audio_pcm((data / case["file"]).read_bytes(), max_seconds=600)
                t = time.perf_counter()
                # The production call's own arguments, plus the one change under test.
                segments, info = whisper.transcribe(pcm, vad_filter=True, beam_size=1,
                                                    condition_on_previous_text=False, **extra)
                hyp = "\n".join(s.text.strip() for s in segments if s.text.strip())
                secs = time.perf_counter() - t
                rows.append({"variant": name, "model": model, "id": case["id"], "lang": case["lang"],
                             "accent": case["accent"], "voice": case["voice"], "noise": case["noise"],
                             "speed": case["speed"], "hyp": hyp, "language": info.language,
                             "rtf": round(secs / (pcm.size / video.SAMPLE_RATE), 3)} | grade(case, hyp))
                if n % 20 == 0:
                    print(f"{model} {name} {n}/{len(chosen)}", flush=True)
    # A run of some variants keeps the rows of the others already in the file.
    kept = [line for line in (out.read_text().splitlines() if only and out.is_file() else [])
            if line.strip() and json.loads(line)["variant"] not in only]
    out.write_text("".join(line + "\n" for line in kept) + "".join(json.dumps(r, ensure_ascii=False) + "\n"
                                                                   for r in rows))


def report(rows: list[dict], base: list[dict]) -> str:
    md = ["# Speech what-if: telling Whisper the language and the brand names", "",
          "Same clips and scoring as `speech.md`; the production figure is Whisper with language auto-detection and "
          "no prompt. Not production code: see `evals/speech/whatif.py`.", ""]
    for name in VARIANTS:
        md += [f"## {name}", "",
               "| Group | Model | Clips | WER production | WER what-if | Critical production | Critical what-if | "
               "Devanagari / Arabic / Latin what-if |", "|---|---|---|---|---|---|---|---|"]
        groups = sorted({group_of(r) for r in rows if r["variant"] == name})
        for g in groups:
            for m in ("base", "small"):
                new = [r for r in rows if r["variant"] == name and r["model"] == m and group_of(r) == g]
                if not new:
                    continue
                ids = {r["id"] for r in new}
                old = [r for r in base if r["model"] == m and r["id"] in ids]
                sh = {k: statistics.mean(r["scripts"][k] for r in new) for k in ("devanagari", "arabic", "latin")}
                md.append(f"| {g} | {m} | {len(new)} | {stats(old)[0]} | {stats(new)[0]} | {stats(old)[2]} | "
                          f"{stats(new)[2]} | {100 * sh['devanagari']:.0f}% / {100 * sh['arabic']:.0f}% / "
                          f"{100 * sh['latin']:.0f}% |")
        kinds = sorted({c["kind"] for r in rows if r["variant"] == name for c in r["critical"]})
        md += ["", "Critical phrases heard by kind (production, what-if):", "",
               "| Kind | base | base what-if | small | small what-if |", "|---|---|---|---|---|"]
        for kd in kinds:
            cells = []
            for m in ("base", "small"):
                mine = [r for r in rows if r["variant"] == name and r["model"] == m]
                ids = {r["id"] for r in mine}
                new = [c for r in mine for c in r["critical"] if c["kind"] == kd]
                old = [c for r in base if r["model"] == m and r["id"] in ids for c in r["critical"]
                       if c["kind"] == kd]
                cells += [pct(sum(c["ok"] for c in old), len(old)), pct(sum(c["ok"] for c in new), len(new))]
            md.append(f"| {kd} | " + " | ".join(cells) + " |")
        md.append("")
    return "\n".join(md) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.speech.whatif")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--out", type=Path, default=RESULTS / "speech_whatif.jsonl")
    p.add_argument("--md", type=Path, default=RESULTS / "speech_whatif.md")
    p.add_argument("--model", action="append")
    p.add_argument("--limit", type=int)
    p.add_argument("--variant", action="append", choices=list(VARIANTS), help="run only these (others kept)")
    p.add_argument("--report", action="store_true")
    args = p.parse_args()
    if not args.report:
        run(args.data, args.out, args.model or ["base", "small"], args.limit, args.variant)
    rows = [json.loads(line) for line in args.out.read_text().splitlines() if line.strip()]
    base = [json.loads(line) for line in (RESULTS / "speech.jsonl").read_text().splitlines() if line.strip()]
    args.md.write_text(report(rows, base))
    print(f"{len(rows)} rows; report in {args.md}")


if __name__ == "__main__":
    main()
