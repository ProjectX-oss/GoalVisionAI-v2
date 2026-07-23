# Registered Candidate-to-Publication Pipeline

`app/official_prediction_pipeline` is the final explicit manual integration
boundary for one immutable current `READY` Official candidate. It does not
discover candidates, fetch data, calculate probabilities/EV/stakes, mutate a
bankroll or exposure, settle results, schedule work, or execute at startup.

The complete deterministic path is:

```
match snapshot -> feature store -> model input -> raw inference
-> calibrated probabilities -> market value assessment
-> Official selection -> risk/stake/exposure assessment
-> immutable Candidate Registry version -> Publication Quality Gate
-> pre-approved Official orchestration -> existing message assembly
-> atomic publication claim -> injected Telegram delivery
-> immutable publication and pipeline histories
```

## Authority and stage order

The Candidate Registry remains authoritative for identity, exact version,
fingerprint, current lifecycle, and supersession/withdrawal/invalidation. The
Publication Quality Gate remains authoritative for detailed eligibility. The
orchestration package owns assembly and orchestration history. The publication
package owns stake-star presentation, Telegram-safe HTML, claim/send/finalize,
and delivery uncertainty.

Every fresh request follows request validation, candidate-state verification,
publication-state verification, Quality Gate, orchestration, message assembly,
publication claim, Telegram send, and publication finalization. Rejection or
review stops after the gate. Dry-run stops after message assembly.

The pipeline evaluates and persists the gate exactly once. It passes that exact
approved evaluation to `prepare_and_publish_preapproved(...)`; orchestration
validates its candidate, model, probability, odds, EV, timestamp, risk,
exposure, and policy identity without calling the gate again.

## Dry-run, retry, and recovery

Dry-run validates all immutable facts, reads Registry/publication state,
evaluates or idempotently reuses the gate, creates a dry orchestration record,
and builds the final payload with the existing message builder. It never
claims, sends, finalizes, or counts as published.

Retry is always explicit. A confirmed retryable publication failure proceeds
only with `retry=True`; an active claim returns `PUBLICATION_IN_PROGRESS`.
Published candidates return `IDEMPOTENT_EXISTING`. Unknown or indeterminate
delivery fails closed and never resends. Recovery checkpoints are the persisted
gate evaluation, orchestration record, atomic claim, Telegram result, and
terminal publication event. The package does not claim cross-module atomicity.

## Fingerprints, persistence, and manual use

Canonical SHA-256 identities cover the request, gate handoff, publication plan,
and final execution. They exclude duration, logs, credentials, object identity,
and uncontrolled time. Identical terminal requests replay before another gate,
orchestration, claim, or send. Changed content under an existing request
identity returns `CONFLICT`.

Migration v22 adds append-only
`official_prediction_pipeline_executions` and
`official_prediction_pipeline_stage_events`, foreign-keyed where downstream
records safely exist. Both reject updates/deletes and use compact sorted JSON.

Use `build_official_prediction_pipeline_service(...)` and explicitly call
`execute_official_prediction_pipeline(...)` or
`run_official_prediction_pipeline_once(...)`. The optional batch helper accepts
only a bounded supplied tuple. Construction does not execute, discover, read
Telegram credentials, start a bot, or schedule work.

Deferred work includes automatic discovery/scheduling, bankroll/exposure
retrieval, result settlement/publication, live betting, exception combos, Mega
Combo, High Risk, Lab, AutoTrader, and Telegram bot lifecycle.

## Operator execution layer

`app/official_prediction_operations` supplies the safe manual executable
boundary around this package. Signed fixtures materialize the real upstream
Match Snapshot through Candidate Registry history and then invoke this pipeline.
Dry-run installs a no-send transport and stops at the exact existing message
preview. Publication requires an injected verified destination, exact
candidate/match/destination confirmations, and exact environment tokens.
Diagnostics and recovery consume immutable execution/stage history without
weakening candidate, gate, claim, idempotency, or resend rules.

This does not wire the pipeline to startup, coordinator discovery, a scheduler,
provider fetches, or Telegram credential resolution.

Model activation remains outside this Official publication pipeline. Preparing
or executing a champion generation does not publish, schedule, select, stake,
or mutate bankroll, and the runtime resolver is intentionally not wired here.
