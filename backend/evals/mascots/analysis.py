"""Which of SAM's own signals (and which geometry against the artwork) predict a bad cut-out?

Part A of the mask-quality work. For every cached scene it computes the candidate signals for the box
mask, the truth quality of that mask (IoU with the generator's true mask), and whether fidelity raised an
alarm on it, then reports each signal's AUC for "this acceptable scene got a false alarm" and for "this
mask is bad" (IoU with the truth under 0.9).

    .venv/bin/python -m evals.mascots.analysis --data DIR --cache DIR [--save features.json]
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np

from evals.mascots.replay import Bench, auc, iou, run_policy
from verytas.media import maskgeom


def features(bench: Bench, case: dict, e: dict) -> dict:
    art = bench.refs[case["mascot"]][1]
    one = e["one"]["masks"][0]
    cands = [one, *e["three"]["masks"]]
    pair = [iou(a, b) for a, b in itertools.combinations(e["three"]["masks"], 2)]
    x0, y0, x1, y1 = e["box"]
    box_area = max(1.0, (x1 - x0) * (y1 - y0))
    f = {
        "one_iou": float(e["one"]["iou"][0]), "one_stab": float(e["one"]["stab"][0]),
        "three_iou_max": float(e["three"]["iou"].max()), "three_stab_max": float(e["three"]["stab"].max()),
        "three_iou_min": float(e["three"]["iou"].min()),
        # Agreement: how much the three alternative masks (and the single one) say the same thing.
        "agree_min": min(pair), "agree_mean": float(np.mean(pair)),
        "agree_one_vs_best": max(iou(one, m) for m in e["three"]["masks"]),
        "area_box": float(one.sum() / box_area),
        "truth_iou": iou(one, bench.truth(case)),
    }
    try:
        f["sil_one"] = maskgeom.similarity_iou(art, one)
        f["sil_best"] = max(maskgeom.similarity_iou(art, m) for m in cands)
    except ValueError:
        f["sil_one"] = f["sil_best"] = 0.0
    return f


def run(data: Path, cache: Path) -> list[dict]:
    from evals.mascots import policies

    bench = Bench(data, cache)
    base = {r["file"]: r for r in run_policy(bench, policies.baseline)}
    rows = []
    for case in bench.cases:
        e = bench.entry(case)
        if e is None:
            continue
        r = base[case["file"]]
        rows.append({**{k: case[k] for k in ("mascot", "variant", "expect", "file", "busy")},
                     **features(bench, case, e), "flagged": bool(r["differences"]),
                     "kinds": sorted({d["kind"] for d in r["differences"]})})
    return rows


SIGNALS = ["one_iou", "one_stab", "three_iou_max", "three_stab_max", "three_iou_min", "agree_min", "agree_mean",
           "agree_one_vs_best", "area_box", "sil_one", "sil_best"]


def report(rows: list[dict]) -> str:
    ok = [r for r in rows if r["expect"] == "ok"]
    busy = [r for r in ok if r["busy"]]
    out = [f"Acceptable scenes {len(ok)}: false alarms {sum(r['flagged'] for r in ok)} "
           f"(busy {sum(r['flagged'] for r in busy)}/{len(busy)})", "",
           "| Signal | AUC false alarm, all ok | busy only | AUC bad mask (IoU<0.9) |", "|---|---|---|---|"]
    for s in SIGNALS:
        def a(rs, label):
            pos = [-r[s] for r in rs if label(r)]  # low signal = bad, so negate: high score means trouble
            neg = [-r[s] for r in rs if not label(r)]
            return auc(pos, neg)
        fa = lambda r: r["flagged"]  # noqa: E731
        bad = lambda r: r["truth_iou"] < 0.9  # noqa: E731
        out.append(f"| {s} | {a(ok, fa):.3f} | {a(busy, fa):.3f} | {a(ok, bad):.3f} |")
    out.append(f"\nBad masks (truth IoU < 0.9) among acceptable: {sum(r['truth_iou'] < 0.9 for r in ok)}/{len(ok)}; "
               f"false alarms with a good mask: {sum(r['flagged'] and r['truth_iou'] >= 0.9 for r in ok)}")
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.mascots.analysis")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--save", type=Path)
    a = p.parse_args()
    rows = run(a.data, a.cache)
    if a.save:
        a.save.write_text(json.dumps(rows))
    print(report(rows))


if __name__ == "__main__":
    main()
