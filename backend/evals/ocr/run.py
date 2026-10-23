"""Run production OCR over the benchmark images and score it.

Each image goes through `verytas.media.ocr.read`, the function reviews call, so the numbers are
what a review sees (including its low-confidence noise filter and reading order):

    .venv/bin/python -m evals.ocr.run --data /private/tmp/.../scratchpad/ocrbench
    .venv/bin/python -m evals.ocr.run --report          # rebuild ocr.md from ocr.jsonl

How it scores, per image:
- CER: character edit distance between the drawn lines (top to bottom, joined) and the OCR text, both
  NFKC, case-folded and with all whitespace removed (so a missed line break costs nothing; spacing is
  scored by WER). Punctuation, digits and currency signs are kept: they matter to the checks.
- WER: the same on whitespace tokens, case-folded, sentence punctuation trimmed from word edges.
- Critical tokens (price, percent, date, URL, phone, hashtag, brand): read exactly when the token, after
  the same normalisation, appears in the OCR text. Exact means every digit and symbol; case is ignored.
- Role recall: share of the truth words of each kind of line (legal, headline...) found in the output,
  order ignored, so a fine-print line can be judged on its own.
Pooled ("micro") figures sum edits and lengths over images, so long images weigh more.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

from evals.ocr.metrics import bag_recall, cer, squash, substitutions, wer

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
DEFAULT_DATA = Path("/private/tmp/claude-502/-Users-varadarajborkar-praj-code/"
                    "298965cb-f1e3-424a-8f01-ca8c15eeb018/scratchpad/ocrbench")
TAG_ORDER = ["script", "fine_print", "size", "contrast", "background", "angle", "jpeg", "scale", "font", "head_font",
             "template", "coloured_text", "shadow"]


def load_done(out: Path) -> set[str]:
    """Keep the rows already scored; a run killed mid-write leaves a torn last line, which is dropped."""
    done: set[str] = set()
    whole = []
    for line in out.read_text().splitlines():
        try:
            done.add(json.loads(line)["id"])
        except (ValueError, KeyError):
            continue
        whole.append(line + "\n")
    tmp = out.with_suffix(".tmp")
    tmp.write_text("".join(whole))
    tmp.replace(out)  # one step: a crash leaves the old file, never a half-written one
    return done


def score(case: dict, img: Image.Image) -> dict:
    from verytas.media import ocr

    t = time.perf_counter()
    res = ocr.read(img)
    seconds = time.perf_counter() - t
    got = res.text
    truth = " ".join(case["lines"])
    ce, cn = cer(truth, got)
    we, wn = wer(truth, got)
    # The production filter drops low-confidence lines; what would reading them too have changed?
    ce2, _ = cer(truth, " ".join(ln.text for ln in ocr._reading_order(res.lines + res.noise)))
    flat = squash(got)
    crit = [dict(c, ok=squash(c["t"]) in flat) for c in case["critical"]]
    # Lines that were present in the OCR text are what "nearest word" can be matched against.
    ocr_words = got.split()
    for c in crit:
        if not c["ok"] and ocr_words:
            c["got"] = max(ocr_words, key=lambda w: SequenceMatcher(None, squash(c["t"]), squash(w)).ratio())
    roles: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in case["roles"]:
        found, total = bag_recall(r["text"], got)
        roles[r["role"]][0] += found
        roles[r["role"]][1] += total
    return {
        "id": case["id"], "file": case["file"], "tags": case["tags"], "truth": case["lines"],
        "ocr": [ln.text for ln in res.lines], "noise_lines": [ln.text for ln in res.noise],
        "cer_edits": ce, "cer_len": cn, "cer_edits_with_noise": ce2, "wer_edits": we, "wer_len": wn,
        "critical": crit, "roles": roles, "seconds": round(seconds, 3), "confidence": round(res.confidence, 3),
    }


def run(data: Path, out: Path, resume: bool, limit: int | None) -> None:
    cases = [json.loads(line) for line in (data / "cases.jsonl").read_text().splitlines() if line.strip()]
    if limit:
        cases = cases[:limit]
    done = load_done(out) if resume and out.is_file() else set()
    out.parent.mkdir(parents=True, exist_ok=True)
    from verytas.media import ocr

    ocr.read(Image.new("RGB", (200, 80), "white"))  # load the models before the first timed image
    t0 = time.perf_counter()
    with out.open("a" if resume else "w") as fh:
        for n, case in enumerate(cases, 1):
            if case["id"] in done:
                continue
            row = score(case, Image.open(data / case["file"]).convert("RGB"))
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            if n % 20 == 0:
                print(f"{n}/{len(cases)} images, {time.perf_counter() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------------------------------ report

def pct(a: float, b: float) -> str:
    return f"{100 * a / b:.1f}%" if b else "n/a"


def summarise(rows: list[dict]) -> tuple:
    ce, cn = sum(r["cer_edits"] for r in rows), sum(r["cer_len"] for r in rows)
    we, wn = sum(r["wer_edits"] for r in rows), sum(r["wer_len"] for r in rows)
    crit = [c for r in rows for c in r["critical"]]
    secs = sorted(r["seconds"] for r in rows)
    return ce, cn, we, wn, sum(c["ok"] for c in crit), len(crit), secs


def table(rows_by: dict[str, list[dict]], order: list[str] | None = None) -> list[str]:
    out = ["| Group | Images | CER | WER | Critical read exactly | Median s |", "|---|---|---|---|---|---|"]
    for key in order or sorted(rows_by):
        rs = rows_by.get(key)
        if not rs:
            continue
        ce, cn, we, wn, ok, nc, secs = summarise(rs)
        out.append(f"| {key} | {len(rs)} | {pct(ce, cn)} | {pct(we, wn)} | {pct(ok, nc)} ({ok}/{nc}) | "
                   f"{statistics.median(secs):.2f} |")
    return out


ORDERS = {
    "size": ["tiny", "small", "medium", "large"], "contrast": ["high", "medium", "low"],
    "background": ["flat", "gradient", "photo", "shapes"], "angle": ["0", "1-3", "4-8"],
    "jpeg": ["png", "q90", "q70", "q40", "q20"], "scale": ["100%", "50%", "30%"],
    "script": ["latin", "hinglish", "devanagari"],
}
HEIGHTS = [(8, "< 8 px"), (10, "8 to 10 px"), (12, "10 to 12 px"), (16, "12 to 16 px"), (10**9, ">= 16 px")]
NOTES = {
    "size": "smallest non-legal line in the image, in pixels as stored: tiny < 14, small < 22, medium < 44, large",
    "contrast": "median WCAG contrast ratio of text against the pixels under it: high >= 7, medium 3 to 7, low < 3",
    "angle": "degrees of rotation of the whole layout",
    "jpeg": "png is lossless; qN is JPEG quality N",
    "scale": "the image downscaled to this share of its drawn size before saving",
    "font": "body font class (headline class is `head_font`)",
}


def report(rows: list[dict]) -> str:
    for r in rows:  # derived tag: fine-print lines are tiny by design and dominate the misses
        r["tags"]["fine_print"] = "yes" if r["roles"].get("legal", [0, 0])[1] else "no"
    n = len(rows)
    ce, cn, we, wn, ok, nc, secs = summarise(rows)
    cer_mean = statistics.mean(r["cer_edits"] / max(1, r["cer_len"]) for r in rows)
    cer_med = statistics.median(r["cer_edits"] / max(1, r["cer_len"]) for r in rows)
    ce2 = sum(r["cer_edits_with_noise"] for r in rows)
    md = [
        "# OCR benchmark", "",
        f"Production OCR (`verytas.media.ocr.read`, RapidOCR PP-OCR on CPU) over {n} generated marketing images with "
        "known text. Generator: `evals/ocr/generate.py` (seeded; Devanagari shaped by pango). Scorer: "
        "`evals/ocr/run.py`.", "",
        "Method: CER is character edit distance over NFKC, case-folded text with all whitespace removed (spacing "
        "is WER's job); punctuation, digits and currency signs are kept. WER is on whitespace tokens with "
        "sentence punctuation trimmed at word edges. A critical token (price, percent, date, URL, phone, hashtag, "
        "brand) counts as read when it appears exactly, ignoring case and spacing. Figures are pooled over all "
        "characters or tokens unless stated.", "",
        "## Overall", "",
        "| Images | CER (pooled) | CER (mean / median per image) | WER | Critical tokens read exactly | "
        "Time p50 / p95 per image |", "|---|---|---|---|---|---|",
        f"| {n} | {pct(ce, cn)} | {100 * cer_mean:.1f}% / {100 * cer_med:.1f}% | {pct(we, wn)} | "
        f"{pct(ok, nc)} ({ok}/{nc}) | {statistics.median(secs):.2f}s / {secs[int(0.95 * (len(secs) - 1))]:.2f}s |", "",
        f"Reading the low-confidence lines the filter drops as well would give a pooled CER of {pct(ce2, cn)} "
        f"(filter on: {pct(ce, cn)}).", "",
    ]
    for tag in TAG_ORDER:
        by: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by[str(r["tags"][tag]).lower() if isinstance(r["tags"][tag], bool) else str(r["tags"][tag])].append(r)
        md += [f"### By {tag}", ""]
        md += [f"_{NOTES[tag]}_", ""] if tag in NOTES else []
        md += table(by, ORDERS.get(tag)) + [""]

    kinds: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        for c in r["critical"]:
            kinds[c["kind"]].append(c)
    md += ["## Critical tokens by kind", "", "| Kind | Tokens | Read exactly |", "|---|---|---|"]
    for k, cs in sorted(kinds.items()):
        md.append(f"| {k} | {len(cs)} | {pct(sum(c['ok'] for c in cs), len(cs))} |")
    md += ["", "Critical tokens by kind and script:", "",
           "| Kind | latin | hinglish | devanagari |", "|---|---|---|---|"]
    for k in sorted(kinds):
        cells = []
        for s in ("latin", "hinglish", "devanagari"):
            cs = [c for r in rows if r["tags"]["script"] == s for c in r["critical"] if c["kind"] == k]
            cells.append(f"{pct(sum(c['ok'] for c in cs), len(cs))} ({len(cs)})" if cs else "-")
        md.append(f"| {k} | " + " | ".join(cells) + " |")

    # Prices: the rupee sign is the part most likely to be lost, so the amount is scored on its own too.
    md += ["", "Prices by how they were written (amount = digits only, symbol ignored):", "",
           "| Written as | Tokens | Whole token exact | Amount exact |", "|---|---|---|---|"]
    for label, test in (("rupee sign", lambda t: t.startswith("₹")), ("Rs.", lambda t: t.startswith("Rs"))):
        cs = [c for k in ("price",) for c in kinds[k] if test(c["t"])]
        flats = {id(c): c for c in cs}
        amt = 0
        for r in rows:
            flat = squash(" ".join(r["ocr"]))
            for c in r["critical"]:
                if id(c) in flats and squash(c["t"].lstrip("₹Rs.")) in flat:
                    amt += 1
        md.append(f"| {label} | {len(cs)} | {pct(sum(c['ok'] for c in cs), len(cs))} | {pct(amt, len(cs))} |")
    dev = [r for r in rows if r["tags"]["script"] == "devanagari"]
    if dev:
        chars = "".join("".join(r["ocr"]) for r in dev)
        cjk = sum("\u2e80" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" for ch in chars)
        real = sum("\u0900" <= ch <= "\u097f" for ch in chars)
        md += ["", f"Devanagari images: {len(chars)} characters came back, {real} of them Devanagari and {cjk} CJK. "
               "The model has no Devanagari vocabulary: Hindi words are mostly dropped, and the rest comes back as "
               "Latin or CJK look-alikes, often glued to the digits beside them (for example 'H市2,999' for '₹2,999')."]

    roles: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        for k, (f, t) in r["roles"].items():
            roles[k][0] += f
            roles[k][1] += t
    md += ["", "## Word recall by kind of line (order ignored)", "", "| Line | Words | Found |", "|---|---|---|"]
    for k, (f, t) in sorted(roles.items(), key=lambda kv: kv[1][0] / kv[1][1]):
        md.append(f"| {k} | {t} | {pct(f, t)} |")
    legal = defaultdict(lambda: [0, 0])
    for r in rows:
        # legal lines by their stored pixel height, whatever the rest of the image looks like
        px = r["tags"].get("legal_px", 0)
        if px:
            b = next(name for edge, name in HEIGHTS if px < edge)
            legal[b][0] += r["roles"].get("legal", [0, 0])[0]
            legal[b][1] += r["roles"].get("legal", [0, 0])[1]
    md += ["", "Fine-print (legal) word recall by line height as stored:", "",
           "| Height | Words | Found |", "|---|---|---|"]
    for _, b in HEIGHTS:
        if legal[b][1]:
            md.append(f"| {b} | {legal[b][1]} | {pct(*legal[b])} |")

    # Failure patterns: what the misread critical tokens turned into.
    missed = [(r, c) for r in rows for c in r["critical"] if not c["ok"]]
    conf: Counter = Counter()
    for _, c in missed:
        if c.get("got"):
            conf.update(substitutions(squash(c["t"]), squash(c["got"])))
    md += ["", "## Failure patterns", "", f"{len(missed)} of {nc} critical tokens were not read exactly.", ""]
    md += ["Most common character edits inside near-miss critical tokens "
           "(truth to read-as; blank is a missing or extra character):", ""]
    md += ["| Truth | Read as | Count |", "|---|---|---|"]
    for (a, b), k in conf.most_common(12):
        md.append(f"| `{a or '(none)'}` | `{b or '(none)'}` | {k} |")
    md += ["", "Misread critical tokens (truth, nearest OCR word, image conditions):", ""]
    md += ["| Kind | Truth | Read as | Image |", "|---|---|---|---|"]
    shown: Counter = Counter()
    for r, c in sorted(missed, key=lambda rc: rc[1]["kind"]):
        if shown[c["kind"]] >= 8:  # a spread across kinds; every miss is in ocr.jsonl
            continue
        shown[c["kind"]] += 1
        t = r["tags"]
        md.append(f"| {c['kind']} | `{c['t']}` | `{c.get('got', '(nothing)')}` | {r['id']}: {t['script']}, "
                  f"{t['size']}, {t['contrast']} contrast, {t['background']}, {t['jpeg']}, {t['scale']}, "
                  f"angle {t['angle']} |")

    worst = sorted(rows, key=lambda r: r["cer_edits"] / max(1, r["cer_len"]), reverse=True)[:8]
    md += ["", "## Worst images by CER", ""]
    for r in worst:
        t = r["tags"]
        md += [f"- {r['id']} CER {pct(r['cer_edits'], r['cer_len'])}: {t['script']}, size {t['size']}, "
               f"{t['contrast']} contrast ({t['contrast_ratio']}), {t['background']}, {t['jpeg']}, "
               f"scale {t['scale']}, angle {t['angle']}",
               f"  - truth: {' / '.join(r['truth'])[:260]}",
               f"  - read:  {' / '.join(r['ocr'])[:260] or '(nothing)'}"]
    return "\n".join(md) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.ocr.run")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--out", type=Path, default=RESULTS / "ocr.jsonl")
    p.add_argument("--md", type=Path, default=RESULTS / "ocr.md")
    p.add_argument("--limit", type=int)
    p.add_argument("--resume", action="store_true", help="keep scored images in --out and run the rest")
    p.add_argument("--report", action="store_true", help="only rebuild the markdown from --out")
    args = p.parse_args()
    if not args.report:
        run(args.data, args.out, args.resume, args.limit)
    rows = [json.loads(line) for line in args.out.read_text().splitlines() if line.strip()]
    args.md.write_text(report(rows))
    print(f"{len(rows)} images scored; report in {args.md}")


if __name__ == "__main__":
    main()
