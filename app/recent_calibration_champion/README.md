# Recent live-78 champion inspection

This package is a read-only, fail-closed Lab/staging boundary. It resolves the
active append-only champion generation, verifies the canonical 78-position
model schema and immutable model/calibration fingerprints, and reports runtime
calibration freshness.

Freshness uses the persisted historical calibration command's
`calibration_timestamp`. The Real Match Lab assembly propagates that value as
`calibration_effective_timestamp`, and market assessment compares it with the
injected assessment clock. The current policy is fresh through 1,800 seconds,
aging through 7,200 seconds, and stale afterward. Artifact creation, activation,
source retrieval, and champion-generation timestamps do not replace this
reference.

The report never fits, edits, activates, publishes, sends Telegram messages, or
mutates bankrolls. Missing metadata, negative age, stale age, schema drift, a
resolver failure, or a non-passing independent audit rejects the report.
