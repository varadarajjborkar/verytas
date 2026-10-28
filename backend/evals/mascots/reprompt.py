"""Does prompting SAM again, with points placed from the artwork's colours, repair a bad cut-out?

A box alone leaves SAM to decide what is the character. The artwork says which colours the character is
made of, so the middle of the largest patch of each of those colours inside the box is certainly the
character (a positive point), and the middle of the largest region in none of them is certainly not
(a negative point). The decoder reruns from the cached image features, so no image encoder pass is paid.

    .venv-vision/bin/python -m evals.mascots.reprompt --data DIR --cache DIR --models DIR [--manifest M]

writes <cache>/<scene>.pts.npz with the box-and-points masks of each variant.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from evals.mascots import cache as cachemod
from verytas.media import fidelity

cv2.setNumThreads(0)

MAX_POSITIVE = 4  # colours that get a point
MIN_PATCH = 0.004  # a patch smaller than this share of the box is a speck, not a place to point at


def centre(region: np.ndarray) -> tuple[int, int]:
    """The point deepest inside a region: the maximum of its distance transform."""
    dist = cv2.distanceTransform(region.astype(np.uint8), cv2.DIST_L2, 3)
    y, x = np.unravel_index(int(dist.argmax()), dist.shape)
    return int(x), int(y)


def points_for(rgb: np.ndarray, box: list[float], palette: list, negative: bool) -> tuple[np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    window = np.zeros((h, w), bool)
    window[y0:y1, x0:x1] = True
    labels = fidelity._assign(rgb, window, palette, fidelity.COUNT_DE)
    floor = MIN_PATCH * (x1 - x0) * (y1 - y0)
    found = []
    for i in range(len(palette)):
        n, comp, stats, _ = cv2.connectedComponentsWithStats((labels == i).astype(np.uint8), connectivity=8)
        if n > 1:
            k = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
            if stats[k, cv2.CC_STAT_AREA] >= floor:
                found.append((int(stats[k, cv2.CC_STAT_AREA]), centre(comp == k)))
    pts = [p for _, p in sorted(found, reverse=True)[:MAX_POSITIVE]]
    lab = [1] * len(pts)
    if negative:
        other = (labels == -1) | (labels == -2)
        other[~window] = False
        # Only background that reaches the box's edge: an eye or a mouth is "no palette colour" too.
        n, comp, stats, _ = cv2.connectedComponentsWithStats(other.astype(np.uint8), connectivity=8)
        best = None
        for k in range(1, n):
            xs, ys, ww, hh, a = stats[k]
            touches = xs <= x0 or ys <= y0 or xs + ww >= x1 or ys + hh >= y1
            if touches and a >= floor and (best is None or a > best[0]):
                best = (a, k)
        if best:
            pts.append(centre(comp == best[1]))
            lab.append(0)
    return np.array(pts, dtype=np.float32).reshape(-1, 2), np.array(lab, dtype=np.int32)


def build(data: Path, cache: Path, models: Path, manifest_name: str, limit: int = 0) -> None:
    from PIL import Image

    from verytas.vision.chain import Chain

    chain = Chain(models, "cpu")
    manifest = json.loads((data / manifest_name).read_text())
    refs = {}
    for c in manifest["cases"]:
        if c["mascot"] not in refs:
            refs[c["mascot"]] = fidelity.official_reference(Image.open(data / f"{c['mascot']}_official.png"))
    for n, case in enumerate(manifest["cases"][: limit or None], start=1):
        out = cache / f"{case['file']}.pts.npz"
        entry = cachemod.load(cache, case["file"])
        if out.is_file() or entry is None:
            continue
        rgb = np.asarray(Image.open(data / case["file"]).convert("RGB"))
        cachemod.load_features(chain.sam, cache / "feats" / f"{case['file']}.pt")
        palette = fidelity.palette_for(refs[case["mascot"]], (rgb, entry["one"]["masks"][0]))
        res = {}
        for name, neg in (("pos", False), ("posneg", True)):
            pts, lab = points_for(rgb, entry["box"], palette, neg)
            for tag, kw in (("box", {"box": np.array(entry["box"])}), ("nobox", {})):
                if tag == "nobox" and name == "pos":
                    continue
                p = cachemod.predict_pack(chain.sam, point_coords=pts, point_labels=lab,
                                          multimask_output=False, **kw)
                res[f"{name}_{tag}_masks"] = cachemod._pack(p["masks"])
                res[f"{name}_{tag}_stab"] = p["stab"]
                res[f"{name}_{tag}_iou"] = p["iou"]
        np.savez_compressed(out, shape=np.array(entry["shape"]), **res)
        if n % 25 == 0:
            print(n, flush=True)


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.mascots.reprompt")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--manifest", default="manifest.json")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    build(a.data, a.cache, a.models, a.manifest, a.limit)


if __name__ == "__main__":
    main()
