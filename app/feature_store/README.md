# Deterministic Pre-Match Feature Store

`app.feature_store` converts exactly one immutable match-data snapshot into one
versioned model-ready feature set. It consumes snapshot facts only. It never fetches
data, uses odds as model inputs, generates or calibrates probabilities, evaluates
betting value, registers Official candidates, or publishes.

The explicit callable is `generate_match_feature_set(...)`; production composition
uses `build_feature_store_service(database)`. Schema
`official_prematch_features_v1` is stored as name `official_prematch_features`,
version `v1`, and compatibility version `official_prediction_model_input_v1`.
The centralized immutable registry in `definitions.py` fixes order, type,
description, source fields, formula, missing-data behavior, valid range, and schema
introduction for all 78 features.

## Formula and missing-data policy

Points per match is `(3*wins + draws) / matches`; scoring, concession, xG,
clean-sheet, failed-to-score, BTTS, and over-2.5 rates divide supplied totals by
their supplied samples. Goal/xG differences subtract rates, comparison features use
documented home/away direction, combined total rates add both sides, combined
clean-sheet/failed-to-score rates take their mean, and normalized position is
`(away position - home position) / max(position)`. Availability and context values
remain supplied counts/booleans; competition stage uses a fixed integer vocabulary.

All arithmetic uses `Decimal`. Division is centralized, zero denominators produce
missing values, and values quantize once at the final `0.000001` boundary using
half-even rounding. Missing optional facts never become feature zero. Every feature
has a parallel missingness flag. Sample-size and availability indicators are
explicit quality features, where zero/false has documented semantics. No mean or
learned imputation exists.

Feature generation requires an internally consistent scheduled pre-match snapshot,
both recent-form baselines, matching content fingerprint, supported schema, and a
feature timestamp exactly equal to snapshot effective time. Only `ACTIVE` snapshots
are accepted unless the caller explicitly requests historical replay. These checks,
the source-only extractor, and the complete exclusion of odds, results, scores,
post-kickoff facts, probabilities, labels, and betting outcomes prevent leakage.

The feature SHA-256 covers source snapshot ID/fingerprint, schema name/version,
model compatibility, ordered names/values, missingness, quality summary, and feature
timestamp. Repository identity, logging, and ingestion execution time are excluded.
Migration v15 adds immutable `match_feature_sets` with deterministic text snapshots,
a foreign key to snapshot history, unique fingerprints/schema identities, indexes,
and update/delete prevention triggers.

Future reviewed flow:

```text
external/provider adapter
  -> register_match_data_snapshot(...)
  -> generate_match_feature_set(...)
  -> generate_model_input(...)
  -> prediction generation
  -> register_official_prediction_candidate(...)
```

The deterministic model-input assembly boundary now exists in
`app.model_input_builder`; provider adapters, automatic ingestion, scheduling,
training, model inference, prediction generation, live processing, and publication
remain intentionally deferred.
