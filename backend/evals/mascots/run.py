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

import numpy as np
from PIL import Image

PROMPT = "a cartoon mascot character."
SAM_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"
SAM_CHECKPOINT = Path(__file__).resolve().parents[2] / ".models" / "sam2.1_hiera_tiny.pt"


class Chain:
    """The three models, loaded once."""

    def __init__(self, device: str = "cpu") -> None:
        import torch
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        from transformers import AutoImageProcessor, AutoModel, AutoModelForZeroShotObjectDetection, AutoProcessor

        self.torch, self.device = torch, device
        self.proc = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-tiny")
        self.gdino = AutoModelForZeroShotObjectDetection.from_pretrained("IDEA-Research/grounding-dino-tiny")
        self.gdino = self.gdino.to(device).eval()
        self.sam = SAM2ImagePredictor(build_sam2(SAM_CONFIG, str(SAM_CHECKPOINT), device=device))
        self.dproc = AutoImageProcessor.from_pretrained("facebook/dinov2-small")
        self.dino = AutoModel.from_pretrained("facebook/dinov2-small").to(device).eval()

    def detect(self, scene: Image.Image, prompt: str = PROMPT) -> tuple[list[float], float] | None:
        inp = self.proc(images=scene, text=prompt, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.gdino(**inp)
        res = self.proc.post_process_grounded_object_detection(
            out, inp.input_ids, threshold=0.25, text_threshold=0.2, target_sizes=[scene.size[::-1]])[0]
        if len(res["boxes"]) == 0:
            return None
        i = int(res["scores"].argmax())
        return [float(v) for v in res["boxes"][i].tolist()], float(res["scores"][i])

    def segment(self, scene: Image.Image, box: list[float]) -> np.ndarray:
        self.sam.set_image(np.asarray(scene))
        masks, _, _ = self.sam.predict(box=np.array(box), multimask_output=False)
        return masks[0].astype(bool)

    def embed(self, img: Image.Image):
        with self.torch.no_grad():
            v = self.dino(**self.dproc(images=img.convert("RGB"), return_tensors="pt").to(self.device))
        return self.torch.nn.functional.normalize(v.last_hidden_state[:, 0], dim=-1)[0].cpu().numpy()


def _on_white(rgba: Image.Image) -> Image.Image:
    bg = Image.new("RGB", rgba.size, "white")
    bg.paste(rgba, mask=rgba.getchannel("A"))
    return bg


def _iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def run(data: Path, out: Path, device: str) -> None:
    from verytas.media.fidelity import compare, official_reference

    manifest = json.loads((data / "manifest.json").read_text())
    t0 = time.perf_counter()
    chain = Chain(device)
    officials = sorted({c["mascot"] for c in manifest["cases"]})
    refs = {m: Image.open(data / f"{m}_official.png") for m in officials}
    ref_vec = {m: chain.embed(_on_white(img)) for m, img in refs.items()}
    ref_fid = {m: official_reference(img) for m, img in refs.items()}
    print(f"models and {len(officials)} officials ready in {time.perf_counter() - t0:.0f}s", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for n, case in enumerate(manifest["cases"], start=1):
            t = time.perf_counter()
            scene = Image.open(data / case["file"]).convert("RGB")
            row = dict(case)
            found = chain.detect(scene)
            if found is None:
                row["found"] = False
            else:
                box, score = found
                mask = chain.segment(scene, box)
                ys, xs = np.nonzero(mask)
                rgb = np.asarray(scene)
                if len(ys):
                    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                    crop = rgb[y0:y1, x0:x1].copy()
                    crop[~mask[y0:y1, x0:x1]] = 255
                    vec = chain.embed(Image.fromarray(crop))
                    fid = compare(ref_fid[case["mascot"]], (rgb, mask))
                    row |= {"likeness": {m: round(float(vec @ v), 4) for m, v in ref_vec.items()},
                            "differences": [{"kind": d.kind, "text": d.text} for d in fid.differences]}
                row |= {"found": True, "score": round(score, 3), "iou": round(_iou(box, case["box"]), 3)}
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
    args = p.parse_args()
    if args.report:
        print(report(args.report))
        return
    run(args.data, args.out, args.device)
    print(report(args.out))


if __name__ == "__main__":
    main()
