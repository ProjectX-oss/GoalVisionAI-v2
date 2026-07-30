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

The current activated historical artifacts declare the 145-position
`historical_training_features_v1` contract, while the pre-match Feature Store
produces the 78-position `goalvision_model_input_v1` contract. The engine
deliberately rejects this mismatch with `MODEL_INPUT_SCHEMA_INCOMPATIBLE`.
No hidden remapping, imputation, placeholder inference, or fictional probability
is used. A successful real preview requires a reviewed champion artifact trained
for the live Feature Store contract.

See `docs/REAL_MATCH_LAB_ANALYSIS_RUNBOOK.md` for the operator procedure.
