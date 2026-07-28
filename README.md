# GoalVision AI Architecture

GoalVision AI keeps prediction generation, calibration, eligibility, public
presentation, delivery, bankroll management, settlement, and result reporting
as separate boundaries.

`app/shadow_evaluation` is the Lab-only bridge between an immutable promotion
recommendation and future controlled activation. It evaluates one approved
challenger beside the authoritative champion on the exact same input and odds.
Migration v30 retains both hypothetical decisions and later one-unit settlement
evidence. It is disabled by default and cannot configure a model, publish,
stake, mutate bankroll, access Telegram, or block the champion.

`app/model_activation` adds the next deliberately manual boundary. A final
promotion recommendation plus sufficient settled shadow evidence may prepare
an immutable plan, but preparation has no runtime effect. Only explicit
execution appends a new champion generation. Manual rollback appends another
generation for a validated historical champion. Its resolver is read-only and
remains disconnected from startup and current production inference.

## Historical machine-learning data foundation

`app/historical_data_import` is the append-only authoritative boundary for
explicitly supplied historical match datasets. The versioned importer
normalizes competition, season, round, kickoff UTC, team identities, scores,
result, venue, optional referee/attendance, available team statistics, and
available lineups before calculating canonical SHA-256 fingerprints.

Migration v23 stores immutable import audits, versioned matches, statistics,
and lineups in one atomic transaction. Exact replay writes nothing; corrected
provider content appends a new match version without changing prior history.
This boundary is intentionally upstream-only: it performs no discovery, live
provider access, scheduling, feature generation, training, prediction,
backtesting, publication, or Telegram work, and it is not connected to startup.

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
`select_official_prediction(...)` ->
`prepare_official_candidate(...)` ->
`register_official_prediction_candidate(...)` -> Publication Quality Gate ->
publication orchestration -> atomic Telegram publication -> immutable pipeline
result. The final manual boundary is
`execute_official_prediction_pipeline(...)` in
`app/official_prediction_pipeline`.
`app/model_input_builder` owns the
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
provenance for the independent `app/official_candidate_preparation` boundary.
That integration consumes explicit immutable Official bankroll/exposure facts,
calls the existing risk service once, and registers only `ELIGIBLE` or
`REDUCED_STAKE` outcomes through the Candidate Registry. `REVIEW_REQUIRED` and
`INELIGIBLE` become append-only no-registration decisions. It does not execute
the Quality Gate, publish, schedule, or support the separate two-leg exception
combo workflow. Migration v21 stores immutable executions and risk snapshots.

## Official prediction publication

`app/official_prediction_pipeline` verifies one exact current Registry version,
checks durable publication state, invokes and persists the Quality Gate once,
then continues through orchestration's verified pre-approved path. Migration
v22 stores the immutable terminal execution and ordered stage events. Identical
terminal requests replay without another gate, orchestration, claim, or send;
active and indeterminate claims fail closed. Dry-run builds the existing final
message payload but never claims or sends. The boundary is manual only.

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

## Controlled manual operations and startup safety

`app/official_prediction_operations` is the operator-facing end-to-end fixture
and CLI boundary. It traverses the real persisted services with a deterministic
adapter only at the external model-artifact boundary. Validation, dry-run,
controlled publication, inspection, bounded retry listing, explicit retry,
diagnostics, and startup smoke checks are available through
`python -m app.official_prediction_operations.cli`.

There is no default database or transport. New files require explicit creation,
fixture environment is no-send, staging/production destinations are injected
and verified, and exact publication/retry confirmation tokens are mandatory.
Indeterminate post-send state forbids resend. Imports and application startup
still execute zero fixture runs, discovery, gates, claims, sends, scheduling,
provider fetching, or bot polling. See
`docs/OFFICIAL_PREDICTION_OPERATIONS_RUNBOOK.md`.

## Historical machine-learning datasets

`app/historical_data_import` is the authoritative supplied-data boundary.
`app/historical_training_dataset` consumes explicitly selected immutable imports
and creates reproducible pre-match training examples under migration v24. Every
source kickoff must be strictly earlier than its target; target outcomes and
statistics cannot enter features. The versioned 145-position historical schema
keeps missing values and provenance explicit rather than claiming silent
compatibility with the live 78-feature schema.

Builds, examples, source linkages, and exclusions are append-only, atomically
persisted, fingerprinted, and independently inspectable. Imports and application
startup perform no dataset build, provider access, model work, scheduling,
publication, or Telegram activity.

`app/historical_dataset_split` owns the next offline boundary. It verifies one
immutable training dataset, preserves equal-kickoff groups, supports explicit
time boundaries, chronological ratios, and bounded expanding windows, and
persists auditable gap/filter/boundary exclusions under migration v25. Splits
are deterministic and append-only; no shuffle, sampling, label balancing,
training, calibration fitting, inference, or backtesting occurs in this layer.

