"""Transcribe the speech benchmark with the production function and score it, per Whisper model.

Each clip goes through `verytas.media.video.audio_pcm` (PyAV decode to 16 kHz mono, as for a video upload)
and `verytas.media.video.transcribe` (faster-whisper, int8 on CPU, VAD on, beam 1: the exact settings
reviews use), and the transcript is `video.cue_text` of the cues, which is what the checks read:

    .venv/bin/python -m evals.speech.run --model base
    .venv/bin/python -m evals.speech.run --model small --resume
    .venv/bin/python -m evals.speech.run --report

Without --resume, rows of the models being run are replaced and rows of other models are kept, so the two
models share one results file. --limit takes the first N clips per model.

Scoring, per clip:
- WER: word edit distance between the script and the transcript after normalisation. Both sides are
  NFKC, case-folded, punctuation and symbols removed (including the danda), nukta and zero-width joiners
  dropped (Whisper writes ज़ and ज interchangeably), and "and" dropped. For English and Hinglish digits are
  spoken: "1,499", "Rs. 1499" and "rupees 1499" all become "one thousand four hundred ninety nine rupees",
  "40%" becomes "forty percent", "31st" becomes "thirty first", "www.x.in/sale" becomes
  "w w w dot x dot in slash sale", and a run of 7 or more digits (a phone number, with or without spaces
  or hyphens) is spelled digit by digit. Hindi keeps its digits as written: a script that says चालीस and a
  transcript that writes 40 counts as a word error, which is why the critical-phrase score below accepts
  both spellings.
- CER: the same normalised text with spaces removed, because Hindi and Hinglish word boundaries are noisy.
- Critical phrases (percent, price, number, date, phone, URL, brand): heard when any accepted spelling
  appears as whole words (brands and Hindi: as a substring with spaces removed, so "Kiraana Kart" and
  "Kirana Kart" differ by a letter and count as a miss, "Lumo Wear" vs "LumoWear" does not).
- Language: Whisper's detected language, scored against the clip (en and hi); for Hinglish there is no
  right answer, so the distribution is reported.
- Real-time factor: transcription seconds per second of audio, model load excluded.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from evals.ocr.metrics import edit_distance

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
DEFAULT_DATA = Path("/private/tmp/claude-502/-Users-varadarajborkar-praj-code/"
                    "298965cb-f1e3-424a-8f01-ca8c15eeb018/scratchpad/speechbench")

# ---------------------------------------------------------------------------------- normalisation

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
ORDINAL = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
           "twelve": "twelfth"}


def spell(n: int) -> str:
    """English words for a whole number, in the spoken style without "and"."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + (f" {ONES[n % 10]}" if n % 10 else "")
    for size, name in ((10**9, "billion"), (10**6, "million"), (10**3, "thousand"), (100, "hundred")):
        if n >= size:
            rest = n % size
            return f"{spell(n // size)} {name}" + (f" {spell(rest)}" if rest else "")
    raise ValueError(n)


def ordinal(n: int) -> str:
    words = spell(n).split()
    last = words[-1]
    words[-1] = ORDINAL.get(last, last[:-1] + "ieth" if last.endswith("y") else last + "th")
    return " ".join(words)


def _digits(m: re.Match) -> str:
    s = re.sub(r"\D", "", m.group())
    return " " + (" ".join(ONES[int(d)] for d in s) if len(s) >= 7 else spell(int(s))) + " "


def _phone(m: re.Match) -> str:
    """Digit groups joined by spaces or hyphens: a phone number if 7 or more digits, else left alone."""
    return _digits(m) if len(re.sub(r"\D", "", m.group())) >= 7 else m.group()


