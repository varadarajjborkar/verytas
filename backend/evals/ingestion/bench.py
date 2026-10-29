"""Runs both pipelines on every corpus file and scores them against corpus/truth.json."""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

# argv[1]: a work folder holding corpus/ (from gen.py) and .venv/ with LlamaIndex installed (see README).
L = Path(sys.argv[1]).resolve()
C = L / "corpus"
truth = json.loads((C / "truth.json").read_text())
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
PIPES = {
    "ours": [str(BACKEND / ".venv/bin/python"), str(HERE / "ours_run.py")],
    "llamaindex": [str(L / ".venv/bin/python"), str(HERE / "li_run.py")],
}
CWD = {"ours": str(BACKEND), "llamaindex": str(L)}
def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def run(pipe, f, reps):
    t = time.perf_counter()
    try:
        p = subprocess.run(
            ["/usr/bin/time", "-l", *PIPES[pipe], str(C / f), str(reps)],
            cwd=CWD[pipe],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timed out after 180 s", "wall": 180}
    rss = re.search(r"(\d+)\s+maximum resident set size", p.stderr)
    out = {"wall": time.perf_counter() - t, "rss_mb": int(rss.group(1)) / 2**20 if rss else None}
    try:
        out.update(json.loads(p.stdout.strip().splitlines()[-1]))
    except Exception:
        out["error"] = (p.stderr.strip().splitlines() or ["no output"])[-1][:160]
    return out


def row_found(row, out):
    cells = [norm(str(c)) for c in row]
    if any([norm(x) for x in r] == cells for t in out.get("tables", []) for r in t["rows"]):
        return True
    for line in out.get("text", "").splitlines():
        text = norm(line)
        pos = 0
        for c in cells:
            # pandas writes 3 as "3.0": accept a trailing .0 on whole numbers
            m = re.search(re.escape(c) + (r"(\.0)?\b" if c.isdigit() else ""), text[pos:])
            if not m:
                break
            pos += m.end()
        else:
            return True
    return False


results = {}
for f, t in truth["files"].items():
    for pipe in PIPES:
        o = run(pipe, f, 5)
        r = {"ms": o.get("ms"), "rss_mb": o.get("rss_mb"), "error": o.get("error")}
        text = norm(o.get("text", ""))
        if "sentences" in t:
            sents = t["sentences"]
            r["sentences"] = f"{sum(norm(s['text']) in text for s in sents)}/{len(sents)}"
            located = [s for s in sents if "page" in s]
            if located:
                ok = sum(
                    any(norm(s["text"]) in norm(u["text"]) and u.get("loc") == s["page"] for u in o.get("units", []))
                    for s in located
                )
                r["right_page_or_slide"] = f"{ok}/{len(located)}"
        if "tables" in t:
            rows = [row for tb in t["tables"] for row in tb["rows"]]
            r["table_rows_intact"] = f"{sum(row_found(row, o) for row in rows)}/{len(rows)}"
        if "cells" in t:
            have = {(c["sheet"], c["addr"]): norm(c["value"]) for c in o.get("cells", [])}
            r["cells_with_address"] = (
                f"{sum(have.get((c['sheet'], c['addr'])) == norm(c['value']) for c in t['cells'])}/{len(t['cells'])}"
            )
        if t.get("scanned"):
            r["says_it_is_a_scan"] = bool(o.get("notes")) and any("scan" in n.lower() for n in o["notes"])
            r["chars"] = len(o.get("text", ""))
        results.setdefault(f, {})[pipe] = r
for f, canary in truth["hostile"].items():
    for pipe in PIPES:
        o = run(pipe, f, 1)
        results.setdefault(f, {})[pipe] = {
            "wall_s": round(o.get("wall", 0), 1),
            "rss_mb": round(o["rss_mb"]) if o.get("rss_mb") else None,
            "error": o.get("error"),
            "chars": len(o.get("text", "")),
            "leaked_canary": bool(canary) and canary in o.get("text", ""),
        }
(L / "results.json").write_text(json.dumps(results, indent=1))  # raw numbers, beside the corpus
for f, by in results.items():
    print("==", f)
    for pipe, r in by.items():
        print(f"  {pipe:11}", {k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items() if v is not None})
