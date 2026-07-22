# TASKS.md

# GoalVision AI Development Tasks

Version 1.0

Tasks are always completed from top to bottom.

No task may be skipped unless explicitly approved.

---

# PRIORITY 1

## Stabilize Current Project

Status:

COMPLETED

Tasks

- [x] Complete Feature migration.
- [x] Fix TeamStrength migration.
- [x] Remove remaining runtime errors.
- [x] Verify project starts successfully.
- [x] Verify prediction pipeline.
- [x] Verify Telegram publishing without contacting the live channel.
- [x] Verify database initialization.
- [x] Verify repository layer.

Definition of Done

Project starts without exceptions.

---

# PRIORITY 2

## Prediction Engine

Status

TODO

Tasks

Improve rating calculation.

- [x] Complete deterministic Official Prediction Selection Engine foundation.
- [x] Complete Official Selection-to-Risk and Candidate Preparation integration.
- [x] Complete Registered Candidate-to-Quality Gate and Official Publication Pipeline integration.
- [x] Complete controlled manual end-to-end fixtures, operational CLI, diagnostics, recovery analysis, and operator runbook.

Review feature weights.

Review confidence thresholds.

Improve probability calculation.

Improve prediction explainability.

Definition of Done

Prediction engine stable.

---

# PRIORITY 3

## Feature System

Status

TODO

Tasks

Review every feature.

Remove duplicate calculations.

Normalize feature values.

Improve FeatureBuilder.

Improve TeamStrengthEngine.

Definition of Done

Feature system fully documented.

---

# PRIORITY 4

## Data Collection

Status

TODO

Tasks

Improve Football API caching.

Improve Standings collector.

Improve Match collector.

Improve History loading.

- [x] Complete the deterministic append-only Historical Match Data Import foundation.

Improve retry logic.

Definition of Done

Stable data collection.

---

# PRIORITY 5

## Telegram

Status

TODO

Tasks

Improve formatting.

Improve readability.

Improve notifications.

Improve weekly reports.

Improve monthly reports.

Improve result publishing.

Definition of Done

Professional Telegram output.

---

# PRIORITY 6

## Bank Manager

Status

TODO

Tasks

Public bankroll.

Weekly statistics.

Monthly statistics.

Bank growth.

Bank history.

Definition of Done

Automatic bankroll management.

---

# PRIORITY 7

## Backtesting

Status

IN PROGRESS

Tasks

- [x] Deterministic historical evaluation foundation.

- [x] Accuracy and hit rate.

- [x] ROI and profit/loss metrics.

- [x] Win rate.

- [ ] League reports.

Definition of Done

Reliable backtesting.

---

# PRIORITY 8

## Optimization

Status

TODO

Tasks

Performance.

Database.

Caching.

Async.

Logging.

Imports.

Architecture cleanup.

Definition of Done

Production-ready performance.

---

# PRIORITY 9

## Testing

Status

TODO

Tasks

Unit Tests.

Integration Tests.

Regression Tests.

Performance Tests.

Definition of Done

Stable release.

---

# PRIORITY 10

## Version 1.0 Release

Status

TODO

Checklist

Production deployment.

Telegram running.

Public bankroll.

Automatic results.

Weekly reports.

Monthly reports.

Monitoring.

Definition of Done

GoalVision AI Version 1.0 released.

---

# COMPLETED TASKS

Move completed work here.

Never delete completed tasks.

Only append.

## 2026-07-12 - Stabilize Current Project

- Completed the Feature and TeamStrength migration.
- Fixed model and feature imports.
- Removed obsolete bot startup code and unused AI initialization.
- Added safe football API failure handling and guaranteed client cleanup.
- Verified the prediction pipeline, Telegram service boundary, database initialization, and team repository with automated tests.
- Verified `python -m app.main` starts and exits without an unhandled exception when no match data is available.

## 2026-07-12 - League Strength Engine

- Added a centralized, normalized league-rating table.
- Added a validated League Strength Engine with injected ratings and unknown-league fallback.
- Injected the engine into the prediction pipeline without changing prediction outcomes.
- Added unit coverage for lookup, validation, fallback, dependency injection, and outcome isolation.

## 2026-07-12 - H2H Engine

- Added a typed H2H Engine with injected historical fixture data.
- Added finished-match, team-pair, duplicate, and maximum-history filtering.
- Added recency weighting and configurable insufficient-history confidence handling.
- Injected the engine into the prediction pipeline without changing prediction outcomes.
- Added unit coverage for empty, single, multiple, recent, duplicate, and normalized histories.

## 2026-07-12 - Rest Days Engine

- Added a typed Rest Days Engine using only finished-fixture timestamps.
- Added configurable rest capping and normalized home-versus-away comparison.
- Injected the engine into the prediction pipeline without changing prediction outcomes.
- Added unit coverage for missing, equal, advantaged, capped, unfinished, and normalized histories.

## 2026-07-13 - AI Quality Score Framework

- Added deterministic, typed supporting-data quality scoring from 0 to 100.
- Centralized and validated signal weights, critical signals, and penalties.
- Added completeness, consistency, warnings, and explanation-ready reason codes.
- Injected the framework into the prediction pipeline without changing predictions or publication.
- Added unit coverage for complete, empty, partial, conflicting, critical-missing, invalid, deterministic, and isolated behavior.

## 2026-07-13 - AI Quality Score Pipeline Integration

