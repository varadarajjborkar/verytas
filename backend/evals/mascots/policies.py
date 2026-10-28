"""Mask policies for the replay: how a scene's cached SAM outputs become the cut-out fidelity sees."""

from __future__ import annotations

import cv2
import numpy as np

from evals.mascots.replay import Bench
from verytas.media import maskgeom


def baseline(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    """What the worker did before the mask-quality work: one box-prompted mask, always trusted."""
    return e["one"]["masks"][0], "ok"


def oracle(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    """The true mask: what fidelity would say if segmentation were perfect (an upper bound)."""
    return bench.truth(case), "ok"


def _grow(mask: np.ndarray, px: int) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * abs(px) + 1,) * 2)
    f = cv2.dilate if px > 0 else cv2.erode
    return f(mask.astype(np.uint8), k).astype(bool)


def grow1(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    return _grow(e["one"]["masks"][0], 1), "ok"


def grow2(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    return _grow(e["one"]["masks"][0], 2), "ok"


def erode1(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    return _grow(e["one"]["masks"][0], -1), "ok"


def erode2(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    return _grow(e["one"]["masks"][0], -2), "ok"


def oracle_erode2(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    return _grow(bench.truth(case), -2), "ok"


def fill_holes(mask: np.ndarray, share: float) -> np.ndarray:
    """Close enclosed holes smaller than `share` of the mask."""
    m = mask.astype(np.uint8)
    contours, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = m.copy()
    limit = share * float(m.sum())
    for i, c in enumerate(contours):
        if hier[0][i][3] >= 0 and cv2.contourArea(c) <= limit:
            cv2.drawContours(out, contours, i, 1, -1)
    return out.astype(bool)


def holes(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    return fill_holes(e["one"]["masks"][0], 0.03), "ok"


def pick(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    art = bench.refs[case["mascot"]][1]
    cands = [e["one"]["masks"][0], *e["three"]["masks"]]
    fits = [maskgeom.similarity_iou(art, c) for c in cands]
    return cands[int(np.argmax(fits))], "ok"


def pick_holes(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    m, s = pick(bench, case, e)
    return fill_holes(m, 0.03), s


def palette(bench: Bench, case: dict, mask: np.ndarray) -> list:
    from verytas.media import fidelity

    return fidelity.palette_for(bench.refs[case["mascot"]], (bench.rgb(case), mask))


def reclaim(bench: Bench, case: dict, e: dict) -> tuple[np.ndarray | None, str]:
    from verytas.media import maskcheck

    m = e["one"]["masks"][0]
    return maskcheck.reclaim(bench.rgb(case), m, palette(bench, case, m)), "ok"
