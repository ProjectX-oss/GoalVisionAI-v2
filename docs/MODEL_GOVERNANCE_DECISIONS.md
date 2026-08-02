# Model Governance Decisions

Decision precedence is fail closed: insufficient evidence, integrity-critical blocks, consecutive severe failures, scoped failures, warnings, monitoring, then clear. Each append-only decision names its primary reason, secondary reasons, affected scopes, publication impact, operator action, next sample threshold, and fingerprint.

New model generations and calibration artifacts begin with insufficient or warm-up evidence. The comparison report can classify genuine shared evidence as insufficient, unchanged, improved, degraded, or mixed, but it cannot activate or roll back anything.

Warning acknowledgement is append-only and does not clear mathematical status. Resume requires the configured number of fresh, clear evaluations. Stale evidence cannot recover a pause.
