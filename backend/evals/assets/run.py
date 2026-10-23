"""Run the brand-artwork benchmark through production matching and findings, and score it.

Each kit's library (current logo, wordmark, app icon, pack front, retired logo, a competitor's logo) is
prepared once; every scene is matched against all of it, and the matches go through the same
`_asset_findings` a review runs, without the vision model, so the numbers are the pixel path's alone.

    .venv/bin/python -m evals.assets.run --data /tmp/assets --out evals/results/assets.jsonl
    .venv/bin/python -m evals.assets.run --report evals/results/assets.jsonl

The report gives, per artwork kind and per variant: how often correct use raised nothing (false alarms),
how often misuse raised the expected finding (catch rate) and what it was called instead when it wasn't,
and the time per scene.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

# Library kinds as a brand admin would register them, by benchmark artwork name.
KINDS = {"logo": "logo", "wordmark": "wordmark", "icon": "icon", "pack": "packaging", "retired": "logo",
         "competitor": "competitor"}
VISUAL = ("VIS-",)


def _library(data: Path, kit: str):
    from verytas.media import assets as asset_match
    from verytas.prism.agents import OfficialAsset

    lib = []
    for n, (which, kind) in enumerate(KINDS.items(), start=1):
        img = Image.open(data / f"{kit}_{which}.png")
        lib.append(OfficialAsset(n, f"{kit} {which}", kind, "full", False, img, asset_match.prepare(n, img), "",
                                 retired=which == "retired"))
    return lib


def _findings(lib, scene: Image.Image) -> tuple[list[tuple[str, str]], dict[str, bool]]:
    from tests.helpers import make_ctx, system_rule_views
    from verytas.media import assets as asset_match
    from verytas.prism import agents
    from verytas.prism.agents import AgentTree, ReviewRun
    from verytas.prism.governor import Governor
    from verytas.providers.offline import OfflineJudge, OfflineLLM

    rules = system_rule_views()
    run = ReviewRun(base=make_ctx("", rules), llm=OfflineLLM(), judge=OfflineJudge(), vision=OfflineLLM(),
                    governor=Governor(1, 1), tree=AgentTree(8, 10), rule_by_code={r.code: r for r in rules},
                    assets=lib, content_tier_rank=0, allow_cloud_vision=False, semantic_threshold=0.6,
                    ocr_min_confidence=0.8)
    node = run.tree.nodes.setdefault("a1", agents.AgentNode("a1", "image", "img", None, 0))
    feats = asset_match.scene_features(scene)
    matches = [asset_match.match(a.prepared, feats) for a in lib]
    agents._asset_findings(run, node, "img:x", {"image": "x"}, matches, None)
    found = {a.name.split(" ", 1)[1]: m.found for a, m in zip(lib, matches, strict=True)}
    return [(f.rule_code, f.title) for f in run.findings if f.rule_code.startswith(VISUAL)], found


def run(data: Path, out: Path, resume: bool = False, limit: int | None = None) -> None:
    manifest = json.loads((data / "manifest.json").read_text())
    done: set[str] = set()
    if resume and out.is_file():
        whole = []
        for line in out.read_text().splitlines():
            try:
                done.add(json.loads(line)["file"])
            except (ValueError, KeyError):
                continue  # a torn last line from a killed run: dropped, and its scene rerun
            whole.append(line + "\n")
        tmp = out.with_suffix(".tmp")
        tmp.write_text("".join(whole))
        tmp.replace(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    libraries: dict[str, list] = {}
    cases = [c for c in manifest["cases"] if c["file"] not in done][:limit]
    with out.open("a" if resume else "w") as fh:
        for n, case in enumerate(cases, start=1):
            lib = libraries.get(case["kit"]) or libraries.setdefault(case["kit"], _library(data, case["kit"]))
            t = time.perf_counter()
            got, found = _findings(lib, Image.open(data / case["file"]).convert("RGB"))
            row = {**case, "findings": got, "found": found, "seconds": round(time.perf_counter() - t, 3)}
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if n % 25 == 0:
                print(f"{n}/{len(cases)}", flush=True)


def report(path: Path) -> str:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        return "No scenes scored yet."

    def ok(r: dict) -> bool:
        return not r["findings"]

    def caught(r: dict) -> bool:
        return any(code == r["expect"] for code, _ in r["findings"])

    lines = [f"# Brand-artwork benchmark ({len(rows)} scenes, pixel path only)", ""]
    good = [r for r in rows if r["expect"] == "ok"]
    bad = [r for r in rows if r["expect"] != "ok"]
    lines += ["## Correct use: nothing should be raised", "",
              "| Artwork | Scenes | Found | False alarms |", "|---|---|---|---|"]
    by_asset = defaultdict(list)
    for r in good:
        by_asset[r["asset"] or "none (absent)"].append(r)
    for which, rs in sorted(by_asset.items()):
        seen = [r for r in rs if r["asset"]]
        found = f"{sum(r['found'].get(r['asset'], False) for r in seen) / len(seen):.0%}" if seen else "n/a"
        lines.append(f"| {which} | {len(rs)} | {found} | {sum(not ok(r) for r in rs) / len(rs):.0%} |")
    lines += ["", "| Variant | Scenes | False alarms | Most common false finding |", "|---|---|---|---|"]
    by_variant = defaultdict(list)
    for r in good:
        by_variant[r["variant"]].append(r)
    for variant, rs in by_variant.items():
        wrong = Counter(code for r in rs for code, _ in r["findings"])
        top = ", ".join(f"{c} ({k})" for c, k in wrong.most_common(2)) or "none"
        lines.append(f"| {variant} | {len(rs)} | {sum(not ok(r) for r in rs) / len(rs):.0%} | {top} |")
    lines += ["", "## Misuse: the expected finding should be raised", "",
              "| Misuse | Artwork | Scenes | Caught | Raised instead (when missed) |", "|---|---|---|---|---|"]
    groups = defaultdict(list)
    for r in bad:
        groups[(r["variant"], r["asset"])].append(r)
    for (variant, which), rs in sorted(groups.items()):
        instead = Counter(code for r in rs if not caught(r) for code, _ in r["findings"]) or Counter()
        missed_silent = sum(1 for r in rs if not caught(r) and not r["findings"])
        desc = ", ".join(f"{c} ({k})" for c, k in instead.most_common(2))
        desc = (desc + ", " if desc else "") + (f"nothing ({missed_silent})" if missed_silent else "")
        lines.append(f"| {variant} | {which} | {len(rs)} | {sum(caught(r) for r in rs) / len(rs):.0%} | "
                     f"{desc.strip(', ') or 'n/a'} |")
    secs = [r["seconds"] for r in rows]

    def share(n: int, of: list) -> str:
        return f"{n / len(of):.1%}" if of else "n/a"

    lines += ["", f"Overall: false alarms {share(sum(not ok(r) for r in good), good)} of {len(good)} correct "
              f"scenes; caught {share(sum(caught(r) for r in bad), bad)} of {len(bad)} misuses. "
              f"Time per scene (6 library assets): median {statistics.median(secs):.2f} s, "
              f"p95 {sorted(secs)[int(0.95 * (len(secs) - 1))]:.2f} s."]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path)
    ap.add_argument("--out", type=Path, default=Path("evals/results/assets.jsonl"))
    ap.add_argument("--report", type=Path)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    if args.report:
        text = report(args.report)
        args.report.with_suffix(".md").write_text(text + "\n")
        print(text)
        return
    if not args.data:
        ap.error("--data is required unless --report is given")
    run(args.data, args.out, args.resume, args.limit)


if __name__ == "__main__":
    main()
