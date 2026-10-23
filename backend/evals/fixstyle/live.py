"""Does a <prefer> hint change the operation the live fix model writes? The live half of evals/fixstyle.

The explain-and-fix cases (claims excluded: they are never fixed) go through the production fix path
three times: no hint, every rule preferring rewrite, every rule preferring replace (as if reviewers had
taken six of six). Counted: the operation each first proposal used, and how many passed the fix gate.
No repair round, so the gate's answer is the hint's alone. Calls Ollama Cloud.

    .venv/bin/python -m evals.fixstyle.live
"""
import asyncio
import collections
import json
import sys
from pathlib import Path

from evals.explain_and_fix import CONFIDENTIAL, finding, load_cases
from verytas.config import Settings
from verytas.prism import suggest
from verytas.prism.fixstyle import FixStyle
from verytas.prism.orchestrator import Prism
from verytas.security.redaction import Redactor


class Spy:
    """Records each fix's operation as the model wrote it, before any gate."""
    def __init__(self, llm): self.llm, self.name, self.ops = llm, llm.name, {}
    async def run(self, task):
        out = await self.llm.run(task)
        for fx in getattr(out, "fixes", []):
            self.ops.setdefault(task.name, []).append(fx.action.strip().lower())
        return out

async def condition(prefer):
    cases, rules = load_cases()
    cases = [c for c in cases if c["rule_code"] != "CLAIM-UNSUPPORTED"]
    prism = Prism(Settings(), None)
    judge, llm, _, _ = prism.guarded_providers(Redactor(CONFIDENTIAL))
    spy = Spy(llm)
    style = None
    if prefer:
        style = FixStyle(seed=1)
        for c in cases:
            code = finding(c).rule_code
            for _ in range(6):
                style.record(code, prefer, True)
    found = [finding(c) for c in cases]
    for i in range(0, len(found), 6):
        try:
            await suggest.explain_and_fix(found[i:i+6], rules, spy, judge, CONFIDENTIAL, repair=False, style=style)
        except Exception as exc:
            print("batch failed", exc, file=sys.stderr)
    first = spy.ops.get("explain_and_fix", [])
    passed = sum(1 for f in found if f.suggestion)
    kept = collections.Counter(f.suggestion.action for f in found if f.suggestion)
    return {"prefer": prefer, "cases": len(found), "written": dict(collections.Counter(first)),
            "passed_gate": passed, "passed_by_op": dict(kept)}

async def main() -> list[dict]:
    rows = []
    for p in (None, "rewrite", "replace"):
        rows.append(await condition(p))
        print(json.dumps(rows[-1]), flush=True)
    return rows


def report(rows: list[dict]) -> str:
    lines = ["# Fix-style hint, live", "",
             f"{rows[0]['cases']} fix cases through the production path, no repair round.", "",
             "| Hint | Operations written (first proposals) | Passed the fix gate |", "|---|---|---|"]
    for r in rows:
        ops = ", ".join(f"{k} {v}" for k, v in sorted(r["written"].items(), key=lambda kv: -kv[1]))
        lines.append(f"| {r['prefer'] or 'none'} | {ops} | {r['passed_gate']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    Path("evals/results/fixstyle_live.md").write_text(report(asyncio.run(main())))
