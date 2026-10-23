"""What if the image were enlarged before OCR? Not production code: a measurement to decide what to change.

`verytas.media.ocr.read` only ever shrinks (images over 2000 px); it never enlarges. The detector works on
the pixels it is given, so fine print a few pixels tall may simply be too small to find. Here each image is
upscaled 2x (Lanczos) before the production `read`, then scored exactly as in `evals.ocr.run`, next to the
production result for the same image:

    .venv/bin/python -m evals.ocr.whatif
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from PIL import Image

from evals.ocr.run import DEFAULT_DATA, HEIGHTS, RESULTS, pct, score, summarise


def run(data: Path, out: Path, factor: float, limit: int | None) -> None:
    cases = [json.loads(line) for line in (data / "cases.jsonl").read_text().splitlines() if line.strip()][:limit]
    with out.open("w") as fh:
        for case in cases:
            img = Image.open(data / case["file"]).convert("RGB")
            big = img.resize((round(img.width * factor), round(img.height * factor)), Image.LANCZOS)
            fh.write(json.dumps(score(case, big) | {"factor": factor}, ensure_ascii=False) + "\n")


def report(new: list[dict], old: list[dict], factor: float) -> str:
    ids = {r["id"] for r in new}
    old = [r for r in old if r["id"] in ids]
    md = [f"# OCR what-if: enlarge {factor:g}x before reading", "",
          "Production `read` on the same images, versus `read` on the image upscaled first (Lanczos). Same scoring "
          "as `ocr.md`. Time is per image, median.", "",
          "| Group | Images | CER production | CER enlarged | Critical production | Critical enlarged | "
          "Median s production | Median s enlarged |", "|---|---|---|---|---|---|---|---|"]

    def row(label: str, key) -> None:
        groups: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
        o = {r["id"]: r for r in old}
        for r in new:
            groups[key(r)].append((o[r["id"]], r))
        for g in sorted(groups):
            a, b = [x[0] for x in groups[g]], [x[1] for x in groups[g]]
            sa, sb = summarise(a), summarise(b)
            md.append(f"| {label}: {g} | {len(a)} | {pct(sa[0], sa[1])} | {pct(sb[0], sb[1])} | "
                      f"{pct(sa[4], sa[5])} ({sa[4]}/{sa[5]}) | {pct(sb[4], sb[5])} ({sb[4]}/{sb[5]}) | "
                      f"{statistics.median(sa[6]):.2f} | {statistics.median(sb[6]):.2f} |")

    row("all", lambda r: "images")
    for tag in ("size", "scale", "script", "contrast", "jpeg"):
        row(tag, lambda r, tag=tag: r["tags"][tag])
    md += ["", "Fine-print (legal) word recall by line height as stored, production and enlarged:", "",
           "| Height | Words | Production | Enlarged |", "|---|---|---|---|"]
    o = {r["id"]: r for r in old}
    for _, label in HEIGHTS:
        tot = [0, 0, 0]
        for r in new:
            px = r["tags"].get("legal_px", 0)
            if px and next(name for edge, name in HEIGHTS if px < edge) == label:
                tot[0] += r["roles"].get("legal", [0, 0])[1]
                tot[1] += o[r["id"]]["roles"].get("legal", [0, 0])[0]
                tot[2] += r["roles"].get("legal", [0, 0])[0]
        if tot[0]:
            md.append(f"| {label} | {tot[0]} | {pct(tot[1], tot[0])} | {pct(tot[2], tot[0])} |")
    return "\n".join(md) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.ocr.whatif")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--out", type=Path, default=RESULTS / "ocr_whatif.jsonl")
    p.add_argument("--md", type=Path, default=RESULTS / "ocr_whatif.md")
    p.add_argument("--factor", type=float, default=2.0)
    p.add_argument("--limit", type=int)
    p.add_argument("--report", action="store_true")
    args = p.parse_args()
    if not args.report:
        run(args.data, args.out, args.factor, args.limit)
    new = [json.loads(line) for line in args.out.read_text().splitlines() if line.strip()]
    old = [json.loads(line) for line in (RESULTS / "ocr.jsonl").read_text().splitlines() if line.strip()]
    for r in new + old:  # same derived tag the main report uses
        r["tags"]["fine_print"] = "yes" if r["roles"].get("legal", [0, 0])[1] else "no"
    args.md.write_text(report(new, old, args.factor))
    print(f"{len(new)} images; report in {args.md}")


if __name__ == "__main__":
    main()
