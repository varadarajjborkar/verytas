"""Cache the expensive model outputs of the mascot benchmark, one file per scene, so mask-quality and
shape experiments rerun in seconds instead of half an hour.

Per scene it keeps the detector's box, SAM's masks for that box (the single mask production uses and all
three multimask outputs) with their predicted IoU and stability score, and SAM's image features, so a
different prompt (points, a tighter box) costs only the mask decoder:

    .venv-vision/bin/python -m evals.mascots.cache --data /tmp/mascots --cache /tmp/mascots-cache \
        --models /path/to/.models --resume

The cache is resumable: a scene whose files exist is skipped, and every file is written whole (to a
temporary name, then renamed), so a killed run never leaves a torn entry.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

# SAM's own stability definition (SAM 1 and 2): how much a mask changes when its threshold moves one
# logit either way. A mask whose edge is a plateau of near-zero logits is unstable.
STABILITY_OFFSET = 1.0


def stability(logits: np.ndarray) -> float:
    inside = float((logits > STABILITY_OFFSET).sum())
    union = float((logits > -STABILITY_OFFSET).sum())
    return inside / union if union else 0.0


def _pack(masks: np.ndarray) -> np.ndarray:
    return np.packbits(masks.reshape(len(masks), -1), axis=1)


def unpack(packed: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    flat = np.unpackbits(packed, axis=1)[:, : shape[0] * shape[1]]
    return flat.reshape(len(packed), *shape).astype(bool)


def predict_pack(sam, **prompt) -> dict[str, np.ndarray]:
    """One SAM call: boolean masks, predicted IoU and stability for each output."""
    logits, ious, _ = sam.predict(return_logits=True, **prompt)
    logits = np.asarray(logits, dtype=np.float32)
    return {"masks": logits > 0, "iou": np.asarray(ious, dtype=np.float32),
            "stab": np.array([stability(m) for m in logits], dtype=np.float32)}


def save_features(sam, path: Path) -> None:
    import torch  # only the vision environment has it; reading the cache needs numpy alone

    f = sam._features
    tensors = {"image_embed": f["image_embed"].half().cpu(), "h0": f["high_res_feats"][0].half().cpu(),
               "h1": f["high_res_feats"][1].half().cpu()}
    tmp = path.with_suffix(".tmp")
    torch.save({"hw": sam._orig_hw[0], **tensors}, tmp)
    tmp.replace(path)


def load_features(sam, path: Path) -> tuple[int, int]:
    """Put a scene's cached image features into the predictor, as if set_image had just run."""
    import torch

    d = torch.load(path, map_location="cpu")
    dev = sam.device
    sam._features = {"image_embed": d["image_embed"].float().to(dev),
                     "high_res_feats": [d["h0"].float().to(dev), d["h1"].float().to(dev)]}
    sam._orig_hw = [tuple(d["hw"])]
    sam._is_image_set = True
    sam._is_batch = False
    return tuple(d["hw"])


def build(data: Path, cache: Path, models: Path, device: str, resume: bool) -> None:
    from verytas.vision.chain import Chain

    (cache / "feats").mkdir(parents=True, exist_ok=True)
    manifest = json.loads((data / "manifest.json").read_text())
    chain = Chain(models, device)
    t0 = time.perf_counter()
    todo = [c for c in manifest["cases"]
            if not (resume and (cache / f"{c['file']}.npz").is_file() and (cache / "feats" / f"{c['file']}.pt").is_file())]
    print(f"{len(todo)} of {len(manifest['cases'])} scenes to cache", flush=True)
    for n, case in enumerate(todo, start=1):
        scene = Image.open(data / case["file"]).convert("RGB")
        found = chain.detect(scene)
        if found is None:
            entry = {"found": np.array(False)}
        else:
            box, score = found
            chain.sam.set_image(np.asarray(scene))
            save_features(chain.sam, cache / "feats" / f"{case['file']}.pt")
            one = predict_pack(chain.sam, box=np.array(box), multimask_output=False)
            three = predict_pack(chain.sam, box=np.array(box), multimask_output=True)
            entry = {"found": np.array(True), "box": np.array(box, dtype=np.float32), "score": np.array(score),
                     "shape": np.array(scene.size[::-1]),
                     "one_masks": _pack(one["masks"]), "one_iou": one["iou"], "one_stab": one["stab"],
                     "three_masks": _pack(three["masks"]), "three_iou": three["iou"], "three_stab": three["stab"]}
        # The features file only exists for found characters; an unfound scene is recorded all the same.
        if found is None:
            (cache / "feats" / f"{case['file']}.pt").write_bytes(b"")
        tmp = cache / f"{case['file']}.tmp.npz"
        np.savez_compressed(tmp, **entry)
        tmp.replace(cache / f"{case['file']}.npz")
        if n % 10 == 0:
            rate = (time.perf_counter() - t0) / n
            print(f"{n}/{len(todo)} scenes, {rate:.1f}s each, about {rate * (len(todo) - n) / 60:.0f} min left",
                  flush=True)


def load(cache: Path, file: str) -> dict | None:
    """A scene's cached entry with its masks unpacked, or None when no character was found."""
    z = np.load(cache / f"{file}.npz")
    if not bool(z["found"]):
        return None
    shape = tuple(int(v) for v in z["shape"])
    return {"box": z["box"].tolist(), "score": float(z["score"]), "shape": shape,
            "one": {"masks": unpack(z["one_masks"], shape), "iou": z["one_iou"], "stab": z["one_stab"]},
            "three": {"masks": unpack(z["three_masks"], shape), "iou": z["three_iou"], "stab": z["three_stab"]}}


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.mascots.cache")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--device", default="cpu")
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    build(a.data, a.cache, a.models, a.device, a.resume)


if __name__ == "__main__":
    main()
