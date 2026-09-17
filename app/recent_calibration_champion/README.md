# Recent live-78 champion inspection

This package is a read-only, fail-closed Lab/staging boundary. It resolves the
active append-only champion generation, verifies the canonical 78-position
model schema and immutable model/calibration fingerprints, and reports runtime
calibration freshness.

Freshness v2 derives its evidence timestamp from the newest immutable labelled
VALIDATION example linked to the persisted calibration run. The fit command's
`calibration_timestamp` remains the artifact creation time and cannot refresh
underlying evidence. Lab/staging evidence is reviewed against a conservative
366-day maximum and a separate 24-hour audit-review lifetime. Official remains
fail-closed because no production lifetime has been established from controlled
synthetic evidence. Bookmaker, feature, and lineup clocks remain separate.

The report never fits, edits, activates, publishes, sends Telegram messages, or
mutates bankrolls. Missing metadata, negative age, stale age, schema drift, a
resolver failure, or a non-passing independent audit rejects the report. Legacy
artifacts without complete evidence linkage remain readable but non-actionable.
