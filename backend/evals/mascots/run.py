"""Run the mascot benchmark through the vision chain and score it.

For every scene: find the character from a text prompt (Grounding DINO), cut it out (SAM2), compare
the cut-out's likeness with every official artwork (DINOv2), and check fidelity against its own
(media.fidelity). Needs the vision environment (backend/.venv-vision) and the SAM2 checkpoint:

    .venv-vision/bin/python -m evals.mascots.run --data /tmp/mascots --out evals/results/mascots.jsonl
    .venv-vision/bin/python -m evals.mascots.run --report evals/results/mascots.jsonl

The report says, from data rather than one example:
- detection: how often the character is found, and how well the box fits (IoU with the truth);
- identity: likeness of genuine pairs against impostors (other mascots and near-twins), the threshold
  that separates them best, and the error rates at it;
- fidelity: false alarms on acceptable variants, and the catch and naming rate per defect.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

# The production chain (verytas/vision), so the benchmark measures what reviews run.
MODELS = Path(__file__).resolve().parents[2] / ".models"


def run(data: Path, out: Path, device: str, resume: bool = False) -> None:
    from verytas.media.fidelity import compare
    from verytas.vision.chain import Chain, iou

    manifest = json.loads((data / "manifest.json").read_text())
    # A full run takes over half an hour on a laptop CPU; --resume keeps the scenes already scored and
    # appends the rest. A run killed mid-write leaves a torn last line, which is dropped (and its scene
    # rerun) rather than glued to the next row.
    done: set[str] = set()
    if resume and out.is_file():
        whole = []
        for line in out.read_text().splitlines():
            try:
                done.add(json.loads(line)["file"])
            except (ValueError, KeyError):
                continue
            whole.append(line + "\n")
        # Replaced in one step: a crash here leaves the old file, never a half-written one.
        tmp = out.with_suffix(".tmp")
        tmp.write_text("".join(whole))
        tmp.replace(out)
    t0 = time.perf_counter()
    chain = Chain(MODELS, device)
    officials = sorted({c["mascot"] for c in manifest["cases"]})
    refs = {m: chain.reference(m, Image.open(data / f"{m}_official.png")) for m in officials}
    print(f"models and {len(officials)} officials ready in {time.perf_counter() - t0:.0f}s", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a" if resume else "w") as fh:
        for n, case in enumerate(manifest["cases"], start=1):
            if case["file"] in done:
                continue
            t = time.perf_counter()
            scene = Image.open(data / case["file"]).convert("RGB")
            row = dict(case)
            found = chain.detect(scene)
            if found is None:
                row["found"] = False
            else:
                box, score = found
                cut = chain.cut_out(scene, box)
                if cut is not None:
                    rgb, mask, crop = cut
                    vec = chain.embed(crop)
                    # Fidelity against the scene's own mascot, whatever likeness says: identity and
                    # fidelity are scored apart.
                    fid = compare(refs[case["mascot"]].fidelity, (rgb, mask))
                    row |= {"likeness": {m: round(float(vec @ r.vector), 4) for m, r in refs.items()},
                            "differences": [{"kind": d.kind, "text": d.text} for d in fid.differences]}
                row |= {"found": True, "score": round(score, 3), "iou": round(iou(box, case["box"]), 3)}
            row["seconds"] = round(time.perf_counter() - t, 2)
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if n % 25 == 0:
                print(f"{n}/{len(manifest['cases'])} scenes, {time.perf_counter() - t0:.0f}s", flush=True)


def _auc(pos: list[float], neg: list[float]) -> float:
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg)) if pos and neg else float("nan")


def report(path: Path) -> str:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    found = [r for r in rows if r.get("found")]
    lines = [f"Scenes: {len(rows)}; character found in {len(found)} ({len(found) / len(rows):.0%}); "
             f"box fits the truth (IoU >= 0.5) in {sum(r['iou'] >= 0.5 for r in found)}; "
             f"median {statistics.median(r['seconds'] for r in rows):.1f}s per scene"]

    # Identity: a scene's likeness to its own official is genuine unless the scene is a near-twin; its
    # likeness to every other official is an impostor score.
    genuine, impostor, twins = [], [], []
    for r in found:
        if "likeness" not in r:
            continue
        own = r["likeness"][r["mascot"]]
        if r["expect"] == "impostor":
            twins.append(own)
        else:
            genuine.append(own)
        impostor += [v for m, v in r["likeness"].items() if m != r["mascot"]]
    negatives = impostor + twins
    best = max(((t, sum(g >= t for g in genuine) / len(genuine) - sum(x >= t for x in negatives) / len(negatives))
                for t in sorted(set(genuine))), key=lambda p: p[1])[0]
    lines += [
        "",
        f"Identity (DINOv2 likeness): genuine median {statistics.median(genuine):.3f} (min {min(genuine):.3f}); "
        f"other mascots median {statistics.median(impostor):.3f} (max {max(impostor):.3f}); "
        f"near-twins median {statistics.median(twins):.3f} (max {max(twins):.3f})",
        f"AUC genuine vs other mascots {_auc(genuine, impostor):.3f}; vs near-twins {_auc(genuine, twins):.3f}",
        f"Best threshold {best:.3f}: genuine accepted {sum(g >= best for g in genuine) / len(genuine):.1%}, "
        f"other mascots accepted {sum(x >= best for x in impostor) / len(impostor):.2%}, "
        f"near-twins accepted {sum(x >= best for x in twins) / len(twins):.1%}",
    ]

    # Fidelity per variant: acceptable ones should report nothing; defects should report the right kind.
    by: dict[str, list[dict]] = defaultdict(list)
    for r in found:
        if "differences" in r:
            by[r["variant"]].append(r)
    lines += ["", "| Variant | Expect | Scenes | Flagged | Named right |", "|---|---|---|---|---|"]
    want = {"colour": {"colour_missing", "colour_new"}, "parts": {"parts"}, "shape": {"shape"}}
    for variant, rs in sorted(by.items(), key=lambda kv: (kv[1][0]["expect"], kv[0])):
        expect = rs[0]["expect"]
        flagged = sum(bool(r["differences"]) for r in rs)
        if expect.startswith("defect:"):
            kinds = want[expect.split(":")[1]]
            right = sum(any(d["kind"] in kinds for d in r["differences"]) for r in rs)
            named = f"{right / len(rs):.0%}"
        else:
            named = "-"
        lines.append(f"| {variant} | {expect} | {len(rs)} | {flagged / len(rs):.0%} | {named} |")
    ok = [r for r in found if r["expect"] == "ok" and "differences" in r]
    lines.append(f"\nFalse alarms on acceptable variants: {sum(bool(r['differences']) for r in ok)} of {len(ok)}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.mascots.run")
    p.add_argument("--data", type=Path)
    p.add_argument("--out", type=Path, default=Path("evals/results/mascots.jsonl"))
    p.add_argument("--device", default="cpu")
    p.add_argument("--report", type=Path)
    p.add_argument("--resume", action="store_true", help="keep scored scenes in --out and run the rest")
    args = p.parse_args()
    if args.report:
        print(report(args.report))
        return
    run(args.data, args.out, args.device, args.resume)
    print(report(args.out))


if __name__ == "__main__":
    main()
