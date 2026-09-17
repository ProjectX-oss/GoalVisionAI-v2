# Independent model activation audit

This package is an inert, manual, read-only review boundary. It inspects SQLite
schema objects, append-only controls, champion history, activation and rollback
evidence, resolver/CLI architecture, rehearsal evidence, and the operator
runbook. It never imports or calls an activation, rollback, bootstrap,
publication, Telegram, scheduler, worker, or inference execution entry point.

Run against an explicit existing review database:

```text
python -m app.model_activation_audit.cli audit --database <review.db> --environment LAB --scope OFFICIAL_GLOBAL --source-commit <full-commit> --generated-at <UTC-timestamp> --output human
```

JSON is canonical and versioned. An optional evidence export writes only the
same redacted JSON document to a new explicit path. A successful readiness
result is technical evidence only; it does not authorize or start staging.