- Added typed prediction assessments containing predictions, quality results, team contexts, signals, reason codes, and supporting metadata.
- Built real quality signals from team form, standings, configured league ratings, cached H2H/rest history, venue history, attack, and defense data.
- Preserved missing data explicitly and added deterministic component-conflict measurement.
- Reused the existing prediction method so assessments do not duplicate or alter prediction calculations.
- Added integration coverage for complete, partial, missing, deterministic, isolated, and Telegram-neutral behavior.

## 2026-07-13 - Deterministic Prediction Explanations

- Added typed deterministic explanations to every prediction assessment.
- Added concise positive factors, risks, missing-data labels, reason codes, and supporting metrics.
- Derived explanations only from predictions, quality results, team contexts, league configuration, and typed H2H/rest history.
- Preserved a single prediction and quality-score calculation per assessment.
- Added coverage for home/away advantages, conflicts, missing and neutral data, determinism, factual isolation, and prediction isolation.

## 2026-07-13 - Telegram Prediction Presentation Framework

- Added typed compact prediction, detailed explanation, result, and inline-action presentation models.
- Added deterministic Telegram-safe HTML formatters with complete text escaping.
- Kept compact posts separate from concise “Why this pick?” analysis.
- Kept AI Quality Score display configurable and disabled by default pending calibration.
- Added unit coverage for home/away picks, optional odds and quality, details, risks, escaping, determinism, and network isolation.

## 2026-07-13 - Telegram Prediction Interaction Framework

- Added typed interaction actions for deterministic explanation retrieval plus future statistics and bankroll placeholders.
- Added versioned, validated callback identifiers with no secrets or raw explanation data and an enforced Telegram size limit.
- Added a dependency-injected assessment/explanation lookup boundary with expiry and missing-data handling.
- Added idempotent duplicate handling that reuses the first formatted explanation response.
- Kept production Telegram sending unchanged and added isolated callback coverage without network access.

## 2026-07-13 - Prediction Result Resolution Framework

- Added typed published-prediction, fixture-result, resolution, status, reason-code, and audit models.
- Added deterministic Match Winner settlement for home, away, and draw picks through a centralized extensible rule registry.
- Added configurable handling for pending, cancelled, postponed, abandoned, finished, and unsupported fixture statuses.
- Added a dependency-injected repository boundary with terminal-result idempotency and immutable prior settlements.
- Kept result publishing, bankroll settlement, live API access, and database schemas unchanged.

## 2026-07-13 - Persistent Prediction Result Storage

- Added an additive, versioned SQLite migration for published predictions and terminal settlement audit data.
- Added persistent pending-prediction loading, idempotent publication writes, immutable result settlement, and result-history retrieval.
- Stored prediction identity, fixture, market, pick, optional odds and stake, timestamps, final score, status, reason codes, and settlement rule version.
- Preserved existing database tables and data while reusing the project Database abstraction.
- Kept Telegram result publishing, bankroll settlement, prediction policy, and application startup behavior unchanged.

## 2026-07-14 - Official Bankroll Settlement Framework

- Added a Decimal-based Official bankroll account starting at EUR 10,000.
- Added explicit STANDARD, STRONG, and ELITE stake tiers at 1%, 2%, and 3%, with separate 3-, 4-, and 5-star public metadata.
- Added deterministic WON, LOST, VOID, PENDING, and UNRESOLVED settlement handling with immutable audit transactions.
- Added dependency-injected bankroll repositories, atomic idempotency, snapshots, and strict product separation.
- Kept Telegram, prediction policy, database schemas, and automatic tier selection unchanged.

## 2026-07-14 - Persistent Official Bankroll Storage

- Added additive SQLite account and immutable transaction migrations without altering existing result history.
- Initialized the Official EUR 10,000 account exactly once and preserved its balance and settled prediction IDs across restarts.
- Added Decimal-safe persistent account loading, atomic idempotent transaction storage, and chronologically ordered history retrieval.
- Integrated explicit-tier bankroll settlement with existing typed prediction resolution results.
- Kept Telegram, automatic jobs, prediction policy, other product bankrolls, and automatic tier selection disabled.

## 2026-07-14 - Automatic Prediction Settlement Orchestration

- Added one deterministic application service for pending prediction loading, deduplicated fixture retrieval, result persistence, and Official bankroll settlement.
- Added typed settlement candidates, batch requests, per-prediction outcomes, reports, and failure reason codes.
- Enforced result-first persistence boundaries and restart-safe bankroll recovery for partial failures.
- Added per-fixture failure isolation, duplicate handling, aggregate audit counts, timestamps, and rule versions.
- Kept scheduling, Telegram publishing, live API coupling, prediction policy, and non-Official bankrolls disabled.

## 2026-07-14 - Official Telegram Result Publication Framework

- Added deterministic WON, LOST, and VOID Official result messages using the existing presentation layer.
- Added persistent, restart-safe publication audit state with atomic delivery claims, retryable confirmed failures, and duplicate prevention.
- Included optional league/team context, final score, odds, public stake stars, Decimal stake and profit/loss values, and updated Official bankroll.
- Kept internal stake percentages, AI Quality Score, other product channels, recurring scheduling, and live Telegram wiring disabled.
- Added isolated SQLite and fake-Telegram coverage for formatting, escaping, retries, database failures, idempotency, and mixed batches.

## 2026-07-15 - Backtesting Engine Foundation

