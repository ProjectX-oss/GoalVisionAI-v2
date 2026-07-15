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

---

# NEXT PRIORITIES

- [x] Probability Calibration Engine foundation.
- Publication Quality Gate.
- CLV ingestion.
- Lineup Impact Engine.
- Opponent Adjusted xG.

---

# DISCOVERED TASKS

If new work is discovered during development,

add it here.

Do not interrupt higher priority work.

Review after completing the current priority.

- Implement and review full production Platt coefficient fitting.
- Implement and review full production Isotonic PAV fitting.
- Add calibration persistence and a fitted-version registry.
- Add calibration drift and performance monitoring.
- Build the Publication Quality Gate after calibration is production-proven.
- Add CLV ingestion without changing prediction selection policy.
- Build a reviewed Lineup Impact Engine.
- Build Opponent Adjusted xG as an isolated, backtested feature.

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
