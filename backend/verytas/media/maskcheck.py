"""A character's cut-out can be wrong in a way that reads as a defect; this keeps that from becoming a finding.

Fidelity compares a cut-out with the official artwork, so a wrong cut-out makes a wrong finding. On the
mascot benchmark (`evals/mascots`, replayed from cached model outputs) most false alarms on acceptable
characters were "fewer shapes than the artwork": SAM, prompted with a box, keeps the body and drops thin
appendages (tail pieces, an antenna, a small accessory). With the true mask the same comparison raised a
third as many. So the cut-out is repaired where the evidence is specific, and nothing else is trusted
less:

- `reclaim` adds shapes in the artwork's own colours that continue just outside the mask.
- `judge` compares both cut-outs with one palette and keeps every finding of the plain cut-out except a
  shortfall (a colour missing, or fewer shapes of it) that the reclaimed cut-out no longer shows. Reclaiming
  can therefore withdraw a "missing" that clipping caused, and can never hide an extra eye or limb, a new
  colour, or a shortfall it does not explain.

Measured and not adopted (figures in evals/results/mascots.md): a gate on SAM's stability or on the
silhouette's fit to the artwork (every threshold that cut false alarms by half sent dozens of real defects
to "not sure"), re-prompting SAM with points placed on the artwork's colours (more false alarms, since
background of a palette colour draws the points), and picking among SAM's three candidate masks by
silhouette.
"""

from __future__ import annotations

import cv2
import numpy as np

from verytas.media import fidelity

# A palette-coloured shape beside the mask is taken as part of the character when it is no bigger than this
# share of the mask: a tail piece, a hat, a limb. Anything bigger is a background region that happens to
# share a colour with the character.
MAX_ADDED_SHARE = 0.12
# Nor smaller than this share: one- to five-pixel specks along the mask's edge are anti-aliasing and JPEG
# fringe in a palette colour, not parts, and enough of them tip a shape count.
MIN_ADDED_SHARE = 0.004
# How far outside the mask's bounding box to look for clipped parts, as a share of its longer side.
LOOK_MARGIN = 0.25
# A shape touches the mask when it is within this many pixels of it (SAM's edge is soft by a pixel or two).
TOUCH_PX = 3
# A tail or an antenna can float a little off the body, as the artwork draws it: look this far (share of the
# mask's longer side) for pieces that belong to it.
REACH = 0.12


def reclaim(rgb: np.ndarray, mask: np.ndarray, palette: list) -> np.ndarray:
    """The mask plus the official-coloured shapes that continue just outside it.

    SAM, prompted with a box, likes the body and drops thin appendages (a tail of small triangles, an
    antenna): the cut-out then "has no yellow shapes" where the artwork has three, which is the cut-out's
    fault, not the character's. A shape in one of the artwork's own colours that touches the mask, and is
    small next to it, is the missing piece: it continues outside the mask, as a real part of the character
    does, where background leakage does not (a leak is in the background's colours, not the character's).
    The mask this returns is the one fidelity should see."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return mask
    pad = int(LOOK_MARGIN * max(ys.max() - ys.min(), xs.max() - xs.min()))
    h, w = mask.shape
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + 1 + pad)
    window = np.zeros_like(mask)
    window[y0:y1, x0:x1] = True
    labels = fidelity._assign(rgb, window, palette, fidelity.COUNT_DE)
    candidate = (labels >= 0) & ~mask
    reach = max(TOUCH_PX, int(REACH * max(ys.max() - ys.min(), xs.max() - xs.min())))
    near = cv2.dilate(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * reach + 1,) * 2)
                      ).astype(bool)
    n, comp, stats, _ = cv2.connectedComponentsWithStats(candidate.astype(np.uint8), connectivity=8)
    out = mask.copy()
    area = float(mask.sum())
    for i in range(1, n):
        if MIN_ADDED_SHARE * area <= stats[i, cv2.CC_STAT_AREA] <= MAX_ADDED_SHARE * area and near[comp == i].any():
            out |= comp == i
    return out


def judge(official: tuple[np.ndarray, np.ndarray], rgb: np.ndarray, mask: np.ndarray) -> fidelity.Fidelity:
    """Fidelity for a cut-out, with shortfalls that only clipping explains withdrawn (see the module note).

    `official` is `fidelity.official_reference(...)`; `rgb` and `mask` are the scene and the segmenter's mask
    for the character."""
    palette = fidelity.palette_for(official, (rgb, mask))
    plain = fidelity.compare(official, (rgb, mask), palette=palette)
    if not any(d.shortfall for d in plain.differences):
        return plain
    fuller = reclaim(rgb, mask, palette)
    if fuller.sum() == mask.sum():
        return plain
    try:
        repaired = fidelity.compare(official, (rgb, fuller), palette=palette)
    except ValueError:
        return plain
    still_short = {d.colour for d in repaired.differences if d.shortfall}
    plain.differences = [d for d in plain.differences if not d.shortfall or d.colour in still_short]
    return plain