- Added an isolated, typed `app/backtesting` package for deterministic historical evaluation.
- Added immutable one-unit evaluation records with Decimal probabilities, odds, profit/loss, results, and WON/LOST/VOID outcomes.
- Added leakage validation that rejects feature or odds timestamps newer than the prediction timestamp.
- Added deterministic hit rate, ROI, profit, odds, drawdown, Brier Score, Log Loss, CLV, and probability metrics.
- Added pluggable walk-forward window and evaluator interfaces without model training or optimization.
- Added edge-case and repeatability coverage without changing production prediction, publication, settlement, scheduling, or database behavior.

## 2026-07-15 - Probability Calibration Engine Foundation

- Added isolated immutable calibration observations with explicit binary outcomes and VOID rejection.
- Added deterministic equal-width and explicit-boundary binning with retained empty bins.
- Added Decimal Brier Score, Log Loss, ECE, MCE, bin reports, and raw-versus-calibrated comparisons.
- Added a fully functional Identity calibrator plus honest Platt and Isotonic fitting interfaces that do not fabricate fitted behaviour.
- Added immutable fit metadata, model/competition/market/odds-band scopes, minimum-sample fallback, and actual-scope reporting.
- Added strict prediction/outcome cutoff, target-isolation, duplicate-timestamp, scope, and model-version protections.
- Kept live prediction generation, Telegram publication, scheduling, bankrolls, and database schemas unchanged.

## 2026-07-15 - Publication Quality Gate Foundation

- Added an isolated deterministic decision pipeline returning APPROVED, REJECTED, or REVIEW_REQUIRED with ordered audit checks and reason codes.
- Encoded configurable Official single-bet, minimum-odds, correct-score, timing, evidence, calibration, value, conflict, uncertainty, exposure, and duplicate policies.
- Represented the reviewed two-selection combo exception without creating or publishing combo bets.
- Added typed calibration metadata consumption, unrounded Decimal expected-value calculation, minimum-sample enforcement, and raw-probability opt-in controls.
- Added explicit evidence states, per-category evidence policy, deterministic decision precedence, and normalized Official duplicate identities.
- Kept prediction generation, Telegram publication, bankroll settlement, scheduling, all product channels, and database schemas unchanged.

## 2026-07-15 - Publication Quality Gate Shadow Evaluation Foundation

- Added immutable shadow requests, snapshots, decisions, safe errors, settlement facts, and deterministic comparison reports.
- Added migration v4 with isolated shadow evaluation and error audit tables plus prediction, fixture, date, status, publication, policy, and stage lookup support.
- Added insert-once persistence keyed by prediction, policy version, and evaluation stage while allowing INITIAL_CANDIDATE, PRE_PUBLICATION, and FINAL_PRE_KICKOFF observations.
- Added disabled-by-default runtime observation immediately after prediction assessment without using the shadow result to alter sorting or publication behaviour.
- Added explicit missing-data adaptation for currently unavailable odds, calibration, lineup, injury, consensus, exposure, and sample-size facts.
- Added idempotent authoritative WON, LOST, and VOID settlement enrichment without bankroll or publication side effects.
- Added descriptive and clearly labelled hypothetical one-unit comparison reports using only evaluation-time offered odds.
- Kept Quality Gate enforcement, Telegram publication decisions, scheduling, betting, bankroll mutation, settlement polling, and all non-Official products disabled.

## 2026-07-16 - Odds Observation and CLV Tracking Foundation

- Added an isolated immutable `app/odds` domain for typed sources, markets, selections, observations, snapshots, consensus, movement, closing odds, CLV, and safe ingestion errors.
- Added deterministic normalization and validation for Decimal odds, exchange commission, source/fixture/market/selection identities, timezone-aware cutoffs, source status, and kickoff policy.
- Added migration v5 with lossless Decimal text storage, insert-once observations, source metadata, separate closing-odds records, deterministic uniqueness constraints, and indexed lookup paths.
- Added deterministic opening/latest queries, consensus and complete-market no-vig calculations, model-versus-market disagreement, odds movement, closing fallback selection, and the established `publication_odds / closing_odds - 1` CLV formula.
- Added provider contracts plus Static and Null providers, idempotent batch ingestion, backtesting conversion with leakage checks, and a shadow-only odds enrichment adapter that never uses future observations.
- Kept live odds network access, Telegram publication, Quality Gate enforcement, betting, bankroll mutation, scheduling, and all non-Official product behavior disabled.

## 2026-07-16 - Team Availability Evidence Foundation

- Added an isolated immutable `app/team_availability` domain for player availability, injuries, suspensions, predicted and confirmed lineups, substitutes, formations, evidence state, conflicts, and safe ingestion audit data.
- Added migration v6 with separate availability-source, player-observation, lineup-observation, and lineup-player tables using insert-once uniqueness and deterministic fixture/team/player/time lookups.
- Added deterministic freshness, lineup-confirmation, snapshot, conflict-preservation, Quality Gate mapping, shadow enrichment, backtesting leakage, and no-op player-impact foundations.
- Added Static, Null, and honest existing-football-API adapters; the current API surface does not expose lineup, injury, suspension, player, coach, or squad evidence and therefore produces no fabricated records.
- Added disabled-by-default one-shot runtime ingestion without scheduling, network activation, Telegram publication, bankroll mutation, betting, or Quality Gate enforcement.

## 2026-07-16 - Opponent-Adjusted Form and xG Evidence Foundation