`app/historical_model_training` consumes one verified split fold and fits only
its TRAIN assignments. It persists a safe canonical parameter artifact under
migration v26 using deterministic logistic baselines: coherent three-class
match result, a monotonic four-bucket totals construction, and binary BTTS.
Median imputation and standard scaling are fitted from TRAIN only; VALIDATION is
evaluation-only and TEST is never loaded. The artifact produces the existing
canonical 11-target raw, explicitly uncalibrated probability contract. No
calibration, backtesting, comparison, promotion, live wiring, or publication is
performed by this layer.

`app/historical_probability_calibration` is the explicit VALIDATION-only next
layer. It reproduces raw probabilities with the immutable source model artifact,
fits the existing identity/Platt/isotonic calibrators, reconciles result and
totals groups, and derives complements. Migration v27 persists a safe inactive
artifact set, audit predictions, metrics, and reliability bins. TRAIN is never
refitted and TEST is never loaded. Activation, backtesting, promotion, live
wiring, provider access, scheduling, publication, and Telegram remain outside
this boundary.

`app/historical_backtesting` is the explicit TEST-only evaluation boundary. It
verifies the full split, fold, dataset, model, and calibration fingerprint chain
and consumes only caller-supplied immutable pre-match odds. Migration v28
atomically stores reproduced predictions, all market assessments and
rejections, at most one Official single per match, isolated-EUR stakes,
immutable-score settlements, the bankroll/drawdown ledger, predictive and
betting metrics, reliability bins, exclusions, and optional post-decision CLV.

Equal-kickoff decisions share one pre-group bankroll and are frozen before any
result settles. Decision odds must be strictly pre-kickoff; closing odds never
influence decisions. This layer makes no profitability promise and performs no
training, recalibration, comparison, promotion, activation, live wiring,
fetching, scheduling, publication, Telegram activity, or startup execution.

`app/model_comparison_promotion` is the immutable Lab-only comparison boundary.
It verifies explicit champion and challenger model, calibration, and completed
TEST backtest identities and fingerprints. Migration v29 atomically persists
fair-scope evidence, predictive/calibration/betting/risk deltas, grouped
stability, deterministic bootstrap uncertainty, mandatory gates, centralized
weighted scores, challenger rankings, exclusions, and the final recommendation.
Exact shared scope is preferred; intersection and policy-normalized modes are
versioned and retain every exclusion. A high ROI cannot override integrity,
calibration, risk, stability, or evidence gates.

The only possible output is an auditable recommendation. At most one challenger
can be recommended for promotion, and no code in this package activates a model,
changes production configuration, performs shadow evaluation, wires live
inference, fetches odds, schedules work, publishes, or contacts Telegram.

```text
historical import
  -> historical training dataset
  -> historical dataset split
  -> historical model training (TRAIN)
  -> historical probability calibration fitting (VALIDATION)
  -> historical backtesting (TEST)
  -> model comparison and promotion recommendation
  -> future shadow evaluation
  -> future controlled production activation
```

`app/model_operations` provides the reviewed manual operator surface over the
controlled activation foundation. It supports explicit one-time bootstrap,
two-stage activation and rollback, immutable audit inspection, generation
listing, and fail-closed diagnostics. Exact confirmation phrases are mandatory
for execution. Preparation does not activate a model, rollback appends a new
generation, and promotion and Shadow remain evidence-only.

The model-operations package adds no migration, startup hook, scheduler,
background worker, runtime inference wiring, Telegram send, prediction
publication, settlement, bankroll, or Official behavior. See
`docs/model_operations_runbook.md`.

`app/staging_model_operations_rehearsal` is the separate, explicit
`STAGING`-only proof boundary. It verifies a caller-supplied SQLite source and
byte-identical backup without using that database as a label source, then
builds a deterministic `REAL_ONLY` chain through the genuine import, dataset,
chronological split, training, calibration, TEST backtest, comparison,
promotion, Shadow evaluation, and settlement services. Fixture fallback is
forbidden. Independent audits gate bootstrap and execution before the real
activation, resolver, rollback, diagnostics, replay, conflict, confirmation,
and atomic-recovery paths run on disposable copies.

The rehearsal has no default source or destination, rejects production and
path collisions, never overwrites evidence, and is not imported by startup.
It does not authorize production activation or change runtime inference,
Official publication, Telegram, bankroll, settlements, statistics,
scheduling, or workers. See `docs/model_operations_runbook.md` and
`docs/rehearsals/staging_model_operations_rehearsal.md`.