def normalise(text: str, lang: str) -> str:
    t = unicodedata.normalize("NFKC", text).casefold()
    t = unicodedata.normalize("NFD", t).replace("़", "")  # nukta
    t = unicodedata.normalize("NFC", t).replace("‌", "").replace("‍", "")
    t = re.sub(r"['’]", "", t)
    if lang != "hi":
        t = t.replace("/-", " ").replace("%", " percent ")
        t = re.sub(r"per cent", "percent", t)
        t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
        t = re.sub(r"(?:₹|\brs\b\.?|\binr\b)\s*(\d+)", r"\1 rupees", t)
        t = re.sub(r"\brupees?\s+(\d+)", r"\1 rupees", t)
        t = re.sub(r"(\d)\s*(?:rs\b\.?|inr\b)", r"\1 rupees", t)
        t = re.sub(r"\btriple w\b", "w w w", t)
        t = re.sub(r"(?<=\w)\.(?=\w)", " dot ", t)
        t = t.replace("/", " slash ").replace("@", " at ")
        t = re.sub(r"\bwww\b", "w w w", t)
        t = re.sub(r"\+?\d+(?:[ \-]\d+)+", _phone, t)
        t = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", lambda m: " " + ordinal(int(m.group(1))) + " ", t)
        t = re.sub(r"\d+", _digits, t)
    t = "".join(" " if unicodedata.category(ch)[0] in "PS" else ch for ch in t)
    return " ".join(w for w in t.split() if w != "and")


def heard(crit: dict, hyp_norm: str, lang: str) -> bool:
    flat = hyp_norm.replace(" ", "")
    for alt in crit["alts"]:
        a = normalise(alt, lang)
        if crit["mode"] == "nospace":
            if a.replace(" ", "") in flat:
                return True
        elif f" {a} " in f" {hyp_norm} ":
            return True
    return False


def script_shares(text: str) -> dict[str, float]:
    """Share of the letters in Devanagari, Arabic (Urdu) and Latin script.

    Whisper may answer Hindi speech in any of the three, and a brand rule written in Latin or Devanagari
    only sees one of them, so which script comes back matters as much as how many words are right.
    """
    count = {"devanagari": 0, "arabic": 0, "latin": 0}
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            count["devanagari"] += 1
        elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F or 0xFB50 <= cp <= 0xFEFF:
            count["arabic"] += 1
        elif ch.isascii() and ch.isalpha():
            count["latin"] += 1
    total = sum(count.values())
    return {k: round(v / total, 3) if total else 0.0 for k, v in count.items()}


# ------------------------------------------------------------------------------------------- run

def score(case: dict, data: Path, model: str) -> dict:
    from verytas.media import video

    raw = (data / case["file"]).read_bytes()
    pcm = video.audio_pcm(raw, max_seconds=600)
    seconds_audio = pcm.size / video.SAMPLE_RATE
    t = time.perf_counter()
    cues, language, prob = video.transcribe(pcm, model)
    seconds = time.perf_counter() - t
    hyp, _ = video.cue_text(cues)
    return {
        "model": model, "id": case["id"], "file": case["file"], "lang": case["lang"], "voice": case["voice"],
        "accent": case["accent"], "noise": case["noise"], "speed": case["speed"], "fine_print": case["fine_print"],
        "duration": round(seconds_audio, 2), "truth": case["text"], "hyp": hyp,
        "language": language, "language_prob": round(prob, 3), "empty": not cues,
        "seconds": round(seconds, 3), "rtf": round(seconds / seconds_audio, 3),
    } | grade(case, hyp)


def grade(case: dict, hyp: str) -> dict:
    """Everything derived from the transcript, so a change to the normaliser can rescore without the model."""
    lang = case["lang"]
    truth_n, hyp_n = normalise(case["text"], lang), normalise(hyp, lang)
    return {
        "wer_edits": edit_distance(truth_n.split(), hyp_n.split()), "wer_len": len(truth_n.split()),
        "cer_edits": edit_distance(truth_n.replace(" ", ""), hyp_n.replace(" ", "")),
        "cer_len": len(truth_n.replace(" ", "")),
        "critical": [{"kind": c["kind"], "t": c["t"], "ok": heard(c, hyp_n, lang)} for c in case["critical"]],
        "scripts": script_shares(hyp),
    }