- Added an isolated immutable `app/form_features` domain for normalized completed-match observations, raw and venue form, deterministic recency weighting, transparent opponent adjustment, conflicts, evidence status, and safe ingestion reports.
- Added migration v7 with insert-once historical match observations, lossless Decimal text fields, fixture/team/competition indexes, restart persistence, and no changes to migrations v1-v6.
- Added deterministic on-demand snapshots for wins/draws/losses, points, goals, clean sheets, failed-to-score counts, goal rates, venue splits, weighted form, opponent-adjusted attack/defense, freshness, completeness, exclusions, and result/goal-rate divergence.
- Added strict no-fake-xG contracts: the existing finished-fixtures provider supplies goals but no genuine xG, shots, cards, penalties, possession, event timing, or player data, so those fields remain explicitly missing.
- Added provider, ingestion, Quality Gate context, shadow enrichment, walk-forward backtesting, disabled-by-default runtime, Null-provider, and prediction-isolation foundations without enabling publication, betting, bankroll mutation, scheduling, or non-Official products.

## 2026-07-16 - Production Calibration Fitting

- Added deterministic Platt fitting using clipped logit inputs, damped Newton/IRLS optimization, L2 regularization, explicit convergence rules, immutable coefficients, diagnostics, and typed unsupported-fit failures.
- Added deterministic Isotonic fitting using grouped Pool Adjacent Violators regression with weighted blocks and right-continuous piecewise-constant prediction and extrapolation.
- Added scope-aware sample and class-balance policies, explicit broader-scope and Identity fallback audit trails, fitted walk-forward target outputs, and conservative validation-window method selection.
- Added stable versioned JSON-safe calibrator serialization with lossless Decimal strings, strict malformed/version rejection, and safe positive-infinite Log Loss representation.
- Kept calibration fitting isolated from live prediction generation, Quality Gate enforcement, Telegram, bankrolls, scheduling, betting, and non-Official products.

## 2026-07-16 - Calibration Registry and Model Monitoring Foundation

- Added an immutable calibration artifact registry using the existing safe versioned calibrator JSON contract, deterministic artifact identity, idempotent equivalent-artifact registration, and audited explicit status transitions.
- Added migration v8 with isolated calibration artifact, status-history, model-monitoring run, and alert tables using lossless Decimal text, deterministic JSON, insert-once constraints, immutable triggers, and indexed scope/status/time queries.
- Added deterministic fixed-count, interval, rolling, and explicit monitoring windows driven only by caller-supplied timestamps.
- Added model performance reports by reusing the existing backtesting and calibration metric services for hit rate, ROI, profit, drawdown, Brier Score, Log Loss, ECE, MCE, and CLV.
- Added conservative threshold-based drift findings, fixed-bin PSI with explicit epsilon smoothing, existing reliability-bin drift, insufficient-sample protection, persisted one-shot monitoring runs, and idempotent alerts.
- Added authoritative Official, settled Quality Gate Shadow, and backtesting monitoring adapters with deterministic Shadow-stage selection and Official-to-Shadow-to-backtesting deduplication priority.
- Kept calibrator activation, automatic promotion or retirement, live prediction changes, Quality Gate enforcement, Telegram alerts/publication, bankroll mutation, betting, scheduling, and non-Official products disabled.

## 2026-07-16 - Risk, Stake Recommendation, and Exposure Assessment Foundation

- Added an isolated immutable `app/risk_management` domain that consumes supplied bankroll and exposure snapshots and returns structured ELIGIBLE, REDUCED_STAKE, REVIEW_REQUIRED, or INELIGIBLE audit decisions.
- Added a transparent Official-only default stake policy using unrounded Decimal 1%, 2%, and 3% internal bands, final EUR-cent quantization, configurable EV/evidence requirements, and public 1-to-3-star mapping without Telegram formatting.
- Added exact drawdown states at 5%, 10%, and 15%, conservative loss-streak caps, explicit no-martingale behaviour, and deterministic reduction-only precedence.
- Added typed single, daily, competition, fixture, team, market, correlated-group, and unsettled exposure evaluation without reserving or mutating exposure.
- Added Quality Gate consumption, special combo-exception representation, explicit product-policy separation, and historical Shadow recommendation adapters that reject missing or future bankroll snapshots.
- Added deterministic flat-unit, fixed-1%, fixed-2%, and recommended-policy backtesting comparison with ROI, drawdown, losing streak, volatility proxy, stake concentration, skips, and stake/drawdown segmentation.
- Kept automatic staking, bankroll mutation, exposure reservation, Quality Gate enforcement, Telegram changes, scheduling, betting, and all non-Official product activation disabled.

## 2026-07-20 - Probability Calibration Post-Prediction Engine

- Added the isolated deterministic `app/probability_calibration` package as a post-prediction transformation boundary without changing prediction generation.
- Added configuration-selected Identity, Platt Scaling, and Isotonic Regression by composing the existing production calibration fitters.
- Added strict model-version and historical-cutoff validation, monotonic-order enforcement, and `[0.001, 0.999]` output clamping.
- Added immutable reports containing raw and calibrated probabilities, delta, method, Brier Score, Log Loss, ECE, MCE, reliability bins, confidence histograms, timestamp, and model version.
- Added migration v9 with lossless Decimal text storage and database-enforced append-only calibration run history.
- Kept prediction selection, Telegram publication, bankroll, risk management, scheduling, external APIs, and all product policies unchanged.

## 2026-07-20 - Official Publication Quality Gate

