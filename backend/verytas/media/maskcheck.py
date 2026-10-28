"""Is a character's cut-out good enough to judge it by? And, if SAM offered several, which one.

Fidelity compares a cut-out with the official artwork, so a cut-out that is wrong makes a finding that is
wrong: a patch of street leaked into the mask reads as a new colour or an extra limb. On the mascot
benchmark most false alarms on busy backgrounds were that, not the character. This module sits between the
segmenter and `fidelity` and answers two questions with numpy alone (the worker supplies the model's
outputs; nothing here imports a model):

- `choose`: of SAM's candidate masks, the one whose outline is nearest the artwork's once both are
  brought to the same size and turned to the best angle (`maskgeom.similarity_iou`).
- `trust`: whether the chosen mask may produce a finding at all. A mask the model itself is unsure of
  (low stability), or one the model's alternatives disagree about, is not evidence about the character;
  the caller then tries better prompts (`seed_points`) or reports "not sure" instead of a difference.

The thresholds below were set on the mascot benchmark; evals/mascots/analysis.py reproduces the figures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from verytas.media import fidelity

# SAM's stability score: the share of a mask that survives moving the logit threshold from -1 to +1.
STABILITY_OFFSET = 1.0


def stability(logits: np.ndarray) -> float:
    """SAM's own stability definition: |logits > +1| / |logits > -1|. A mask whose edge sits on a plateau of
    near-zero logits (a shadow, a texture it cannot decide about) changes a lot when the threshold moves."""
    inside = float((logits > STABILITY_OFFSET).sum())
    union = float((logits > -STABILITY_OFFSET).sum())
    return inside / union if union else 0.0


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


@dataclass
class Candidate:
    """One mask SAM produced for a prompt, with the model's own opinion of it."""

    mask: np.ndarray
    iou: float  # SAM's predicted IoU with the object
    stability: float


@dataclass
class Cut:
    """The cut-out fidelity will see, and whether it may speak."""

    mask: np.ndarray
    trusted: bool
    fit: float  # silhouette overlap with the artwork after similarity alignment, 0 to 1
    why: str = ""
    signals: dict[str, float] = field(default_factory=dict)


# A palette-coloured shape beside the mask is taken as part of the character when it is no bigger than this
# share of the mask: a tail piece, a hat, a limb. Anything bigger is a background region that happens to
# share a colour with the character.
MAX_ADDED_SHARE = 0.12
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
    limit = MAX_ADDED_SHARE * float(mask.sum())
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] <= limit and near[comp == i].any():
            out |= comp == i
    return out
