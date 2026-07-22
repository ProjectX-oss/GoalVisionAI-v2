# Historical Dataset Split Foundation

`app.historical_dataset_split` consumes one immutable historical training
dataset and creates reproducible train, validation, and test assignments. It
does not train a model, fit calibration, tune parameters, run inference or
backtests, fetch data, schedule work, publish, or contact Telegram.

## Chronology first

Examples are ordered by kickoff UTC, competition, historical match ID, and
training example ID. Every fold proves:

- maximum TRAIN kickoff is strictly earlier than minimum VALIDATION kickoff;
- maximum VALIDATION kickoff is strictly earlier than minimum TEST kickoff;
- one training example occurs at most once in a fold;
- all examples sharing a kickoff remain together in one active partition or
  share an exclusion classification;
- configured gap examples are `EXCLUDED_GAP` and never enter active partitions.

The source dataset is independently rechecked before any write: dataset and
example fingerprints, schema linkage, labels, source temporal leakage, duplicate
identities, deterministic order, and canonical UTC timestamps must all pass.

## Strategies

`EXPLICIT_TIME_BOUNDARIES_V1` is the default. The caller supplies exclusive
TRAIN end, inclusive/exclusive VALIDATION bounds, inclusive TEST start, and an
optional exclusive TEST end. Any interval between adjacent partitions must
match the explicit gap configuration.

`RATIO_BY_CHRONOLOGY_V1` requires positive Decimal-safe ratios summing exactly
to one. Boundaries are selected deterministically only between whole equal-
kickoff groups. Reported achieved ratios describe actual assignments; the
implementation never shuffles, samples, balances, or changes labels.

`EXPANDING_WINDOW_V1` creates a bounded explicit number of folds. Each step
advances validation and test windows while TRAIN includes all eligible history
strictly before the next training boundary. One example may therefore become
TRAIN in a later fold, but never belongs to two partitions in the same fold.

## Assignments and exclusions

Every persisted assignment records split/fold identity, source example and
match identity, kickoff, competition, season, partition, deterministic order,
source example fingerprint, assignment fingerprint, and optional exclusion
reason. Supported values are TRAIN, VALIDATION, TEST, EXCLUDED_GAP,
EXCLUDED_FILTER, EXCLUDED_BOUNDARY_GROUP, and
EXCLUDED_INVALID_PROVENANCE. Invalid source integrity normally rejects the
whole request before persistence; the last status remains reserved for an
explicit future policy that can prove safe per-example exclusion.

Partition label summaries report all 11 immutable training labels with zeros
where absent. Reporting never reweights, resamples, or mutates labels.

## Identity and persistence

Canonical SHA-256 identities cover the normalized request, each assignment,
each fold, and the complete split. Exact request replay returns the existing
split without writes. Reusing a request ID with changed content returns
`CONFLICT`. A source dataset may own multiple distinct split plans.

Migration v25 adds append-only `historical_dataset_splits`,
`historical_dataset_split_folds`, and
`historical_dataset_split_assignments`. Foreign keys, uniqueness constraints,
indexes, and six update/delete triggers protect the audit history. One
`BEGIN IMMEDIATE` transaction persists the full split or rolls it back.

Read-only inspection summarizes plans and label distributions, inspects folds
and assignments, verifies exclusivity, chronology, equal-kickoff grouping,
fingerprints, and source linkage, and streams partition examples in bounded
deterministic order.

```text
historical import
  -> historical training dataset
  -> historical dataset split
  -> model training
  -> historical probability calibration fitting
  -> historical backtesting
  -> model comparison and promotion
  -> shadow evaluation
```

`app.historical_model_training` is the explicit next layer. It independently
re-verifies the split and fold, fits preprocessing and model parameters from
TRAIN only, may inspect VALIDATION without fitting from it, and never loads TEST.
The calibration fitting boundary now exists in
`app.historical_probability_calibration`; it consumes VALIDATION only after a
model training run. Backtesting, comparison/promotion, and shadow evaluation
remain deliberately deferred.