def rescore(data: Path, out: Path) -> None:
    cases = {c["id"]: c for c in map(json.loads, (data / "cases.jsonl").read_text().splitlines()) if c}
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    tmp = out.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r | grade(cases[r["id"]], r["hyp"]), ensure_ascii=False) + "\n" for r in rows))
    tmp.replace(out)


def run(data: Path, out: Path, models: list[str], resume: bool, limit: int | None) -> None:
    from verytas.media import video

    cases = [json.loads(line) for line in (data / "cases.jsonl").read_text().splitlines() if line.strip()]
    if limit:
        cases = cases[:limit]
    kept: list[str] = []
    done: set[tuple[str, str]] = set()
    if out.is_file():
        for line in out.read_text().splitlines():
            try:
                row = json.loads(line)
                key = (row["model"], row["id"])
            except (ValueError, KeyError):
                continue  # a torn last line from a killed run is dropped and its clip rerun
            if resume or row["model"] not in models:
                kept.append(line + "\n")
                done.add(key)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text("".join(kept))
    tmp.replace(out)  # one step: a crash leaves the old file, never a half-written one
    with out.open("a") as fh:
        for model in models:
            t0 = time.perf_counter()
            import numpy as np

            video.transcribe(np.zeros(video.SAMPLE_RATE, dtype=np.float32), model)  # load, untimed
            print(f"{model}: loaded in {time.perf_counter() - t0:.0f}s", flush=True)
            for n, case in enumerate(cases, 1):
                if (model, case["id"]) in done:
                    continue
                fh.write(json.dumps(score(case, data, model), ensure_ascii=False) + "\n")
                fh.flush()
                if n % 10 == 0:
                    print(f"{model} {n}/{len(cases)} clips, {time.perf_counter() - t0:.0f}s", flush=True)


# ---------------------------------------------------------------------------------------- report

def pct(a: float, b: float) -> str:
    return f"{100 * a / b:.1f}%" if b else "-"


def group_of(r: dict) -> str:
    if r["lang"] == "en":
        return "English, Indian voices" if r["accent"] == "en_IN" else "English, US and UK voices"
    if r["lang"] == "hi":
        return "Hindi (Lekha)"
    return "Hinglish, Indian-English voices" if r["accent"] == "en_IN" else "Hinglish, Hindi voice (Lekha)"


def condition_of(r: dict) -> str:
    if r["noise"] != "none":
        kind, snr = r["noise"].split("_")
        return f"{'white noise' if kind == 'white' else 'music bed'}, {snr} dB SNR"
    if r["speed"] == "tts_fast":
        return "fine print read very fast"
    return "clean, normal speed" if r["speed"] == "1.0" else f"clean, {r['speed']}x speed-up"


def stats(rs: list[dict]) -> tuple[str, str, str, str]:
    we, wn = sum(r["wer_edits"] for r in rs), sum(r["wer_len"] for r in rs)
    cr = [c for r in rs for c in r["critical"]]
    ce, cn = sum(r["cer_edits"] for r in rs), sum(r["cer_len"] for r in rs)
    ok = sum(c["ok"] for c in cr)
    return pct(we, wn), pct(ce, cn), f"{pct(ok, len(cr))} ({ok}/{len(cr)})" if cr else "-", \
        f"{statistics.median(r['rtf'] for r in rs):.2f}"


def compare(rows: list[dict], models: list[str], key, order: list[str] | None = None,
            label: str = "Group") -> list[str]:
    by: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[key(r)][r["model"]].append(r)
    head = f"| {label} | Clips | " + " | ".join(f"WER {m} | Critical {m}" for m in models) + " |"
    out = [head, "|---|---|" + "---|---|" * len(models)]
    for k in order or sorted(by):
        if k not in by:
            continue
        first = by[k][models[0]] if by[k][models[0]] else next(iter(by[k].values()))
        cells = []
        for m in models:
            rs = by[k].get(m)
            cells += [stats(rs)[0], stats(rs)[2]] if rs else ["-", "-"]
        out.append(f"| {k} | {len(first)} | " + " | ".join(cells) + " |")
    return out


