# Calibration Quality Review

This package derives immutable, deterministic quality evidence from an existing
historical calibration artifact, its exact VALIDATION predictions, and one live
model input. It never refits a calibrator, changes an artifact, discovers data,
publishes a prediction, or calls Telegram.

The review keeps four decisions separate:

- whether analysis and inspection may complete;
- mathematical market rank;
- calibration-quality actionability;
- Lab Telegram send eligibility.

Controlled-synthetic evidence can be inspected and replayed, but is never send
eligible. Official remains independently fail-closed.

Reports are stored inside the existing immutable Real Match Lab result snapshot
and per-market evaluation snapshots. This preserves append-only, replay-safe,
foreign-key-protected persistence without a schema migration. Legacy snapshots
without a report display `CALIBRATION_QUALITY_NOT_EVALUATED` and fail closed.