- Added the isolated deterministic `app/publication_quality_gate` package for fully prepared Official candidates immediately before publication eligibility.
- Added immutable configurable checks for calibrated probability, Official odds, supplied/recomputed EV, confidence, calibration quality, model health, freshness, supported market semantics, optional lineup/injury evidence, risk, exposure, bankroll scope, and duplicate publication state.
- Added fixed REJECTED, REVIEW_REQUIRED, APPROVED precedence with ordered internal reason codes, explanations, normalized input snapshots, and deterministic SHA-256 fingerprints.
- Added migration v10 with database-enforced append-only Official Quality Gate evaluation history and idempotent identical-candidate persistence.
- Added a fail-closed eligibility wrapper that persists evaluations before forwarding only APPROVED candidates to an injected atomic publisher while leaving claim and retry ownership unchanged.
- Kept prediction generation, market selection, bankroll balances, stake calculation, settlement, result publication, Telegram formatting, scheduling, external APIs, and non-Official products unchanged.

## 2026-07-20 - Official Prediction Candidate Assembly and Publication Orchestration

- Added the isolated deterministic `app/official_prediction_orchestration` application boundary for complete supplied Official facts.
- Added strict model, match, market, calibration, health, risk, exposure, bankroll, and publication-state identity validation with deterministic newest-record selection.
- Added Decimal EV verification that preserves the upstream supplied value and canonical versioned candidate fingerprints over every material selected fact.
- Added persisted gate-before-publisher sequencing, typed dry-run and disabled-publisher outcomes, safe retryable/indeterminate delivery mapping, and identical-input idempotency.
- Added migration v11 with append-only immutable Official orchestration history and safe Quality Gate foreign-key linkage.
- Added a production service factory without scheduling, startup publication, fake production data, direct Telegram calls, bankroll mutation, or non-Official product changes.

## 2026-07-20 - Official Prediction Message Assembly and Atomic Publisher Adapter

- Added the isolated `app/official_prediction_publication` package for deterministic Telegram HTML assembly from approved orchestration and supplied public facts only.
- Added supported Official match-winner, double-chance, totals, and both-teams-to-score formatting; calibrated-only public probability; strict HTML escaping; approved reasoning limits; responsible-betting language; and fail-closed exact-score, unsafe-language, and unsupported-market rejection.
- Added exact 1%, 2%, and 3% public stake-star mapping with conservative lower-band mapping for reduced stakes and rejection of zero or ineligible recommendations.
- Added immutable publication payloads and canonical SHA-256 message fingerprints that exclude raw probability, internal expected value, stake percentage, exposure, calibration metrics, internal audit content, destination identifiers, and credentials.
- Added migration v12 with append-only immutable Official prediction publication events and atomic claim/send/finalize sequencing that distinguishes confirmed retryable failures from indeterminate delivery outcomes.
- Added a concrete publisher adapter and production composition path that reuse the existing Telegram sender and settlement-facing published-prediction writer without changing prediction generation, selection, bankroll, risk, exposure, settlement, result publication, scheduling, or non-Official products.

## 2026-07-20 - Official Prediction Run Coordinator and Manual Batch Boundary

- Added the isolated `app/official_prediction_run_coordinator` application layer over the existing single-prediction orchestration callable.
- Added injected persisted-candidate discovery, explicit Official-only state classification, deterministic kickoff/creation/prediction ordering, bounded lookahead and batch limits, immutable-fingerprint rejection freshness, and dry-run-only force review without bypassing the Quality Gate.
- Added centralized confirmed-failure retry limits and cooldowns while permanently blocking automatic published, active-claim, indeterminate, expired, malformed, non-Official, and unchanged rejected/review-required candidates.
- Added sequential failure-isolated batch execution, exact orchestration outcome mapping, validated immutable counters, safe stop-after-failure policy, structured status-only logging, and no hidden time, randomness, fetching, or startup execution.
- Added canonical SHA-256 run idempotency, existing-terminal result reuse, incomplete-run replay blocking, and migration v13 with append-only immutable run start/terminal events and ordered item outcomes.
- Added `build_official_prediction_run_coordinator(...)` and the explicit dry-run-default `run_official_prediction_batch(...)` manual callable without scheduling, provider ingestion, real credential construction, or changes to prediction, bankroll, risk, publication, settlement, or non-Official product logic.

## 2026-07-21 - Official Prediction Candidate Ingestion and READY Registry

- Added the isolated `app/official_prediction_candidate_registry` boundary for complete supplied pre-match Official facts without prediction, calibration, EV, risk, exposure, bankroll, Quality Gate, message, or publication calculations.
- Added strict Official-only market, identity, Decimal, timestamp, scope, live/accumulator, and structured reasoning validation with deterministic Unicode, whitespace, identifier, market, selection, line, Decimal, timestamp, and reasoning normalization.
- Added canonical logical-identity and material-content SHA-256 fingerprints; source events remain provenance, registration time remains audit-only, and identical content is idempotent across ingestion attempts.
- Added append-only READY, SUPERSEDED, WITHDRAWN, and INVALIDATED lifecycle history with transaction-safe version allocation, concurrent ingestion protection, explicit withdrawal/invalidation, published-state protection, and no hard deletion or historical reactivation.
- Added migration v14 with immutable Official candidate version and lifecycle-event tables, unique content and logical-version identities, deterministic snapshots, foreign keys, discovery indexes, and update/delete prevention triggers.
- Added a registry-backed coordinator source and injected assembly-context port that preserve registry traceability while leaving calibration, model-health, risk, exposure, bankroll, Quality Gate, atomic publication, and retry selection in the existing orchestration stack.
- Added `build_official_prediction_candidate_registry(...)`, `build_registry_candidate_source(...)`, and the explicit `register_official_prediction_candidate(...)` callable without automatic ingestion, scheduling, external providers, or startup execution.

