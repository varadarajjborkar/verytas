# Mascot fidelity: cut-out repair and stretch

425 generated scenes (`backend/evals/mascots`, 30 procedural mascots, seed 7) plus 56 posed ones
(`poses.json`: arms raised, stance widened, both acceptable). The models ran once and their outputs are
cached (`evals.mascots.cache`); every row below is a replay of the same outputs through a different policy
(`evals.mascots.replay --policy ...`), so the differences are the policy's alone. Local CPU, 28 Oct 2026.

- **Before:** the box-prompted SAM mask compared as given (`baseline`).
- **After:** production, `maskcheck.judge` (`settled`): shortfalls that the reclaimed cut-out does not repeat
  are withdrawn, and a stretch is reported from the fitted map.
- **True mask:** the generator's own mask (`oracle`), an upper bound for anything that repairs the cut-out.

## False alarms on acceptable characters

| Variant | Before | After | True mask |
|---|---|---|---|
| plain | 4/30 | 3/30 | 1/30 |
| busy background | 16/30 | 11/30 | 1/30 |
| small | 1/30 | 1/30 | 1/30 |
| rotated | 19/30 | 14/30 | 9/30 |
| JPEG | 18/30 | 13/30 | 4/30 |
| redrawn | 6/30 | 6/30 | 5/30 |
| **all acceptable** | **64/180** | **48/180** | 21/180 |
| posed (arms up, wide) | 36/56 | 26/56 | |

Most remaining false alarms are still the cut-out: with the true mask they fall to 21/180.

## Defects named

"In the right direction" means an extra part is named as more shapes, a missing one as fewer; the replay's
own table counts any parts finding, which credits a missing arm "caught" as clipped tail pieces.

| Defect | Before | After |
|---|---|---|
| stretched body | 0/30 | **19/30** |
| recolour | 30/30 | 30/30 |
| swapped colours | 22/30 | 20/30 |
| extra eye | 25/28 | 25/28 |
| extra limb | 17/22 | 17/22 |
| extra tail piece | 3/11 | 3/11 |
| missing accessory | 18/18 | 18/18 |
| missing eye | 22/24 | 21/24 |
| missing limb | 19/22 | 18/22 |

The four scenes lost (m03 and m14 swapped colours, m09 missing eye, m27 missing limb) were caught before
only through the same clipping: in m27 the missing part is a green arm, and the "4 orange shapes where the
artwork has 5" that flagged it was the tail the mask had cut off. Repairing the cut-out restores the tail,
and nothing then points at the arm. No finding of an extra part, and no new colour, can be withdrawn.

The earlier figure of 23% for stretched bodies measured nothing: fidelity had no notion of shape, and those
scenes were flagged for other, incidental differences.

## Stretch thresholds

Ratio of the fitted map's singular values (1.0 is any size, any angle), from the box mask:

| Scenes | Median | 90th percentile | Highest |
|---|---|---|---|
| plain, small, redrawn | 1.01 to 1.05 | 1.04 to 1.08 | 1.11 |
| busy, JPEG, rotated, posed | 1.06 to 1.13 | 1.36 to 1.85 | 2.86 |
| stretched (1.35x) | 1.35 | 1.48 | 3.30 |

Bad cut-outs and new poses move the moments as much as a stretch, so the fit of the mapped artwork to the
cut-out gates it. Caught / flagged among 236 acceptable and posed scenes / among 185 other defects:

| Ratio at least | Fit 0.80 | Fit 0.85 | **Fit 0.88** | Fit 0.90 |
|---|---|---|---|---|
| 1.15 | 22 / 11 / 8 | 21 / 2 / 2 | 19 / 0 / 0 | 17 / 0 / 0 |
| **1.20** | 22 / 9 / 6 | 21 / 1 / 2 | **19 / 0 / 0** | 17 / 0 / 0 |
| 1.25 | 22 / 7 / 6 | 21 / 0 / 2 | 19 / 0 / 0 | 17 / 0 / 0 |

Chosen: 1.20 and 0.88. The thresholds were set on this benchmark, which stretches only one way by one
amount; a brand's real artwork should be checked against reviewer decisions.

## Tried and not adopted

| Idea | What happened |
|---|---|
| A quality gate on SAM's stability or the silhouette's fit | Every setting that halved false alarms (53 to 27 or fewer, on the reclaimed cut-out) also sent at least 46 real defects to "not sure" (`gate.py`). |
| Re-prompting SAM with points on the artwork's colours | False alarms rose to 87 to 132 of 180: background in a palette colour draws the points (`reprompt.py`). |
| Picking among SAM's three masks by silhouette | Slightly more false alarms than the single mask. |
| Using the reclaimed cut-out for every finding | 53/180 false alarms, but an extra eye and a missing limb were lost; reclaiming is now allowed only to withdraw a shortfall. |
