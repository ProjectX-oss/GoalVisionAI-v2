# Manual Real Match Lab Analysis

`app.real_match_lab_analysis` is an isolated, manual, Lab-only boundary for
exactly one supplied upcoming match. Analysis is dry-run only. The sole network
operation is the separate `send` command, protected by an exact confirmation,
Lab environment, immutable destination, configured bot identity, and an
append-only exactly-once delivery claim.

The production engine composes the existing immutable match snapshot, Feature
Store, model-input builder, controlled champion resolver, raw inference,
calibration, and market-value services. It fails closed if any provenance,
schema, probability, odds, freshness, or model compatibility check fails. It
does not perform fixture discovery, fetch data, schedule work, activate models,
publish Official predictions, or mutate bankroll/statistics.

Legacy artifacts declare the 145-position `historical_training_features_v1`
contract and remain deliberately incompatible. The controlled compatible path
trains new artifacts directly on historical rows projected through the canonical
78-position `goalvision_model_input_v1` authority. No remapping, padding,
truncation, aliasing, or placeholder inference is used.

Before inference the engine verifies schema version, exact ordered names, count,
schema fingerprint, preprocessing input order, missingness format, and
compatibility metadata. It also independently audits the activated generation
against the supplied source commit, validates immutable calibration provenance,
and keeps calibration artifact creation, validation-evidence recency, audit
review validity, features, lineups, and odds on separate clocks. Historical
calibration parameters are applied with their persisted simplex reconciliation,
totals projection, and complement rules before the calibrated assembly is
appended. Missing lineups remain explicitly unavailable; they are never treated
as fresh observations.

See `docs/REAL_MATCH_LAB_ANALYSIS_RUNBOOK.md` for the operator procedure.
