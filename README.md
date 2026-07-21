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

The intentionally deferred integration is provider adapter ->
`register_match_data_snapshot(...)` -> `generate_match_feature_set(...)` -> future
`generate_model_input(...)` -> model inference/prediction generation ->
`register_official_prediction_candidate(...)`. `app/model_input_builder` owns only
the fixed-order, missingness-preserving vector bridge; it does not contain or invoke
a prediction model. None of these new callables run at application startup.

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
