"""CLI: python -m blackbox run|report|arms  (run from the repo root with backend/.venv/bin/python)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import fields

from blackbox import report
from blackbox.runner import Config, campaign
from blackbox.store import Store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="blackbox", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run a campaign and write a report")
    for f in fields(Config):
        flag = "--" + f.name.replace("_", "-")
        if isinstance(f.default, bool):
            run.add_argument(flag, action=argparse.BooleanOptionalAction, default=f.default)
        else:
            run.add_argument(flag, type=type(f.default), default=f.default)
    rep = sub.add_parser("report", help="print the report for a run (default: latest)")
    rep.add_argument("--run", type=int)
    sub.add_parser("arms", help="show what the bandit has learned")
    args = ap.parse_args(argv)

    if args.cmd == "run":
        cfg = Config(**{f.name: getattr(args, f.name) for f in fields(Config)})
        run_id = asyncio.run(campaign(cfg))
        store = Store()
        path = report.write(store, run_id)
        print(report.render(store, run_id))
        print(f"report saved to {path}")
    elif args.cmd == "report":
        store = Store()
        run_id = args.run or store.last_run()
        if run_id is None:
            print("no finished runs yet")
            return 1
        print(report.render(store, run_id))
    else:
        store = Store()
        rows = sorted(store.arm_stats().items(), key=lambda kv: -(kv[1][1] + 1) / (kv[1][0] + 2))
        print(f"{'arm':40} {'trials':>6} {'fails':>6} {'fail rate':>9}")
        for arm, (t, f) in rows:
            print(f"{arm:40} {t:6} {f:6} {(f + 1) / (t + 2):9.2f}")

    # The harness must stay a black box: if anything pulled in the backend
    # package, its results can't be trusted to be independent.
    leaked = sorted(m for m in sys.modules if m == "verytas" or m.startswith("verytas."))
    if leaked:
        print(f"black-box violation: imported {leaked}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
