"""Would a quality gate on the cut-out pay for itself? The sweep that said no.

A gate would send a cut-out to "unsure" when SAM's mask is unstable or its silhouette is far from the
artwork's. Not adopted: every setting that halved false alarms also sent dozens of real defects to "unsure"
(evals/results/mascots.md). Both thresholds trade the same two things: false alarms removed on
acceptable scenes, and real defects no longer named. This sweeps a grid over the cached scenes, with the
fidelity result of the reclaimed mask as the thing being gated, and prints for each setting

- false alarms left on acceptable scenes, and how many acceptable scenes went unsure instead;
- per defect variant, scenes named right before and after (the never-regress figures).

    .venv/bin/python -m evals.mascots.gate --data DIR --cache DIR [--manifest poses.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.mascots import analysis, policies
from evals.mascots.replay import WANT, Bench, run_policy

STABS = [0.0, 0.80, 0.85, 0.90, 0.93, 0.95, 0.97]
FITS = [0.0, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]


def collect(bench: Bench) -> list[dict]:
    """One record per scene: its signals, and fidelity under the reclaim policy."""
    feats = {r["file"]: r for r in analysis.run(bench)}
    rows = []
    for r in run_policy(bench, policies.reclaim):
        if not r.get("found"):
            continue
        f = feats[r["file"]]
        named = None
        if r["expect"].startswith("defect:"):
            named = any(d["kind"] in WANT[r["expect"].split(":")[1]] for d in r["differences"])
        rows.append({"variant": r["variant"], "expect": r["expect"], "busy": r["busy"], "file": r["file"],
                     "flagged": bool(r["differences"]), "named": named, "stab": f["one_stab"],
                     "fit": f["sil_best"], "fit_one": f["sil_one"], "truth_iou": f["truth_iou"]})
    return rows


def sweep(rows: list[dict]) -> str:
    ok = [r for r in rows if r["expect"] == "ok"]
    defects = [r for r in rows if r["expect"].startswith("defect:")]
    variants = sorted({r["variant"] for r in defects})
    base = {v: sum(bool(r["named"]) for r in defects if r["variant"] == v) for v in variants}
    out = ["| Stability >= | Fit >= | False alarms | Unsure (ok) | Unsure (defect) | " +
           " | ".join(f"{v} lost" for v in variants) + " |", "|" + "---|" * (5 + len(variants))]
    for s in STABS:
        for fit in FITS:
            unsure = lambda r, s=s, fit=fit: r["stab"] < s or r["fit"] < fit  # noqa: E731
            fa = sum(r["flagged"] and not unsure(r) for r in ok)
            lost = {v: sum(bool(r["named"]) and unsure(r) for r in defects if r["variant"] == v) for v in variants}
            out.append(f"| {s:.2f} | {fit:.2f} | {fa}/{len(ok)} | {sum(unsure(r) for r in ok)} | "
                       f"{sum(unsure(r) for r in defects)} | " + " | ".join(str(lost[v]) for v in variants) + " |")
    out.append("\nNamed right without a gate: " + ", ".join(f"{v} {n}" for v, n in base.items()))
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.mascots.gate")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--manifest", default="manifest.json")
    p.add_argument("--save", type=Path, help="write the per-scene records here")
    p.add_argument("--load", type=Path, help="read records saved earlier instead of recomputing")
    a = p.parse_args()
    rows = json.loads(a.load.read_text()) if a.load else collect(Bench(a.data, a.cache, a.manifest))
    if a.save:
        a.save.write_text(json.dumps(rows))
    print(sweep(rows))


if __name__ == "__main__":
    main()
