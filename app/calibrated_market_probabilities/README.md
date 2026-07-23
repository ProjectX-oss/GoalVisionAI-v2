# Calibrated Market Probabilities

This package is the deterministic boundary from one persisted raw inference to
one immutable calibrated probability assembly. It resolves an explicit artifact
for each of the 11 canonical inference targets, invokes the existing probability
calibration engine exactly once per target, validates the combined result, and
persists the aggregate atomically.

Artifacts explicitly declare identity, Platt, or isotonic calibration, source
model compatibility, probability schema, calibration policy/version, historical
fit data, timestamps, and quality references. Identity is never a fallback: it
must be registered like every other artifact. The immutable registry performs no
file scanning, downloading, fitting, or “latest” selection.

Selection uses exactly one mode: a complete ordered target-to-artifact map, or an
explicit active calibration-set ID. Sets cover every target exactly once and have
their own deterministic fingerprint. Inactive artifacts and sets remain
queryable but are not automatically resolved.

Independent target calibration can break group consistency. The v1 policy does
not normalize, redistribute, or repair. Calibrated values must be within
`[0.001, 0.999]`; match-result, totals complements, and BTTS must sum to one
within tolerance; totals must remain monotonic. Violations reject the entire
assembly and no target rows are persisted. Future group-aware calibration needs
a new policy/schema version.

The current calibration engine does not expose a distinct clamp-event flag, so
the per-target `clamping_indicator` is preserved as unavailable (`None`) rather
than inferred. The calibrated value itself still follows the engine's configured
`[0.001, 0.999]` bounds.

Migration v18 adds append-only `probability_calibration_sets`,
`calibrated_market_probability_assemblies`, and
`calibrated_market_probability_targets`, with deterministic Decimal/JSON
serialization, foreign keys, uniqueness, indexes, and mutation-prevention
triggers. Aggregate and target rows are one transaction.

The production boundaries are `build_calibrated_market_probability_service(...)`
and `generate_calibrated_market_probabilities(...)`. Every dependency and the
effective timestamp are explicit. `to_future_market_probability_input(...)`
provides read-only calibrated/raw/model/calibration provenance for later market
assembly. `app.market_value_assessment` is the separate supplied-odds consumer;
this package itself remains without odds, EV, risk, candidates, Quality Gate, or
publication.

Future flow:

```text
match snapshot -> feature store -> model input -> raw inference
  -> calibrated market probabilities -> future market prediction assembly
  -> odds/value assessment -> risk/exposure -> candidate registry
  -> Quality Gate -> publication
```

Calibration training/retraining, odds, EV, selection, staking, candidate
registration, and publication integration are intentionally deferred.

`app.historical_probability_calibration` now owns offline VALIDATION-only
fitting and maps persisted artifacts only to inactive runtime-compatible
objects. Registration and activation remain an explicit reviewed future action.

Shadow evaluation applies each model's explicitly linked historical
calibration artifact exactly once and re-verifies the canonical contract.
Those assemblies remain isolated v30 evidence and never enter a live registry.
