# Calibration Quality and Extreme Probability Review

## Finding

The Aberdeen vs Heart of Midlothian `UNDER_2_5 = 0.999` result was reproduced
from the persisted champion without changing fixture facts, odds, timestamps,
or artifacts.

The exact path was:

1. The controlled-synthetic model emitted `OVER_2_5 = 0` and its derived raw
   complement `UNDER_2_5 = 1`.
2. The fitted `OVER_2_5` Platt calibrator (`a=0.7465429458251747`,
   `b=-0.05960953394669173`) clipped its logit input at `0.000001` and produced
   approximately `OVER_2_5 = 0.00003124934983548016`.
3. The canonical historical probability contract raised that source value to
   `0.001`.
4. Decreasing totals projection did not alter it.
5. `UNDER_2_5` was derived explicitly as `1 - OVER_2_5`, producing `0.999`.
6. No match-result simplex operation applies to this totals market.

The 0.999 value was therefore not a direct Platt prediction, isotonic endpoint,
or arbitrary presentation cap. It was a valid canonical clamp followed by an
explicit complement. The quality defect is insufficient support for this live
inference: the Platt calibrator was fitted on `OVER_2_5` raw probabilities from
`0.029061812592188825` to `0.9375409128958305`, while the live source input was
zero and outside that range.

## Quality policy

`goalvision-lab-calibration-quality-policy-v1` requires, per directly fitted
target:

- at least 100 VALIDATION examples;
- at least 20 positive and 20 negative labels;
- at least 20 unique raw probabilities;
- at least three populated reliability bins;
- ECE no greater than 0.15 and MCE no greater than 0.35;
- Brier and log-loss degradation no greater than 0.01;
- maximum individual adjustment of 0.35;
- explicit tracing of canonical extremes, complements, totals projection, and
  match-result simplex reconciliation.

Live inference additionally checks calibration support range, adjustment size,
all 78 feature distributions, required and optional missingness, odds-implied
probability, and EV. Unsupported extremes and their EV are non-actionable.

Controlled-synthetic evidence is permitted for development, inspection,
dry-run analysis, and shadow experimentation. It is not eligible for a Lab
Telegram publication. This is a separate decision from whether an analysis can
complete or a market can be mathematically ranked.

## Distribution shift

Each live feature is compared with the exact active champion fold's TRAIN,
VALIDATION, and TEST examples. The report retains partition medians, TRAIN
median absolute deviation, percentile rank, standardized robust distance,
historical range, imputation and absence flags, and missingness status.

The Aberdeen replay had all required baselines, 42 optional missing values, 13
out-of-range features, and 13 strongly shifted features. The aggregate result
was `CALIBRATION_DISTRIBUTION_SHIFT`.

## Official review

The existing Official Quality Gate checks a calibration sample size, model
version, Brier score, log loss, ECE, and MCE. It does not establish calibration
source mode, per-target class/reliability support, extreme frequency, live
support range, adjustment magnitude, distribution shift, or independent audit
review. No Official calibration-quality authorization or real-data requirement
exists, so this foundation does not enable Official actionability.

## Persistence and compatibility

No migration was necessary. Versioned reports are embedded in the existing
append-only analysis result snapshot and market evaluation snapshots. Existing
analyses remain readable. Missing quality evidence is rendered as
`CALIBRATION_QUALITY_NOT_EVALUATED` and is never newly send eligible.

Canonical rehearsal evidence is stored at
`docs/rehearsals/live_78_calibration_quality_review_2026-07-31.json`.
