# Model Operations Lab Rehearsal

This package is a manual, inert development aid. It creates two timestamped
copies of one explicitly selected SQLite database: a byte-identical backup and
a separate Lab rehearsal database. Only the rehearsal copy is migrated and
seeded.

The seeded model, promotion, and shadow records are deterministic fictional
fixtures labeled `FICTIONAL_LAB_REHEARSAL_ONLY`. They exercise typed services
and append-only repositories. They are not scientific evidence and must never
be interpreted as an approval for production.

The package has no startup import, scheduler, Telegram integration, automatic
activation, automatic rollback, or publication path. Execution is available
only through the explicit disposable rehearsal command below.

Example:

```text
python -m app.model_operations_rehearsal.cli prepare-lab-db \
  --source-database data/goalvision.db \
  --destination-directory var/lab_rehearsal
```

The explicit end-to-end execution rehearsal creates a deterministic prepared
foundation, copies it to a new disposable database, then invokes the real model
operations CLI in subprocesses:

```text
python -m app.model_operations_rehearsal.cli \
  execute-activation-rollback-rehearsal \
  --source-database data/goalvision.db \
  --destination-directory var/lab_rehearsal
```

It requires the real `ACTIVATE_CHAMPION` and `ROLLBACK_CHAMPION` confirmation
phrases, verifies every state transition, and never imports Telegram or
application startup wiring.
