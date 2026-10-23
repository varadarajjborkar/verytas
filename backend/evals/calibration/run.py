"""Calibration benchmark: does "how often reviewers agreed" predict the next decision better than raw certainty?

Reads a seeded showcase database (`python -m verytas.cli seed-showcase`). Decisions are replayed in time
order; each one in the held-out last 30% is predicted from the decisions before it in the same workspace:

- raw certainty: the finding's confidence as the checks produced it;
- base rate: the share of earlier decisions in the workspace that agreed;
- calibrated: prism/calibration.py fitted on the earlier decisions (raw certainty while too few exist).

Scored by Brier score (lower is better) and expected calibration error over ten bins, with a reliability
table: in each band of predicted agreement, how often reviewers actually agreed. The seeded reviewers
decide by persona, at a fixed acceptance rate per rule and blind to certainty, so on them the best a
predictor can do is learn those rates. A second run keeps the same findings and replaces the reviewers
with simulated ones who agree more often the surer the check was, but less often than it claims
(agreement = certainty cubed, an overconfident judge): there the certainty carries signal, and a
calibrator should beat both raw certainty and the base rate.

    .venv/bin/python -m evals.calibration.run --db /path/to/showcase.db
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

from verytas.checks.base import RawFinding
from verytas.prism.calibration import Calibration, agreed

BINS = 10


def _decisions(db: Path) -> list[tuple[int, str, bool, float, bool]]:
    con = sqlite3.connect(db)
    rows = con.execute("""
        select c.workspace_id, f.category, f.model is not null, f.confidence, d.action, d.reason_code
        from decisions d
        join findings f on f.id = d.finding_id
        join reviews rv on rv.id = f.review_id
        join content_versions v on v.id = rv.version_id
        join contents c on c.id = v.content_id
        where d.id in (select max(id) from decisions group by finding_id)
        order by d.created_at, d.id""").fetchall()
    out = []
    for ws, cat, modelled, conf, action, reason in rows:
        y = agreed(action, reason)
        if y is not None:
            out.append((ws, cat, bool(modelled), float(conf), y))
    return out


def _scores(pairs: list[tuple[float, bool]]) -> tuple[float, float, list[tuple[int, float, float]]]:
    brier = sum((p - y) ** 2 for p, y in pairs) / len(pairs)
    bins: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for p, y in pairs:
        bins[min(int(p * BINS), BINS - 1)].append((p, y))
    table, ece = [], 0.0
    for b in sorted(bins):
        got = bins[b]
        mean_p = sum(p for p, _ in got) / len(got)
        rate = sum(y for _, y in got) / len(got)
        ece += len(got) / len(pairs) * abs(mean_p - rate)
        table.append((b, mean_p, rate, len(got)))
    return brier, ece, table


def _overconfident(rows: list[tuple[int, str, bool, float, bool]], seed: int = 7) -> list:
    rng = random.Random(seed)
    return [(ws, cat, m, conf, rng.random() < conf ** 3) for ws, cat, m, conf, _ in rows]


def run(db: Path, held_out: float = 0.3) -> str:
    rows = _decisions(db)
    seeded = _replay(rows, held_out, "seeded reviewers")
    simulated = _replay(_overconfident(rows), held_out, "simulated reviewers (agreement = certainty cubed)")
    return "# Calibration benchmark\n\n" + seeded + "\n" + simulated


def _replay(rows: list[tuple[int, str, bool, float, bool]], held_out: float, title: str) -> str:
    cut = int(len(rows) * (1 - held_out))
    seen: dict[int, list[tuple[str, bool, float, bool]]] = defaultdict(list)
    preds: dict[str, list[tuple[float, bool]]] = {"raw certainty": [], "base rate": [], "calibrated": []}
    fitted = 0
    for i, (ws, cat, modelled, conf, y) in enumerate(rows):
        if i >= cut:
            before = seen[ws]
            rate = (sum(p[3] for p in before) + 1) / (len(before) + 2)
            cal = Calibration.from_points(before).of(
                RawFinding("p", cat, "t", "x", conf, "c", model="m" if modelled else None))
            fitted += cal is not None
            preds["raw certainty"].append((conf, y))
            preds["base rate"].append((rate, y))
            preds["calibrated"].append((cal["agree"] if cal else conf, y))
        seen[ws].append((cat, modelled, conf, y))

    n = len(rows) - cut
    lines = [f"## {title}", "",
             f"{len(rows)} decided findings from the seeded demo, replayed in time order; the last {n} are "
             f"predicted from the ones before them in the same workspace. The calibrated curve was available "
             f"for {fitted} of {n} (raw certainty otherwise).", "",
             "| Predictor | Brier (lower is better) | Calibration error (ECE) |", "|---|---|---|"]
    tables = {}
    for name, pairs in preds.items():
        brier, ece, table = _scores(pairs)
        tables[name] = table
        lines.append(f"| {name} | {brier:.3f} | {ece:.3f} |")
    for name in ("raw certainty", "calibrated"):
        lines += ["", f"Reliability, {name}: in each band of prediction, how often reviewers agreed.", "",
                  "| Predicted | Mean predicted | Reviewers agreed | Decisions |", "|---|---|---|---|"]
        for b, mean_p, rate, k in tables[name]:
            lines.append(f"| {b / BINS:.1f} to {(b + 1) / BINS:.1f} | {mean_p:.2f} | {rate:.2f} | {k} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("evals/results/calibration.md"))
    args = ap.parse_args()
    md = run(args.db)
    args.out.write_text(md)
    print(md)


if __name__ == "__main__":
    main()