## 2026-07-21 - Pre-Match Data Snapshot and Feature Store Foundation

- Added isolated `app/match_data_snapshot` and `app/feature_store` packages for supplied pre-match provenance and deterministic model-ready features without provider, prediction, candidate, or publication coupling.
- Added strict partial-data-preserving validation and normalization for identity, timing, status, form, venue splits, season aggregates, head-to-head, availability, context, and optional odds using Unicode, UTC, and lossless Decimal contracts.
- Added logical match identity and complete material-content SHA-256 fingerprints, idempotent identical registration, sequential immutable versions, and append-only ACTIVE, SUPERSEDED, WITHDRAWN, and INVALIDATED history.
- Added the centralized 78-feature `official_prematch_features_v1` registry, Decimal-only final quantization, explicit zero-denominator/missingness rules, completeness/sample/evidence indicators, and odds/future-data leakage protection.
- Added deterministic feature fingerprints and append-only feature-set history linked to source snapshots, plus explicit historical replay without enabling inactive snapshots by default.
- Added migration v15 with immutable `match_data_snapshot_versions`, `match_data_snapshot_lifecycle_events`, and `match_feature_sets` tables, safe indexes, unique identities, foreign keys, and update/delete triggers.
- Added `build_match_data_snapshot_service(...)`, `register_match_data_snapshot(...)`, `build_feature_store_service(...)`, and `generate_match_feature_set(...)` without external fetching, automatic ingestion, scheduling, prediction generation, training, live processing, or startup execution.

## 2026-07-21 - Prediction Model Input Builder

- Added isolated `app/model_input_builder` as the deterministic bridge from persisted Feature Store output to future machine-learning engines, without implementing or invoking inference or prediction logic.
- Added immutable `goalvision_model_input_v1` with fixed registry-derived 78-feature ordering, typed per-position metadata, explicit compatibility, source snapshot/feature provenance, and no dictionary-dependent ordering.
- Added strict persisted-provenance and canonical Feature Store fingerprint verification, schema/compatibility enforcement, duplicate/unknown/order checks, type and finite-Decimal validation, and fail-closed required recent-form baselines.
- Added missing-value preservation with an ordered boolean mask, ordered missing-feature list, and deterministic available-position completeness score; no zero or learned imputation is performed.
- Added canonical model-input SHA-256 identity over schema, compatibility, ordered names/typed values, missingness, and source feature fingerprint while excluding execution time.
- Added migration v16 with immutable append-only `model_input_vectors`, unique identities, deterministic serialization, Feature Store foreign-key linkage, indexes, and update/delete triggers.
- Added `build_model_input_builder(...)` and `generate_model_input(...)` without training, inference, probability calibration, odds, market, candidate registry, Quality Gate, bankroll, Telegram, scheduling, or live coupling.

## 2026-07-21 - Official Selection-to-Risk and Candidate Preparation

- Added isolated `app/official_candidate_preparation` to re-verify one persisted selected decision and value assessment, consume explicit immutable Official EUR bankroll/exposure facts, and call the existing risk service exactly once.
- Added explicit pre-publication-gate risk phase semantics without claiming Quality Gate approval or changing existing post-gate behavior, stake thresholds, exposure limits, bankroll logic, or selection policy.
- Registered candidates only for exact `ELIGIBLE` or `REDUCED_STAKE` outcomes; persisted `REVIEW_REQUIRED` and `INELIGIBLE` as typed no-registration decisions without a Candidate Registry call.
- Preserved selection, model, calibration, value, risk, stake, bankroll, and exposure provenance while leaving candidate identity, versioning, lifecycle, and publication protection under Candidate Registry authority.
- Added migration v21 with immutable append-only preparation execution/risk snapshot tables, structured candidate provenance, deterministic fingerprints, query indexes, foreign keys, and update/delete triggers.
- Added production composition, explicit callable, read-only downstream Quality Gate handoff, idempotent terminal replay, conflict handling, recovery-safe registry interaction, and comprehensive integration/migration/regression tests.

---

# NEXT PRIORITIES

- [x] Probability Calibration Engine foundation.
- [x] Publication Quality Gate foundation.
- [x] Quality Gate shadow-mode persistence foundation.
- [x] Safe disabled-by-default runtime observation.
- [x] Shadow settlement enrichment foundation.
- [x] Shadow comparison reporting foundation.
- [x] Odds domain foundation.
- [x] Odds persistence foundation.
- [x] CLV calculation foundation.
- [x] Consensus and disagreement foundation.
- [x] Shadow odds-enrichment adapter.
- [x] Provider adapter contracts.
- [x] Team availability domain foundation.
- [x] Lineup and injury persistence.
- [x] Deterministic availability snapshots.
- [x] Quality Gate availability adapter.
- [x] Shadow availability enrichment.
- [x] Team availability provider adapter contracts.
- [x] Opponent-adjusted form foundation.
- [x] Historical match normalization and persistence.
- [x] Deterministic form snapshots.
- [x] Venue and recency weighting.
- [x] Genuine xG evidence contracts and no-fake-xG policy.
- [x] Quality Gate form adapter.
- [x] Shadow form enrichment.
- [x] Backtesting form adapter.
- [x] Production Platt fitting.
- [x] Production Isotonic fitting.
- [x] Deterministic calibrator serialization.
- [x] Walk-forward fitted calibration.
- [x] Calibration method comparison and conservative selection.
- [x] Calibration artifact registry foundation.
- [x] Immutable artifact status history.
- [x] Deterministic model performance reports.
- [x] Drift detection foundation.
- [x] Persisted monitoring runs and alerts.
- [x] Shadow/backtesting monitoring adapters.
- [x] Risk assessment domain foundation.
- [x] Official stake recommendation foundation.
- [x] Drawdown and loss-streak guards.
- [x] Exposure limit evaluation.
- [x] Public stake-star mapping.
- [x] Shadow risk recommendation adapter.
- [x] Risk-policy backtesting comparison.
- [x] Immutable pre-match match-data snapshots.
- [x] Versioned deterministic feature-store foundation.
- [x] Versioned prediction model-input builder.
- [x] Deterministic prediction inference engine foundation.
- [x] Calibrated market probability assembly foundation.
- [x] Market probability and value assessment foundation.
- Lineup Impact Engine.
- Richer provider-backed Opponent Adjusted xG.

