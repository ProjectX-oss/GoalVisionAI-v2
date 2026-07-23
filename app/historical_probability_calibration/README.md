# Historical Probability Calibration Fitting

This package fits deterministic probability calibrators from the immutable
`VALIDATION` partition of a completed historical model-training run. It never
loads `TEST` examples, changes the source artifact, or activates a calibrator at
runtime.

## Contract

- Raw probabilities are reproduced with the persisted source model artifact.
- Identity, Platt scaling, and isotonic regression use the existing runtime
  calibration implementations.
- Seven independent targets are fitted: the three match-result classes, three
  over-goal thresholds, and `BTTS_YES`. Four complementary targets are derived.
- Match-result probabilities are projected onto a lower-bounded simplex.
- Totals are projected with deterministic decreasing PAVA before complements
  are derived.
- All probabilities are clamped to `[0.001, 0.999]`.
- Runs, artifact sets, target artifacts, reproduced predictions, metrics, and
  reliability bins are persisted atomically and append-only by migration v27.
- Request IDs and content fingerprints provide exact replay idempotency and
  conflict detection.

The runtime adapter creates inactive compatibility objects only. Importing this
package performs no fitting, database access, provider access, scheduling,
prediction publication, or Telegram activity.

`app.historical_backtesting` is the only downstream TEST consumer in this ML
flow. It replays these persisted calibrators, lower-bounded result
reconciliation, totals monotonicity, and exact complements without fitting or
altering them. The calibration artifact set remains inactive and immutable.
