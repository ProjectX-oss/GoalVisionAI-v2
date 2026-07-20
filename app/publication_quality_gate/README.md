# Official Publication Quality Gate

This package is the deterministic final eligibility boundary for prepared
Official prediction candidates. It consumes caller-supplied facts only and has
no network, Telegram, scheduling, prediction-generation, bankroll-mutation, or
stake-calculation behavior.

## Flow

1. `OfficialPublicationQualityGate` normalizes the supplied immutable candidate.
2. It evaluates policy, probability, odds, EV, freshness, calibration, model
   health, risk, exposure, market semantics, and duplicate-delivery state.
3. It returns exactly `APPROVED`, `REJECTED`, or `REVIEW_REQUIRED` using fixed
   precedence and ordered internal reason codes.
4. `SQLiteQualityGateEvaluationRepository` stores the evaluation once using the
   policy version and deterministic input fingerprint.
5. `app.official_prediction_orchestration` now supplies the complete candidate,
   persists this evaluation, applies orchestration idempotency and dry-run
   policy, and calls the injected atomic publisher only for `APPROVED` facts.

`OfficialPublicationEligibilityBoundary` remains available for existing direct
consumers, but the orchestration service is the complete callable Official
pre-publication boundary for future scheduling.

The downstream publisher remains solely responsible for Telegram delivery
claims, confirmed-failure retry state, and marking messages as sent. The gate
never mutates publication, bankroll, risk, settlement, or calibration records.

## Default Official policy

- Calibrated probability required in `[0.001, 0.999]`.
- Decimal odds must be valid and at least `1.60`.
- EV is verified as `calibrated_probability * decimal_odds - 1` with strict
  `0.0001` tolerance.
- EV below `0.02` is rejected; EV from `0.02` through less than `0.05` requires
  review.
- Candidate age is limited to 30 minutes, odds age to 15 minutes, and core data
  age to 60 minutes.
- Calibration requires 100 observations, a matching model version, and the
  configured Brier Score, Log Loss, ECE, and MCE preferred/warning/hard limits.
- Match-winner and double-chance markets are lineup-sensitive by default.
- Correct score and unsupported or structurally invalid markets are rejected.
- Risk `INELIGIBLE`, non-Official bankroll scope, hard exposure breaches,
  published state, and active delivery attempts are rejected.
- Risk review, exposure warnings, limited liquidity, weak medium-confidence
  evidence, and qualifying calibration warnings require review.
- Risk `REDUCED_STAKE` remains eligible when every other rule passes.
