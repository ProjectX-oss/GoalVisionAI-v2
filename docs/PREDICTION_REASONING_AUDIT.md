# Prediction reasoning integrity audit

Every persisted reasoning record receives an immutable fail-closed audit. The
audit verifies canonical identity and public-copy fingerprints, analysis/input/
artifact linkage, score and probability reproduction, factor traceability,
prohibited wording and markets, blocker/confidence consistency, factor limits,
message length and explanation stability.

Statuses are:

- `REASONING_AUDIT_PASSED`: publication-gate integrity checks pass.
- `REASONING_AUDIT_WARNING`: evidence is intact but a non-blocking limitation
  needs operator attention.
- `REASONING_AUDIT_BLOCKED`: publication must stop.
- `REASONING_AUDIT_CORRUPT`: fingerprints, reproduction or traceability fail.

Lab publication review requires the exact observation, selected market,
reasoning record and a passed audit. It fingerprints the base preview together
with the public reasoning. Future manual-send authorization must present that
exact composite message fingerprint. Missing or stale reasoning fails closed.

Audit success validates explanation integrity only. It does not validate the
prediction outcome or prove profitability.