---

# DISCOVERED TASKS

If new work is discovered during development,

add it here.

Do not interrupt higher priority work.

Review after completing the current priority.

- Collect a sufficient settled Quality Gate shadow sample before threshold or enforcement decisions.
- Calibrate Quality Gate thresholds from settled shadow observations.
- Integrate the Quality Gate with prediction selection only after shadow-mode review and explicit production-enforcement approval.
- Integrate approved Quality Gate decisions with Official Telegram publication only after explicit product review.
- Add a persistent active-publication duplicate checker adapter.
- Integrate exposure inputs with the Official bankroll without allowing the gate to mutate balances.
- Integrate a reviewed official odds provider only when genuine licensed/provider data is available.
- Add scheduled odds ingestion only after operational review.
- Automate opening/reference/publication/pre-kickoff/closing role assignment after the observation foundation is proven.
- Add CLV reporting to Official weekly statistics after publication and closing roles are reliably populated.
- Add real-time lineup refresh near kickoff only after a genuine provider endpoint and operational schedule are reviewed.
- Build a calibrated player-strength and lineup-impact model only after reliable minutes, starts, ratings, or internal player-strength inputs exist.
- Integrate a richer licensed event/xG provider only when genuine xG, shots, cards, penalties, possession, and event timing are available.
- Add scheduled historical-form ingestion only after operational review.
- Integrate a reviewed real pre-match model artifact without implicit loading.
- Build calibrated market prediction assembly after inference and calibration evidence is approved.
- Add group-aware calibration only under a new reviewed policy/schema version.

- Gather a sufficient settled Shadow sample before monitoring threshold decisions.
- Statistically tune drift thresholds after sufficient historical evidence exists.
- Add scheduled monitoring execution only after operational review.
- Add Telegram/Admin monitoring alert presentation only after product review.
- Define an automatic artifact promotion policy only after offline and Shadow evidence is sufficient.
- Activate reviewed calibration artifacts in prediction runtime only after explicit approval.
- Persist Shadow risk audit records only after a reviewed persistence consumer exists.
- Integrate authoritative historical bankroll snapshots before historical risk reporting.
- Statistically validate stake and exposure thresholds on separate evaluation samples.
- Integrate exposure with bankroll reservations only after explicit operational review.
- Keep production Quality Gate enforcement disabled pending settled Shadow evidence.
- Build the Publication Quality Gate after calibration is production-proven.
- Add CLV reporting to weekly statistics without changing prediction selection policy.
- Build a reviewed Lineup Impact Engine.
- Build Opponent Adjusted xG as an isolated, backtested feature.
- Replace goals-only form inputs with genuine provider xG only after a reviewed richer provider integration.

- Calibrate Quality Score weights through backtesting.
- Integrate Quality Score into Telegram display only after calibration and product review.
- Consider publication-threshold integration only after calibration proves an explicit threshold improves quality.
- Add expandable deterministic analysis to Telegram only after product review.
- Consider an optional LLM wording layer only after deterministic explanations are proven reliable; it must never alter prediction facts.
- Integrate presentation actions with Telegram interactions only after product review.
- Keep AI Quality Score display blocked until backtest calibration is complete.
- Integrate WON/LOST/VOID result presentation with result publishing in a future task.
- Wire the prediction interaction handler into production Telegram callbacks after product review.
- Implement the future statistics button data lookup and presentation.
- Implement the future bankroll button data lookup and presentation.
- Integrate result-resolution persistence with the production database in a future task.
- Integrate WON/LOST/VOID presentation with Telegram publishing in a future task.
- Integrate resolved results with the correct product bankroll only in a future reviewed task.
- Wire persistent WON/LOST/VOID history into Telegram result publication in a future task.
- Apply resolved outcomes to the correct product bankroll only in a future reviewed task.
- Build weekly statistics from persistent result history in a future task.
- Add persistent database storage for Official bankroll accounts and transactions.
- Add Telegram presentation for Official bankroll snapshots and stake-star ratings.
- Build weekly Official statistics from immutable bankroll transaction history.
- Backtest automatic stake-tier selection before connecting tiers to prediction confidence or AI Quality Score.
- Build separate reviewed bankroll systems for High Risk and Combo without mixing Official history.
- Orchestrate automatic result-to-bankroll settlement only after the explicit workflow is reviewed.
- Add coordinated Telegram result and Official bankroll messages in a future task.
- Build weekly Official statistics from persistent bankroll and result history.
- Calibrate automatic stake-tier selection through backtesting before enabling it.
- Schedule recurring settlement execution only after operational review.
- Publish coordinated Telegram WON/LOST and bankroll messages in a future task.
- Generate weekly Official statistics from settlement reports and persistent histories.
- Add operational settlement monitoring, retry metrics, and alerts.
- Coordinate scheduled settlement and result publication only after operational review.
- Generate weekly Official reports from immutable result and bankroll histories.
- Send publication failures and stuck-delivery claims to the Admin channel in a future task.
- Integrate the operations CLI with application-owned staging/production Telegram credential resolution only after deployment-specific controls are reviewed.
- Keep automatic Official discovery, scheduling, provider ingestion, bankroll/exposure retrieval, and startup execution disabled until separately approved.

