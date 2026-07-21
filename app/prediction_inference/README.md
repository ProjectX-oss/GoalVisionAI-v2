# Prediction Inference Engine Foundation

`app.prediction_inference` is the deterministic boundary between one immutable
`goalvision_model_input_v1` vector and one immutable set of raw, uncalibrated
football probabilities. It has no model training, file discovery, downloads,
provider access, odds, EV, market selection, candidate registration, Quality
Gate, staking, publication, scheduling, or live-betting behavior.

The production factory requires an explicit repository, immutable registry, and
policy. No adapter is created or activated automatically, and importing or
starting the application performs no inference. Callers use
`generate_raw_prediction(...)` with an explicit model artifact and timezone-aware
effective timestamp.

## Adapter and registry contract

A `PredictionModelAdapter` declares its artifact ID, name, version, family,
accepted input schema/version/compatibility, target tuple, and missing-value
support. It validates compatibility and deterministically returns typed Decimal
outputs. The adapter cannot persist, calibrate, inspect odds, select bets, or
publish. Operational adapter failures must be declared with
`ModelAdapterExecutionError`; unrelated programmer defects are not swallowed.

`PredictionModelRegistry` is functional and immutable: registration returns a
new registry. Artifact IDs and name/version pairs are unique. Models are selected
only by an explicit artifact ID or one explicitly configured active Official
model. Inactive models remain available for explicit testing. There is no
filesystem scan, implicit “latest” selection, download, or bundled fake model.

## Targets and consistency

The canonical order is:

1. `HOME_WIN`, `DRAW`, `AWAY_WIN`
2. `OVER_1_5`, `UNDER_1_5`
3. `OVER_2_5`, `UNDER_2_5`
4. `OVER_3_5`, `UNDER_3_5`
5. `BTTS_YES`, `BTTS_NO`

Every value is a finite `Decimal` in `[0, 1]`, quantized to `0.000001` only
after typed validation. Match-result, each totals complement, and BTTS must sum
to one within policy tolerance. Over probabilities must be non-increasing as the
line rises; under probabilities must be non-decreasing. Invalid sets are rejected
without normalization or repair.

Input validation recomputes the model-input fingerprint and checks persisted
identity, schema, compatibility, all 78 fixed positions, required baselines,
missingness, source provenance, adapter metadata, and effective timestamp.

## Identity and persistence

The inference SHA-256 covers model-input ID and fingerprint, match ID, model
artifact/name/version/family, input schema/version/compatibility, ordered target
values, inference-effective timestamp, and validation policy version. It excludes
duration, repository identity, logging, credentials, and hidden wall-clock time.
Identical effective inference returns the existing record; any identified input,
model, output, policy, or timestamp change creates a different identity.

Migration v17 adds append-only `prediction_inference_results`, a foreign key to
`model_input_vectors`, unique inference fingerprint, canonical JSON/Decimal
snapshots, lookup indexes, and update/delete prevention triggers.

## Calibration boundary and deferred work

`to_calibration_input(result, target)` maps one raw target to a typed downstream
payload while preserving raw probability, target, inference ID/fingerprint, and
model provenance. `app.calibrated_market_probabilities` is the separate owner of
explicit calibration-artifact resolution, execution, combined validation, and
immutable assembly persistence. Raw inference never invokes it automatically.
The reviewed flow is:

```text
match snapshot -> feature set -> model input -> raw inference
  -> calibrated market probabilities -> future market prediction assembly
  -> candidate registry -> Quality Gate -> publication
```

Real model artifacts, training, calibration execution, and prediction-candidate
assembly are intentionally deferred.
