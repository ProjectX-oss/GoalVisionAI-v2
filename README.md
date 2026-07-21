# GoalVision AI Architecture

GoalVision AI keeps prediction generation, calibration, eligibility, public
presentation, delivery, bankroll management, settlement, and result reporting
as separate boundaries.

## Pre-match data and features

`app/match_data_snapshot` is the append-only provenance boundary for complete or
partial supplied pre-match football facts. `app/feature_store` consumes one such
immutable snapshot and derives the explicit `official_prematch_features_v1`
Decimal-safe feature vector with separate missingness and quality indicators.
Neither package fetches providers, generates predictions, uses odds as v1 model
features, or invokes the Official candidate/publication stack.

The intentionally explicit integration is provider adapter ->
`register_match_data_snapshot(...)` -> `generate_match_feature_set(...)` ->
`generate_model_input(...)` -> `generate_raw_prediction(...)` -> probability
calibration -> market value assessment ->
`select_official_prediction(...)` -> future risk and candidate assembly ->
`register_official_prediction_candidate(...)`. `app/model_input_builder` owns the
fixed-order, missingness-preserving vector bridge. `app/prediction_inference` owns
only explicit model-adapter execution, raw probability validation, and immutable
inference history. It loads no model and runs no inference at startup.

The inference registry accepts explicitly supplied adapters and selects only an
explicit artifact or explicitly configured active Official model. Its canonical
11-target order covers match result, over/under 1.5, 2.5 and 3.5, and BTTS. Raw
Decimal probabilities must satisfy complement sums and monotonic totals rules;
invalid model output is rejected without normalization. Calibration remains a
separate downstream operation. `app/calibrated_market_probabilities` resolves a
complete explicit calibration set, runs the existing calibration engine per
target, validates the combined set without normalization, and atomically stores
the calibrated assembly. It does not perform odds/value, risk, candidate,
Quality Gate, or publication work.

`app/market_value_assessment` is the next isolated boundary. It combines a
calibrated assembly with explicitly supplied pre-match odds, maps only canonical
markets, derives double chance from match-result probabilities, and stores
Decimal-safe fair-odds/edge/EV assessments. Its actionability classification is
structural and does not select, stake, register, approve, or publish a bet.

`app/official_prediction_selection` consumes an explicit bounded collection of
those persisted assessments for one match. It verifies immutable provenance,
applies the versioned Official single policy, reads existing publication state
through an adapter, deduplicates logical markets, and deterministically selects
at most one assessment. The v1 boundary requires Official scopes, odds of at
least 1.60, EV of at least 0.02, a positive or strong upstream classification,
and actionable fresh data. It supports match winner, double chance, totals, and
BTTS only. Every per-assessment evaluation and either the selected or explicit
no-selection result is append-only in migration v20.

Selection is not publication approval and carries no stake recommendation. Its
typed handoff preserves verified value, model, calibration, and market
provenance for future risk assessment. Risk/staking, candidate registration,
Quality Gate execution, scheduling, Telegram publication, and the separate
future two-leg exception-combo workflow remain outside the package.

## Official prediction publication

The future scheduler-facing callable is
`prepare_and_publish_official_prediction(...)`. It assembles one supplied
candidate, persists the Official Quality Gate decision, creates the canonical
public message, obtains an atomic publication claim, sends through the injected
Telegram service, finalizes the delivery event, and then persists the
orchestration outcome.

`app/official_prediction_publication` owns public message assembly and the
claim/send/finalize adapter only. Prediction generation, calibration, market
selection, risk, exposure, bankroll, settlement, result publication, Telegram
credentials, scheduling, and non-Official products stay outside this boundary.
Unknown delivery outcomes are indeterminate and cannot be automatically resent.
Application startup constructs dependencies but never sends a prediction.

## Manual Official batches

`app/official_prediction_run_coordinator` is the explicit application boundary
for a future scheduler or administrator. It reads complete immutable requests
from an injected persisted source, orders them by kickoff, creation time, and
prediction ID, then calls the existing single-prediction boundary sequentially.
Every logical run and item outcome is append-only and idempotent. The callable
defaults to dry-run, requires an explicit timestamp and idempotency key, and is
not registered with application startup.

## Official candidate ingestion

`app/official_prediction_candidate_registry` is the append-only persistence
boundary below manual Official batches. Existing or future prediction engines
may explicitly register complete supplied pre-match facts; the registry
normalizes, validates, fingerprints, versions, supersedes, withdraws, and
invalidates those facts without calculating probabilities, EV, risk, exposure,
bankroll, or Quality Gate decisions. Its read-only adapter supplies active
`READY` versions to the existing coordinator, which retains all processing and
publication-state policy. No ingestion or batch is registered at startup.
