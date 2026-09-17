# Controlled staging model-operations rehearsal

This package is a manual, isolated `STAGING`-only boundary. It checks one
explicit source database read-only, verifies its SHA-256 and migration history,
and creates a byte-identical backup. It then builds a deterministic controlled
artifact chain through the real historical ML services under the Git-ignored
`var/staging_rehearsal/` directory before reusing the existing audit,
model-operations, activation, rollback, resolver, and rehearsal boundaries.

The independent audit CLI runs in the separate typed preflight mode before
bootstrap and again before execution. The complete audit runs after activation
and rollback. Both human and canonical JSON paths are required.

Only `REAL_ONLY` is accepted. There is no fixture fallback. All controlled
historical labels carry `CONTROLLED_SYNTHETIC_STAGING_SOURCE`, and all
downstream artifacts are produced and linked by the genuine domain services.

```text
python -m app.staging_model_operations_rehearsal.cli run \
  --source-database data/goalvision.db \
  --destination-directory var/staging_rehearsal/run-20260728 \
  --environment STAGING \
  --scope OFFICIAL_GLOBAL \
  --timestamp 20260728T130000Z \
  --source-commit 5387bd62cd8b435af5d444aca186219b9c879514 \
  --artifact-mode real-only
```

Production is rejected. There is no startup hook, scheduler, worker, automatic
switching, runtime inference wiring, publication, bankroll, settlement,
statistics, credential, or Telegram integration.
