# Calibration benchmark

## seeded reviewers

276 decided findings from the seeded demo, replayed in time order; the last 83 are predicted from the ones before them in the same workspace. The calibrated curve was available for 83 of 83 (raw certainty otherwise).

| Predictor | Brier (lower is better) | Calibration error (ECE) |
|---|---|---|
| raw certainty | 0.128 | 0.141 |
| base rate | 0.101 | 0.069 |
| calibrated | 0.108 | 0.082 |

Reliability, raw certainty: in each band of prediction, how often reviewers agreed.

| Predicted | Mean predicted | Reviewers agreed | Decisions |
|---|---|---|---|
| 0.5 to 0.6 | 0.56 | 1.00 | 5 |
| 0.6 to 0.7 | 0.61 | 1.00 | 7 |
| 0.7 to 0.8 | 0.75 | 1.00 | 1 |
| 0.8 to 0.9 | 0.84 | 0.86 | 7 |
| 0.9 to 1.0 | 0.97 | 0.87 | 63 |

Reliability, calibrated: in each band of prediction, how often reviewers agreed.

| Predicted | Mean predicted | Reviewers agreed | Decisions |
|---|---|---|---|
| 0.6 to 0.7 | 0.67 | 1.00 | 11 |
| 0.7 to 0.8 | 0.77 | 0.81 | 16 |
| 0.8 to 0.9 | 0.82 | 0.86 | 14 |
| 0.9 to 1.0 | 0.95 | 0.90 | 42 |

## simulated reviewers (agreement = certainty cubed)

276 decided findings from the seeded demo, replayed in time order; the last 83 are predicted from the ones before them in the same workspace. The calibrated curve was available for 83 of 83 (raw certainty otherwise).

| Predictor | Brier (lower is better) | Calibration error (ECE) |
|---|---|---|
| raw certainty | 0.084 | 0.068 |
| base rate | 0.128 | 0.069 |
| calibrated | 0.076 | 0.081 |

Reliability, raw certainty: in each band of prediction, how often reviewers agreed.

| Predicted | Mean predicted | Reviewers agreed | Decisions |
|---|---|---|---|
| 0.5 to 0.6 | 0.56 | 0.20 | 5 |
| 0.6 to 0.7 | 0.61 | 0.29 | 7 |
| 0.7 to 0.8 | 0.75 | 1.00 | 1 |
| 0.8 to 0.9 | 0.84 | 0.71 | 7 |
| 0.9 to 1.0 | 0.97 | 0.97 | 63 |

Reliability, calibrated: in each band of prediction, how often reviewers agreed.

| Predicted | Mean predicted | Reviewers agreed | Decisions |
|---|---|---|---|
| 0.3 to 0.4 | 0.35 | 0.20 | 5 |
| 0.4 to 0.5 | 0.49 | 0.33 | 3 |
| 0.5 to 0.6 | 0.57 | 0.40 | 5 |
| 0.6 to 0.7 | 0.66 | 0.57 | 7 |
| 0.7 to 0.8 | 0.76 | 1.00 | 8 |
| 0.8 to 0.9 | 0.89 | 1.00 | 5 |
| 0.9 to 1.0 | 0.95 | 0.98 | 50 |