def report(rows: list[dict]) -> str:
    models = [m for m in ("base", "small") if any(r["model"] == m for r in rows)] or sorted({r["model"] for r in rows})
    md = [
        "# Speech benchmark", "",
        "Production speech-to-text (`verytas.media.video.audio_pcm` then `transcribe`, faster-whisper int8 on CPU, "
        "VAD on, beam 1, language auto-detected) on clips with known scripts. Generator: `evals/speech/generate.py` "
        "(macOS `say` voices, synthetic noise and music, ffmpeg speed changes). Scorer: `evals/speech/run.py`; its "
        "docstring defines the normalisation (spoken numbers, URLs and phone numbers are made comparable).", "",
        "Caveat: every voice is text-to-speech. Real voices are noisier and less regular, so absolute errors will be "
        "higher in the field. Hinglish is an approximation (an Indian-English voice reading romanised Hindi, or the "
        "Hindi voice reading the same Latin text); real code-switching is harder to read and to transcribe.", "",
        "## Base vs small", "",
        "| Model | Clips | Audio | WER (pooled) | CER | Critical phrases heard | RTF median | RTF mean | "
        "Empty transcripts |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        w, c, k, rtf = stats(rs)
        md.append(f"| {m} | {len(rs)} | {sum(r['duration'] for r in rs) / 60:.1f} min | {w} | {c} | {k} | {rtf} | "
                  f"{statistics.mean(r['rtf'] for r in rs):.2f} | {sum(r['empty'] for r in rs)} |")
    both = sorted({r["id"] for m in models for r in rows if r["model"] == m}
                  & set.intersection(*[{r["id"] for r in rows if r["model"] == m} for m in models]))
    if len(models) > 1 and both:
        md += ["", f"The {len(both)} clips both models transcribed (a fair like-for-like):", "",
               "| Model | WER | Critical phrases heard |", "|---|---|---|"]
        for m in models:
            rs = [r for r in rows if r["model"] == m and r["id"] in both]
            md.append(f"| {m} | {stats(rs)[0]} | {stats(rs)[2]} |")
        md += ["", "RTF is transcription seconds per second of audio on this machine (8 CPU cores, int8); the tables "
               "below show WER and critical phrases heard per condition and model."]
    groups = ["English, Indian voices", "English, US and UK voices", "Hindi (Lekha)", "Hinglish, Indian-English voices",
              "Hinglish, Hindi voice (Lekha)"]
    conds = ["clean, normal speed", "white noise, 15 dB SNR", "white noise, 5 dB SNR", "music bed, 15 dB SNR",
             "music bed, 5 dB SNR", "clean, 1.25x speed-up", "clean, 1.5x speed-up", "fine print read very fast"]
    md += ["", "## By language group", ""] + compare(rows, models, group_of, groups)
    md += ["", "## By condition", "", "All languages pooled; clean means no added noise at normal speed.", ""]
    md += compare(rows, models, condition_of, conds, "Condition")
    md += ["", "### Condition within each language group", ""]
    for g in groups:
        sub = [r for r in rows if group_of(r) == g]
        if sub:
            md += [f"**{g}**", ""] + compare(sub, models, condition_of, conds, "Condition") + [""]
    md += ["## By voice", ""] + compare(rows, models, lambda r: f"{r['voice']} ({r['accent']})", None, "Voice")

    md += ["", "## Critical phrases by kind", "", "Share of phrases heard, English clips and Hindi plus Hinglish clips "
           "apart.", "",
           "| Kind | Phrases (en / hi+hinglish) | " + " | ".join(f"{m} en | {m} hi+hinglish" for m in models) + " |",
           "|---|---|" + "---|---|" * len(models)]
    kinds = sorted({c["kind"] for r in rows for c in r["critical"]})
    for kd in kinds:
        cells = []
        for m in models:
            for is_en in (True, False):
                cs = [c for r in rows if r["model"] == m and (r["lang"] == "en") == is_en
                      for c in r["critical"] if c["kind"] == kd]
                cells.append(f"{pct(sum(c['ok'] for c in cs), len(cs))} ({len(cs)})" if cs else "-")
        n_en = sum(1 for r in rows if r["model"] == models[0] and r["lang"] == "en" for c in r["critical"]
                   if c["kind"] == kd)
        n_hi = sum(1 for r in rows if r["model"] == models[0] and r["lang"] != "en" for c in r["critical"]
                   if c["kind"] == kd)
        md.append(f"| {kd} | {n_en} / {n_hi} | " + " | ".join(cells) + " |")

    md += ["", "## Language detection", "",
           "| Group | Clips | " + " | ".join(f"detected as ({m})" for m in models) + " |",
           "|---|---|" + "---|" * len(models)]
    for g in groups:
        cells = []
        n = 0
        for m in models:
            rs = [r for r in rows if r["model"] == m and group_of(r) == g]
            n = len(rs)
            dist = Counter(r["language"] or "none" for r in rs)
            cells.append(", ".join(f"{k} {v}" for k, v in dist.most_common()))
        md.append(f"| {g} | {n} | " + " | ".join(cells) + " |")
    for m in models:
        for lg, name in (("en", "English"), ("hi", "Hindi")):
            rs = [r for r in rows if r["model"] == m and r["lang"] == lg]
            md.append(f"\nLanguage accuracy, {name} clips, {m}: {pct(sum(r['language'] == lg for r in rs), len(rs))}")
    md += ["", "Script of the transcript (share of letters) for the Hindi and Hinglish groups:", "",
           "| Group | Model | Devanagari | Arabic (Urdu) | Latin |", "|---|---|---|---|---|"]
    for g in groups[2:]:
        for m in models:
            rs = [r for r in rows if r["model"] == m and group_of(r) == g]
            if rs:
                sh = {k: statistics.mean(r["scripts"][k] for r in rs) for k in ("devanagari", "arabic", "latin")}
                md.append(f"| {g} | {m} | {100 * sh['devanagari']:.0f}% | {100 * sh['arabic']:.0f}% | "
                          f"{100 * sh['latin']:.0f}% |")

    md += ["", "## Failure examples", ""]
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        worst = sorted(rs, key=lambda r: r["wer_edits"] / max(1, r["wer_len"]), reverse=True)[:6]
        md += [f"**Worst clips, {m}**", ""]
        for r in worst:
            md += [f"- {r['id']} ({group_of(r)}; {condition_of(r)}) WER {pct(r['wer_edits'], r['wer_len'])}",
                   f"  - said: {r['truth'][:200]}", f"  - heard: {r['hyp'][:200] or '(nothing)'}"]
        missed = [(r, c) for r in rs for c in r["critical"] if not c["ok"]]
        md += ["", f"Critical phrases missed by {m}: {len(missed)}", ""]
        seen: Counter = Counter()
        for r, c in missed:
            if seen[c["kind"]] >= 3:
                continue
            seen[c["kind"]] += 1
            heard_as = r["hyp"][:160].replace("\n", " ") or "(nothing)"
            md.append(f"- {c['kind']} `{c['t']}` in {r['id']} ({condition_of(r)}): heard `{heard_as}`")
        md.append("")
    return "\n".join(md) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.speech.run")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--out", type=Path, default=RESULTS / "speech.jsonl")
    p.add_argument("--md", type=Path, default=RESULTS / "speech.md")
    p.add_argument("--model", action="append", help="whisper model to run; repeat for several (default base and small)")
    p.add_argument("--limit", type=int)
    p.add_argument("--resume", action="store_true", help="keep scored clips in --out and run the rest")
    p.add_argument("--report", action="store_true", help="only rebuild the markdown from --out")
    p.add_argument("--rescore", action="store_true", help="regrade the stored transcripts (no model), then report")
    args = p.parse_args()
    if args.rescore:
        rescore(args.data, args.out)
    elif not args.report:
        run(args.data, args.out, args.model or ["base", "small"], args.resume, args.limit)
    rows = [json.loads(line) for line in args.out.read_text().splitlines() if line.strip()]
    args.md.write_text(report(rows))
    print(f"{len(rows)} rows scored; report in {args.md}")


if __name__ == "__main__":
    main()
