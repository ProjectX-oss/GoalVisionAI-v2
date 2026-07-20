# Official Prediction Run Coordinator

This package is the deterministic manual batch boundary above the existing
single-prediction orchestration service. It discovers immutable persisted
Official candidate references, classifies them against durable history, calls
`prepare_and_publish_official_prediction(...)` sequentially, and stores one
append-only logical run audit. It performs no generation, calibration, risk,
exposure, Quality Gate, message, claim, Telegram, settlement, or bankroll work.

## Persisted candidate source

The repository has no table containing enough data to reconstruct a complete
`OfficialCandidateAssemblyRequest`; v11 orchestration snapshots are audit-only.
The production factory therefore requires an injected
`PersistedOfficialPredictionCandidateSource`. That source must return complete
immutable request references from reviewed persistence. The coordinator never
fetches, invents, or refreshes candidate facts.

The concrete SQLite state reader combines those references with published
predictions, v12 publication events, prior coordinator items, and v11
orchestration outcomes. A changed source-owned immutable fingerprint permits a
new Quality Gate evaluation; an unchanged `REJECTED` or `REVIEW_REQUIRED`
fingerprint remains blocked. Manual force review is allowed only in dry-run and
never bypasses the Quality Gate.

## Discovery and ordering

Every reference is classified as ready, already published, active claim,
confirmed retryable failure, indeterminate, unchanged rejected, unchanged
review-required, expired, malformed, outside the lookahead window, or
non-Official. Only ready and explicitly confirmed retryable failures process by
default.

Ordering is always:

1. Earliest kickoff timestamp.
2. Earliest prediction creation timestamp.
3. Prediction ID.
4. Match ID as a final deterministic tie-break.

The policy applies a bounded batch limit after ordering. Duplicate prediction
references cannot produce a second attempt within one run.

## Retry and failure behavior

Only a v12 `FAILED` terminal publication event is retryable. The default policy
allows at most three prior attempts and requires a five-minute cooldown. Active
claims, published messages, indeterminate delivery, expired candidates,
malformed inputs, and non-Official scopes never retry. Prediction-level atomic
claims remain authoritative even when a new batch idempotency key is used.

Candidate dependency exceptions become `INTERNAL_FAILURE` without exposing the
private exception message; processing continues by default. An optional policy
can stop after the first failure. Discovery failure after a persisted start is
terminally `ABORTED`. Item or terminal persistence uncertainty returns
`INDETERMINATE` and leaves the persisted start incomplete, which blocks replay
of that run fingerprint.

No database transaction remains open during orchestration or Telegram work.

## Run model and idempotency

Run statuses are `COMPLETED`, `COMPLETED_WITH_FAILURES`, `DRY_RUN_COMPLETED`,
`NO_ELIGIBLE_CANDIDATES`, `ABORTED`, `FAILED_TO_START`, and `INDETERMINATE`.
Item statuses preserve every orchestration outcome and the explicit skip,
retry-limit, retry-cooldown, indeterminate, and internal-failure outcomes.

The SHA-256 run fingerprint contains the manual idempotency key, explicit UTC
evaluation timestamp, policy version, dry-run and force-review flags, Official
bankroll and destination scopes, lookahead and minimum-time windows, batch
limit, retry policy, and canonical sorted discovery filters. It excludes
credentials, logging fields, repository identity, and runtime memory state.

An identical terminal run fingerprint returns its existing immutable result
without rediscovery or sending. An incomplete matching run returns
`INDETERMINATE` and is not replayed automatically.

## Persistence

Migration v13 creates:

- `official_prediction_runs`: immutable start and terminal events for each
  logical run, with one unique start fingerprint and one terminal finalization.
- `official_prediction_run_items`: immutable ordered item outcomes linked to
  the run start event, prediction ID, candidate fingerprint, orchestration ID,
  and publication attempt when available.

Both tables reject update and delete operations. JSON snapshots use sorted keys
and compact deterministic separators. The terminal run counters are rebuilt and
validated from ordered item results.

## Manual boundary and future integration

`build_official_prediction_run_coordinator(...)` composes the injected
persisted source, SQLite state/audit repositories, existing orchestration
callable, and immutable policy. Construction only applies additive migration.

`run_official_prediction_batch(...)` requires an explicit timestamp and
idempotency key. It defaults to dry-run, accepts canonical discovery filters,
and never accesses the current time implicitly. Import and application startup
perform no discovery, claim, or send.

Reserved for future reviewed work: the persisted-candidate source adapter,
manual command wrapper or admin surface, scheduling, external ingestion,
operator recovery for incomplete or indeterminate runs, corrections, and all
non-Official products.
