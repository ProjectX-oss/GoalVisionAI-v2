# Controlled staging model-operations rehearsal

This package is a manual, isolated `STAGING`-only boundary. It inventories one
explicit source database read-only, verifies its SHA-256 and migration history,
creates a byte-identical backup and disposable copies under the Git-ignored
`var/staging_rehearsal/` directory, then reuses the existing audit,
model-operations, activation, rollback, resolver, and rehearsal boundaries.

The independent audit CLI runs in the separate typed preflight mode before
bootstrap and again before execution. The complete audit runs after activation
and rollback. Both human and canonical JSON paths are required.

Real persisted artifact chains are inventoried first. Incomplete or ambiguous
chains are rejected. Fixture fallback requires the explicit CLI flag and every
new fixture chain carries `FICTIONAL_STAGING_REHEARSAL_ONLY`; real and fictional
evidence are never mixed.

```text
python -m app.staging_model_operations_rehearsal.cli run \
  --source-database data/goalvision.db \
  --destination-directory var/staging_rehearsal/run-20260725 \
  --environment STAGING \
  --scope OFFICIAL_GLOBAL \
  --timestamp 20260725T120000Z \
  --source-commit 78f218632fafe4ceeab708b5dd92dbd1e48a890f \
  --artifact-mode prefer-real \
  --allow-fixture-fallback
```

Production is rejected. There is no startup hook, scheduler, worker, automatic
switching, runtime inference wiring, publication, bankroll, settlement,
statistics, credential, or Telegram integration.
