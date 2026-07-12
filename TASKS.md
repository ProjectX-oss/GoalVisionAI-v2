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

TODO

Tasks

Historical predictions.

Accuracy.

ROI.

Win Rate.

League reports.

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

---

# DISCOVERED TASKS

If new work is discovered during development,

add it here.

Do not interrupt higher priority work.

Review after completing the current priority.
