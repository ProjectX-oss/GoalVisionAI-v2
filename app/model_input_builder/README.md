# Prediction Model Input Builder

`app.model_input_builder` is the deterministic bridge between persisted Feature
Store output and future machine-learning engines. It accepts one immutable
`MatchFeatureSet`, validates its persisted provenance and canonical fingerprint,
and emits one immutable `goalvision_model_input_v1` vector. It does not perform
training, inference, probability generation or calibration, market or odds work,
candidate registration, Quality Gate evaluation, bankroll work, publication,
scheduling, or live processing.

The explicit production boundaries are
`build_model_input_builder(database)` and
`generate_model_input(service, feature_set)`. Construction applies additive
migration v16 only; generation never invokes another application workflow.

## Schema and ordering

`goalvision_model_input_v1` is compatible with Feature Store schema
`official_prematch_features` version `v1` and compatibility contract
`official_prediction_model_input_v1`. Its 78 positions come directly from the
immutable Feature Store definition registry. Each position has an index, name,
type, description, required-baseline flag, and source schema. No dictionary is
used to decide vector order.

The six required baseline features are home/away recent points, goals scored,
and goals conceded per match. Optional xG, venue, season, availability,
head-to-head, and context features may remain missing.

## Missing values and validation

Missing values remain `None`; they are never replaced with zero. Every vector
contains an ordered boolean missingness mask, ordered missing-feature names, and
an available-position completeness score quantized to `0.000001`. Genuine
integer zero and boolean false remain ordinary non-missing values.

Generation rejects unpersisted or unsupported feature sets, incompatible schema
or compatibility versions, snapshot or feature provenance mismatches, malformed
SHA-256 identities, duplicate, unknown, missing, or reordered feature names,
non-boolean or contradictory missingness, missing required baselines, malformed
types, and non-finite Decimal values. The Feature Store fingerprint is recomputed
over the full source feature payload before construction.

## Identity and persistence

The model-input SHA-256 covers schema name/version, compatibility version,
ordered feature names, ordered typed values, ordered missingness mask, and source
feature fingerprint. Execution and repository time are excluded. Identical source
features and schema therefore produce the same vector and return the existing
record.

Migration v16 adds append-only `model_input_vectors`, with a foreign key to
`match_feature_sets`, unique input fingerprint and feature/schema identity,
deterministic JSON/Decimal serialization, lookup indexes, and update/delete
prevention triggers.

Future reviewed flow:

```text
register_match_data_snapshot(...)
  -> generate_match_feature_set(...)
  -> generate_model_input(...)
  -> generate_raw_prediction(...)
  -> probability calibration
  -> future prediction generation
```

`app.prediction_inference` is the separate downstream owner of raw probability
generation. No model, prediction, probability, market, candidate, or publication
logic is implemented in the model-input package.

Offline historical examples use `historical_training_features_v1`, whose
ordering and semantics are documented independently. They are not silently fed
to `goalvision_model_input_v1`; a future reviewed training layer must declare an
explicit schema mapping or train an artifact against the historical schema.

Shadow evaluation requires both compared artifacts to declare the exact shared
input schema, fingerprint, and feature order. Model-specific persisted
preprocessing remains separate, and shadow never invokes this builder
automatically.
