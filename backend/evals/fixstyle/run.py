"""Fix-style benchmark: does Thompson sampling find the kind of fix reviewers take, and how fast?

Offline and reproducible. Simulated reviewers per rule take each operation (replace, rewrite, delete) at a
hidden rate; each round one review proposes a fix with the operation the policy prefers and the reviewer
takes it or writes their own. Three policies:

- the model alone: the operation the fix model picks without a hint, here uniformly at random (on the
  live eval it varies by rule, so this is the uninformed baseline);
- greedy: always the best smoothed rate so far ((taken + 1) / (decided + 2), ties broken at random), so an
  untried operation starts at a half chance rather than at zero, which can still lock onto early luck;
- Thompson (prism/fixstyle.py): one draw from each operation's Beta posterior, highest wins.

Before MIN_DECIDED decided fixes on a rule, every policy falls back to the model alone, as production does.
Reported: share of fixes taken over 100 rounds per rule, and over the last 50, averaged over 200 runs.
This measures the policy, not the fix model: whether the hint changes what the model writes is the live
half (`evals/explain_and_fix.py`).

    .venv/bin/python -m evals.fixstyle.run
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from verytas.prism.fixstyle import MIN_DECIDED, OPERATIONS, FixStyle

# Hidden take rates per operation for three kinds of rule (what reviewers do with each operation).
RULES = {
    "a dig at rivals (rewrite keeps the offer)": {"replace": 0.35, "rewrite": 0.8, "delete": 0.45},
    "jargon (swap the words)": {"replace": 0.85, "rewrite": 0.6, "delete": 0.1},
    "a countdown (delete the line)": {"replace": 0.3, "rewrite": 0.55, "delete": 0.7},
}
ROUNDS = 100
RUNS = 200


def _simulate(rates: dict[str, float], policy: str, seed: int) -> list[bool]:
    world, choice = random.Random(seed), random.Random(seed + 1)
    style = FixStyle(rng=random.Random(seed + 2))
    taken: list[bool] = []
    for _ in range(ROUNDS):
        decided = sum(a + b for a, b in style.tally.get("R", {}).values())
        if policy == "model alone" or decided < MIN_DECIDED:
            op = choice.choice(OPERATIONS)
        elif policy == "greedy":
            row = style.tally["R"]
            rate = {o: (a + 1) / (a + b + 2) for o, (a, b) in row.items()}
            best = max(rate.values())
            op = choice.choice([o for o, r in rate.items() if r == best])
        else:
            style.chosen.clear()  # a new review, a new draw
            op = style.prefer("R")
        ok = world.random() < rates[op]
        style.record("R", op, ok)
        taken.append(ok)
    return taken


def run() -> str:
    lines = ["# Fix-style benchmark", "",
             f"Simulated reviewers, {ROUNDS} fixes per rule, averaged over {RUNS} runs. Share of fixes the reviewer "
             f"took (all rounds / last 50).", "",
             "| Rule (best operation) | Best possible | Model alone | Greedy | Thompson |", "|---|---|---|---|---|"]
    for name, rates in RULES.items():
        cells = []
        for policy in ("model alone", "greedy", "thompson"):
            runs = [_simulate(rates, policy, seed) for seed in range(RUNS)]
            every = sum(sum(r) for r in runs) / (RUNS * ROUNDS)
            late = sum(sum(r[-50:]) for r in runs) / (RUNS * 50)
            cells.append(f"{every:.0%} / {late:.0%}")
        lines.append(f"| {name} | {max(rates.values()):.0%} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("evals/results/fixstyle.md"))
    args = ap.parse_args()
    md = run()
    args.out.write_text(md)
    print(md)


if __name__ == "__main__":
    main()
