# Controlled Official Prediction Operations

`app.official_prediction_operations` is the manual, bounded operator layer over
the existing Official prediction pipeline. It is dry-run-first and inert on
import. It does not schedule work, discover candidates, fetch live providers,
start bot polling, resolve Telegram credentials, or mutate a real bankroll or
exposure ledger.

## External fixture boundaries

The fixture executor persists and runs the real Match Snapshot, Feature Store,
Model Input, Inference, Calibration, Market Value, Official Selection, Risk,
Candidate Preparation/Registry, Quality Gate, Orchestration, Message, Atomic
Publisher, and Pipeline services. Only the external model artifact is replaced
by `FixturePredictionModelAdapter`. Telegram remains an injected transport; a
dry run installs `NoSendTelegramTransport`, which raises if invoked.

## Commands

Run `python -m app.official_prediction_operations.cli --help` for full syntax.

- `validate-fixture`: read-only schema, provenance, timestamp, scope, Decimal,
  fingerprint, market, URL, and secret validation. It runs no gate.
- `dry-run-fixture`: requires a signed fixture, explicit fixture database,
  explicit UTC times, request ID, `--environment fixture`, and
  `--create-database` for a new file. It stops after exact message preview.
- `publish-fixture`: requires staging/production, injected transport and
  destination verification, exact candidate/match/destination values, and
  `YES_PUBLISH_OFFICIAL`. Production also requires `PRODUCTION_OFFICIAL`.
- `inspect-execution` and `inspect-candidate`: read immutable evidence.
- `retry-execution`: permits only a confirmed-safe recovery classification,
  `--retry`, and `YES_RETRY_OFFICIAL`; application infrastructure must inject
  the verified destination and transport.
- `list-retry-required`: bounded to 1–100 results (default 20) and filtered
  through read-only recovery analysis so active, indeterminate, terminal, and
  already-recovered executions are never offered for retry.
- `smoke-startup`: creates an isolated in-memory schema and proves zero
  executions, gates, orchestrations, claims, and sends.

Every command has human output and `--json-output` using
`goalvision_official_operations_result_v1`. Output excludes credentials and
private transport configuration.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Successful validation, dry-run, publication, replay, inspection, or smoke check |
| 2 | Invalid arguments, unsafe database/environment, or confirmation failure |
| 3 | Fixture validation failure |
| 4 | Provenance or candidate-state rejection |
| 5 | Quality Gate rejection or review required |
| 6 | Publication in progress, retry required, or resend forbidden pending evidence |
| 7 | Orchestration or publication failure |
| 8 | Immutable identity conflict |
| 9 | Persistence failure |
| 10 | Unexpected internal failure |

## Database and destination safety

There is no default database. New files require `--create-database`, missing
parent directories are refused, aliases such as `prod` are refused, and publish
refuses `:memory:`. Fixture environment cannot publish. Destination
verification must be `VERIFIED`, enabled, type/environment/identity matched;
`UNKNOWN`, `INDETERMINATE`, `DISABLED`, or mismatched results fail closed.
Production also refuses fixtures explicitly marked `non_production`; the
checked-in fictional samples can therefore never publish to production.

Diagnostics are read-only and verify the latest migration v26, required tables,
append-only triggers, candidate provenance/lifecycle, gate/orchestration links,
claim and terminal state, ordered stages, duplicate fingerprints, request
identity conflicts, retry safety, and optional destination verification.

Recovery classifications are `TERMINAL_SUCCESS`, `TERMINAL_NO_PUBLICATION`,
`RETRYABLE_BEFORE_CLAIM`, `RETRYABLE_SEND_FAILURE`, `ACTIVE_CLAIM`,
`INDETERMINATE_POST_SEND`, `TERMINAL_FAILURE`, `CONFLICTED`, and
`INVALID_HISTORY`. Analysis never mutates state. See the
[operator runbook](../../docs/OFFICIAL_PREDICTION_OPERATIONS_RUNBOOK.md).
