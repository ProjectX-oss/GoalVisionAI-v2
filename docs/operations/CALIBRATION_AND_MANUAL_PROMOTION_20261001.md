# PREMATCH calibration and manual promotion — 2026-10-01

Status: engineering PASS; production challenger/calibration evidence NEEDS_MORE_EVIDENCE. Not deployed.

## Changes

- New calibration_research.py fits sigmoid/Platt and positive temperature scaling to raw TRAIN-only model outputs on an earlier, fixture-disjoint VALIDATION calibration partition.
- A later VALIDATION evaluation partition chooses the method and checks degradation. A 24-hour label-availability embargo purges overlapping fixtures.
- Minimum calibration fitting sample remains 300 with both classes; evaluation minimum 30. Isotonic requires 1,000 calibration observations. These do not replace the original TRAIN/30 VALIDATION/100 fresh SEALED_HOLDOUT preflight.
- Insufficient calibration data returns CALIBRATION_DATASET_NOT_READY before model fitting, cycle persistence or holdout use. No partition is borrowed from TRAIN or SEALED_HOLDOUT.
- Raw and calibrated Brier, log loss, ECE, MCE, reliability bins, extreme probabilities and method-level gates are retained.
- Initial research quality ceilings are ECE <= 0.10 and MCE <= 0.20, plus existing relative Brier/log-loss/ECE degradation limits. These are research gates, not publication thresholds or claims of optimal thresholds.
- Wrapper artifacts bind raw model, TRAIN fingerprint, dataset, calibration fitting/evaluation manifests, method and deterministic reproduction. JSON round trips preserve exact artifacts. Invalid raw endpoints or calibrated endpoints fail closed; no clamp hides invalid probability.
- Existing ensemble blending remains compatible but cannot count as calibration proof for PREMATCH promotion.
- AutoLearner validates/compares the calibrated wrapper on later evaluation rows before the untouched sealed holdout.
- Governance recommendations are read-only. Scheduled settlement now creates recommendations, never calls promote.
- Promotion requires all dataset/validation/calibration/holdout/shadow/global/stability gates, unchanged prior champion, and an explicit operator approval bound to the current recommendation ID, stream and time (maximum 24 hours).
- Existing rollback protection remains; no actual champion pointer was changed during this work.
- Legacy COMBO learning rows are excluded from shadow comparisons/rollback evidence as well as datasets.

## Changed files

app/adaptive_lab/calibration_research.py, models.py, automl.py, governance.py, coordinator.py; calibration/readiness/governance/autonomy regression tests.

## Verification

- Dedicated calibration/readiness tests: 25 PASS.
- Full synthetic PREMATCH integration uses 2,500 resolved fixture observations with noisy outcomes and an actual context logistic model. TRAIN, separate calibration, later validation, sealed holdout and 140 later shadow outcomes pass before explicit promotion. Missing, stale and mismatched approvals leave the champion unchanged.
- Synthetic LIVE legacy governance still requires manual approval; this test does not enable the LIVE runtime.
- Integrity rollback, other-stream isolation and SQLite foreign-key/integrity assertions remain covered.
- Scheduled 600-observation rehearsal now correctly blocks calibration instead of assuming automatic promotion.
- Tests also prove training computation does not hold the audit database write lock.
- See forward_ai_ml_20261001/calibration_readiness_projection.json for the read-only current-data projection. This is not a real research attempt.

## Limits / next evidence

The production dataset currently fails VALIDATION readiness. No production challenger was trained and no holdout was consumed. The next scheduled job is 2026-10-02 02:12 UTC; its eligibility cooldown can still prevent a real research cycle. Operator-approved deployment and a naturally eligible attempt are needed to validate this implementation in the runtime.

Primary calibration reference: Guo et al., 2017, https://proceedings.mlr.press/v70/guo17a.html (temperature scaling motivation). This implementation is a binary-logit research adaptation and makes no football performance claim.
