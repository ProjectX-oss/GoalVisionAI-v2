# Historical Training Dataset Builder

`app.historical_training_dataset` transforms explicitly selected immutable
historical imports into deterministic, append-only model-training examples. It
does not train or run a model, fit calibration, split datasets, backtest,
predict, fetch data, publish, schedule work, or contact Telegram.

## Strict temporal boundary

For a target kickoff `T`, every contributing source match must have kickoff
strictly less than `T`. Equal-kickoff, later same-day, later-round, later-season,
and all future matches are unavailable. The target score is used only for labels;
target statistics, attendance, referee, half-time facts, and lineups never enter
features. Imported lineups currently have no independently proven pre-kickoff
effective timestamp, so v1 excludes them. Missing or uncertain timestamps fail
closed. Independent inspection rechecks every persisted source linkage.

Default policy `historical_training_dataset_policy_v1` requires three earlier
matches for each team, uses rolling windows of 3, 5, and 10, caps head-to-head at
five earlier meetings, and orders matches by kickoff, competition identity, then
historical match ID. There is no same-kickoff ordering assumption.

## Feature schema

`historical_training_features_v1` contains 145 fixed positions. Each registry
entry declares index, name, type, semantic definition, source window,
missingness rule, and leakage classification. It includes, for both teams:

- last-3, last-5, and last-10 form, goals, result, clean-sheet, BTTS, and totals;
- last-10 home/away venue splits;
- competition-and-season-to-date and season venue-split aggregates;
- rest days and 7/14-day congestion;
- last-10 prior-match averages for optional possession, shots, shots on target,
  xG, corners, cards, fouls, and offsides;
- five-meeting head-to-head counts, outcomes, goals, BTTS, and over-2.5.

This is an explicit historical schema, not a claim of binary compatibility with
the live 78-position `official_prematch_features_v1` schema. Concepts such as
recent points/goals, venue form, season form, xG, rest, and head-to-head map
semantically; live availability/context concepts without timestamped historical
evidence remain outside v1. All ratios use Decimal and quantize to `0.000001`.

Missing optional facts remain `None` with a parallel ordered boolean mask. No
implicit imputation, random sampling, class balancing, or splitting occurs.
Eligible incomplete examples are `INCLUDED_WITH_MISSINGNESS`; targets below the
minimum history are `EXCLUDED_INSUFFICIENT_HISTORY`; uncertain per-target
provenance is `EXCLUDED_INVALID_PROVENANCE`.

## Labels

`historical_training_labels_v1` contains exactly 11 binary labels: home/draw/away,
over and under 1.5/2.5/3.5, and BTTS yes/no. Result labels are one-hot,
complements sum to one, and over totals are monotonic. Correct score, scorer,
half-time, and live labels are intentionally absent.

## Identity, persistence, and inspection

SHA-256 fingerprints cover the normalized build request; the owning request
fingerprint (which keeps the same match valid in distinct datasets), each match fingerprint,
strict cutoff, ordered sources, ordered vector, mask, completeness, labels, and
schema/policy versions; and the ordered complete dataset with exclusions. JSON
keys are sorted and Decimal serialization is canonical. Exact request replay
returns the existing build without writes; reused request IDs with different
content return `CONFLICT`.

Migration v24 adds append-only tables for dataset builds, examples, example
sources, and exclusions. Foreign keys, uniqueness rules, indexes, and eight
update/delete triggers protect history. A single `BEGIN IMMEDIATE` transaction
persists the complete build or rolls it all back.

Read-only helpers summarize datasets, inspect examples, recheck temporal
leakage, recompute fingerprints, and validate labels. Example streaming uses a
bounded iterator in deterministic order.

Machine-learning flow:

```text
historical import
  -> historical training dataset
  -> dataset split
  -> model training
  -> calibration training
  -> historical backtesting
  -> model comparison and promotion
  -> shadow evaluation
```

The next explicit layer is `app.historical_dataset_split`, which independently
rechecks dataset/example fingerprints, labels, and leakage before assigning
chronology-safe partitions. Model training, calibration fitting, backtesting,
comparison/promotion, and shadow evaluation remain separately reviewed layers.
