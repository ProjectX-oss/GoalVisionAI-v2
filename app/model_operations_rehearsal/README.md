# Model Operations Lab Rehearsal

This package is a manual, inert development aid. It creates two timestamped
copies of one explicitly selected SQLite database: a byte-identical backup and
a separate Lab rehearsal database. Only the rehearsal copy is migrated and
seeded.

The seeded model, promotion, and shadow records are deterministic fictional
fixtures labeled `FICTIONAL_LAB_REHEARSAL_ONLY`. They exercise typed services
and append-only repositories. They are not scientific evidence and must never
be interpreted as an approval for production.

The package has no startup import, scheduler, Telegram integration, activation
execution, rollback execution, or automatic publication path.

Example:

```text
python -m app.model_operations_rehearsal.cli prepare-lab-db \
  --source-database data/goalvision.db \
  --destination-directory var/lab_rehearsal
```
