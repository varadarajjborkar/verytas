"""Replay the mascot benchmark from the cache of model outputs: fidelity and the mask decisions are
recomputed, the models are not run, so a change to either is measured in seconds.

    .venv/bin/python -m evals.mascots.replay --data DIR --cache DIR [--policy production] [--manifest poses.json]

A *policy* turns a scene's cached outputs into the cut-out that fidelity sees (or says it is not sure).
`baseline` is what the worker did before the mask-quality work (one box-prompted mask, trusted always);
`settled` is the production logic, `verytas.media.maskcheck.judge`. Reports the same tables as run.py plus the
busy and plain split of false alarms, and the never-regress figures.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from evals.mascots.cache import load
from verytas.media.fidelity import compare, official_reference
from verytas.media.maskcheck import judge

cv2.setNumThreads(0)  # OpenCV's pool is not fork-safe on macOS, and these images are small

OK_VARIANTS = ["plain", "busy", "small", "rotated", "jpeg", "redrawn"]
WANT = {"colour": {"colour_missing", "colour_new"}, "parts": {"parts"}, "shape": {"shape"}}


def auc(pos: list[float], neg: list[float]) -> float:
    """P(a positive scores above a negative), ties half: rank-sum form, so 4,000 pairs cost nothing."""
    if not pos or not neg:
        return float("nan")
    p, n = np.asarray(pos, float), np.asarray(neg, float)
    wins = (p[:, None] > n[None, :]).sum() + 0.5 * (p[:, None] == n[None, :]).sum()
    return float(wins / (len(p) * len(n)))


def iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0


class Bench:
    """The scenes, their official artwork and cached SAM outputs, loaded once."""

    def __init__(self, data: Path, cache: Path, manifest: str = "manifest.json") -> None:
        self.data, self.cache = data, cache
        # Only scenes already cached, so a half-built cache can be analysed (it holds whole mascots).
        self.cases = [c for c in json.loads((data / manifest).read_text())["cases"]
                      if (cache / f"{c['file']}.npz").is_file()]
        self.refs = {m: official_reference(Image.open(data / f"{m}_official.png"))
                     for m in sorted({c["mascot"] for c in self.cases})}
        self._scene: dict[str, np.ndarray] = {}

    def rgb(self, case: dict) -> np.ndarray:
        return np.asarray(Image.open(self.data / case["file"]).convert("RGB"))

    def truth(self, case: dict) -> np.ndarray:
        return np.asarray(Image.open(self.data / f"{case['mascot']}_{case['variant']}_truth.png")) > 127

    def entry(self, case: dict) -> dict | None:
        return load(self.cache, case["file"])


# A policy gets (bench, case, cache entry) and returns (mask or None, status); status "unsure" means the
# mask was not trusted and fidelity must not speak.
Policy = Callable[[Bench, dict, dict], tuple[np.ndarray | None, str]]


def _one(bench: Bench, policy: Policy, case: dict) -> dict:
    e = bench.entry(case)
    row = dict(case)
    if e is None:
        row["found"] = False
        return row
    mask, status = policy(bench, case, e)
    row |= {"found": True, "status": status, "differences": []}
    if mask is not None and mask.any() and status != "unsure":
        try:
            ref = bench.refs[case["mascot"]]
            fid = judge(ref, bench.rgb(case), mask) if status == "judge" else compare(ref, (bench.rgb(case), mask))
            row["differences"] = [{"kind": d.kind, "text": d.text} for d in fid.differences]
        except ValueError:
            row["status"] = "toosmall"
    return row


def run_policy(bench: Bench, policy: Policy, only: set[str] | None = None) -> list[dict]:
    """Fidelity for every cached scene under a policy. One process on purpose: the cache makes a replay
    take a minute or two, and forking after OpenCV has started its thread pool crashes on macOS."""
    return [_one(bench, policy, c) for c in bench.cases if not only or c["variant"] in only]


def tables(rows: list[dict]) -> str:
    found = [r for r in rows if r.get("found")]
    by: dict[str, list[dict]] = defaultdict(list)
    for r in found:
        by[r["variant"]].append(r)
    out = ["| Variant | Expect | Scenes | Flagged | Named right | Not sure |", "|---|---|---|---|---|---|"]
    for variant, rs in sorted(by.items(), key=lambda kv: (kv[1][0]["expect"], kv[0])):
        expect = rs[0]["expect"]
        flagged = sum(bool(r["differences"]) for r in rs)
        unsure = sum(r["status"] == "unsure" for r in rs)
        if expect.startswith("defect:"):
            kinds = WANT[expect.split(":")[1]]
            right = sum(any(d["kind"] in kinds for d in r["differences"]) for r in rs)
            named = f"{right}/{len(rs)}"
        else:
            named = "-"
        out.append(f"| {variant} | {expect} | {len(rs)} | {flagged}/{len(rs)} | {named} | {unsure} |")
    ok = [r for r in found if r["expect"] == "ok"]
    busy = [r for r in ok if r["busy"]]
    plain = [r for r in ok if not r["busy"]]

    def fa(rs):
        return f"{sum(bool(r['differences']) for r in rs)}/{len(rs)}"

    out.append(f"\nFalse alarms on acceptable variants: {fa(ok)} (busy background {fa(busy)}, plain {fa(plain)})")
    return "\n".join(out)


def main() -> None:
    from evals.mascots import policies

    p = argparse.ArgumentParser(prog="evals.mascots.replay")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--policy", default="baseline")
    p.add_argument("--manifest", default="manifest.json", help="poses.json replays the posed scenes")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    bench = Bench(a.data, a.cache, a.manifest)
    rows = run_policy(bench, getattr(policies, a.policy))
    print(tables(rows))
    if a.out:
        a.out.write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    main()
