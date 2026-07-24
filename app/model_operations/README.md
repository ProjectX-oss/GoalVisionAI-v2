# Manual Model Operations

`app.model_operations` is the inert operator interface over
`app.model_activation`. It adds no activation rules and no migration. The CLI
requires an explicit existing database, supported environment, and
`OFFICIAL_GLOBAL` scope for every command.

```text
python -m app.model_operations.cli <command> \
  --database C:\fictional\goalvision.db \
  --environment lab \
  --scope OFFICIAL_GLOBAL
```

Commands:

- `bootstrap-champion`
- `prepare-activation`
- `execute-activation --confirm ACTIVATE_CHAMPION`
- `prepare-rollback`
- `execute-rollback --confirm ROLLBACK_CHAMPION`
- `show-champion`
- `show-activation`
- `list-generations`
- `diagnose-state`

Bootstrap requires every model, preprocessing, calibration, feature-schema,
target, probability-contract, and runtime-compatibility identifier and
fingerprint. Activation preparation additionally requires the exact current
generation, final promotion recommendation, challenger, and settled-shadow
evidence fingerprint. Rollback preparation requires an exact prior generation,
reason, and incident reference. Nothing is inferred.

Preparing a plan appends immutable review evidence but does not switch the
champion. Only a confirmed execution command can append a new champion
generation. Rollback also appends a new generation; it never edits, deletes, or
deactivates the current row without an atomic replacement.

Inspection commands open SQLite in read-only mode. `diagnose-state` verifies
migration v31+, generation chains and fingerprints, registry/execution
linkage, runtime artifact resolution, pending plans, and append-only triggers.
It reports `HEALTHY`, `WARNING`, `RECOVERY_REQUIRED`, or `INVALID_STATE` and
never repairs rows.

All output is deterministic, versioned, and secret-redacted. `--output json`
emits `goalvision-model-operations-output-v1`. Known failures return typed
non-zero outcomes without tracebacks. Ambiguous execution must be inspected;
it is never retried automatically.

The optional Lab formatter produces preview text only. Model operations never
instantiate a Telegram sender or contact Telegram. Runtime inference remains
disconnected from the champion resolver. There are no startup hooks,
schedulers, workers, automatic promotion, automatic rollback, bankroll,
settlement, prediction-publication, or Official Telegram changes.

See `docs/model_operations_runbook.md` for the full operator procedure.