## 2026-07-22 - Historical Match Data Import Foundation

- Added the strict `goalvision_historical_dataset_v1` supplied-dataset boundary.
- Added deterministic Unicode/team identity and UTC normalization with
  fail-closed score, result, statistics, lineup, duplicate, and kickoff checks.
- Added canonical SHA-256 identities for dataset content, provider/natural match
  identity, normalized match content, statistics, and lineups.
- Added migration v23 with atomic append-only import, match-version, statistics,
  and lineup persistence plus update/delete rejection triggers.
- Added exact replay idempotency, cross-version match reuse, immutable correction
  versions, conflict detection, and full transaction rollback.
- Kept live fetching, scheduling, provider polling, feature generation, model
  training, prediction, backtesting, publication, Telegram, and startup imports
  outside this foundation.

## 2026-07-22 - Historical Training Dataset Builder Foundation

- Added the immutable `historical_training_features_v1` and
  `historical_training_labels_v1` contracts over explicitly selected imports.
- Added strict source-kickoff-before-target enforcement, independent leakage
  inspection, fixed Decimal-safe feature ordering, masks, provenance, and
  deterministic labels without correct-score output.
- Added centralized last-3/5/10, venue, season, head-to-head, rest/congestion,
  and prior-statistics projection with no target-match or future information.
- Added migration v24 with atomic append-only builds, examples, source linkages,
  exclusions, foreign keys, uniqueness, indexes, and update/delete guards.
- Added immutable request/example/dataset fingerprints, replay idempotency,
  request conflict handling, bounded streaming, and read-only inspection.
- Kept splitting, training, calibration fitting, backtesting, model comparison,
  promotion, shadow evaluation, fetching, scheduling, prediction, publication,
  and Telegram activity outside this foundation.

## 2026-07-22 - Historical Dataset Split Foundation

- Added typed explicit-boundary, ratio-by-chronology, and bounded expanding-
  window split strategies over one immutable verified training dataset.
- Added strict partition chronology, indivisible equal-kickoff groups,
  deterministic ordering, explicit buffer exclusions, and no randomization.
- Added immutable per-fold assignments, achieved counts/ratios, all-11-label
  reporting, bounded partition streaming, and independent integrity inspection.
- Added canonical request, assignment, fold, and complete split SHA-256
  identities with exact replay idempotency and immutable request conflicts.
- Added migration v25 with atomic append-only split, fold, and assignment
  persistence, foreign keys, uniqueness, indexes, and update/delete guards.
- Kept model training, hyperparameter tuning, calibration fitting, inference,
  backtesting, model comparison/promotion, shadow evaluation, fetching,
  scheduling, publication, and Telegram outside this foundation.

## 2026-07-22 - Historical Model Training Foundation

- Added the explicit TRAIN-only `MULTI_TARGET_LOGISTIC_REGRESSION_V1` baseline
  over verified immutable split folds and the exact 145-feature schema.
- Added deterministic TRAIN-fitted median imputation and standard scaling,
  evaluation-only VALIDATION handling, strict TEST isolation, class-support and
  convergence rejection, and canonical raw 11-target probability validation.
- Added safe executable-free JSON-compatible artifacts with ordered parameters,
  convergence evidence, compatibility metadata, complete source provenance,
  descriptive TRAIN/VALIDATION metrics, and read-only inference reproduction.
- Added request, preprocessing, estimator, artifact, and run SHA-256 identities,
  exact replay idempotency, immutable request conflicts, and atomic persistence.
- Added migration v26 with six append-only training/artifact/target/
  preprocessing/example/metric tables, foreign keys, uniqueness, indexes, and
  twelve update/delete guards.
- Kept calibration fitting, backtesting, model comparison/promotion, shadow
  evaluation, live inference wiring, fetching, scheduling, publication, and
  Telegram outside this foundation.

## 2026-07-22 - Historical Probability Calibration Fitting Foundation

- Added explicit VALIDATION-only fitting over one verified training run, model
  artifact, split, and fold; TRAIN is not refitted and TEST is never loaded.
- Reused the runtime identity, Platt, and isotonic fitters with strict support,
  convergence, schema, version, and provenance validation.
- Added seven fitted calibrators, four derived complements, lower-bounded result
  simplex reconciliation, decreasing totals PAVA, and the canonical bounded
  11-target output contract.
- Added per-target and multiclass metrics, deterministic reliability bins,
  diagnostics, and read-only reproduction and compatibility inspection.
- Added migration v27 with six atomic append-only run/artifact/target/
  prediction/metric/reliability tables and twelve mutation guards.
- Added deterministic fingerprints, exact replay idempotency, immutable request
  conflicts, and a deliberately inactive runtime compatibility adapter.
- Kept runtime activation, TEST evaluation, backtesting, model promotion, shadow
  evaluation, fetching, scheduling, publication, and Telegram outside scope.
