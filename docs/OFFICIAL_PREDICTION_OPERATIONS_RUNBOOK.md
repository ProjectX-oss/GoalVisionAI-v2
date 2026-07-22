# Official Prediction Operations Runbook

## 1. Purpose and scope

This runbook covers controlled, one-fixture-at-a-time execution of the Official
single-bet pipeline. It does not authorize automation, live betting, combos,
provider ingestion, bankroll changes, or bot lifecycle operations.

## 2. Preconditions

Use an approved code revision, a signed `goalvision_official_fixture_v1` file,
an explicit UTC timeline, an explicit database path, and access appropriate to
the named environment. Confirm the Official product policy remains unchanged.

## 3. Environment preparation

Choose `fixture`, `staging`, or `production` explicitly. Fixture is dry-run
only. Staging must use an injected test destination. Production transport and
credentials are supplied through existing deployment controls, never fixture
files or command output. Use environment-specific placeholders where local
deployment commands are not documented.

## 4. Database backup

Before staging or production publication, use the existing approved database
backup procedure: `<environment-specific backup command>`. Record the backup
identity and verify it is restorable. Never overwrite the active database.

## 5. Migration verification

Run inspection/diagnostics against the explicit database. The expected latest
  migration is v25. Stop if tables, foreign keys, or append-only triggers are
missing. Fixture execution applies migrations only after database safety checks.

## 6. Fixture validation

Run:

```text
python -m app.official_prediction_operations.cli validate-fixture --fixture <fixture.json> --json-output
```

Exit 0 and status `VALID` are required. This command writes nothing and does
not execute the Quality Gate.

## 7. Dry-run procedure

Use a dedicated fixture database and fixed UTC times:

```text
python -m app.official_prediction_operations.cli dry-run-fixture --fixture <fixture.json> --database <fixture.db> --create-database --environment fixture --execution-time <UTC-Z> --quality-gate-time <UTC-Z> --publication-time <UTC-Z> --request-id <unique-id> --json-output
```

Require `DRY_RUN_COMPLETED`, gate `APPROVED`, zero publication events, and zero
Telegram sends. Reusing the exact request is idempotent.

## 8. Reviewing message preview

Record the message fingerprint. Inspect the candidate and execution, and review
the rendered preview through the approved internal review surface. Confirm the
teams, market, selection, odds, probability, confidence, stake display, and
public reasoning. A fingerprint change requires a new review.

## 9. Candidate and provenance verification

Use `inspect-candidate --candidate-id <id>` and
`inspect-execution --execution-id <id>`. Confirm READY lifecycle, exact version,
complete model/calibration/odds/value/selection/risk/bankroll/exposure
provenance, one gate linkage, and no conflicting publication state.

## 10. Staging publication

Use only an application-composed CLI with injected staging transport and an
enabled, verified staging destination. Supply the candidate, match, and
destination values copied from reviewed evidence. Never use fixture environment.

## 11. Production publication

Repeat validation and dry-run from the approved revision and backup evidence.
Use the verified production destination, exact identities, and both production
confirmations. A fixture marked `non_production` is refused. Observe one claim,
one send, and one terminal finalization.

## 12. Required confirmation tokens

- Publication: `YES_PUBLISH_OFFICIAL`
- Production environment: `PRODUCTION_OFFICIAL`
- Retry: `YES_RETRY_OFFICIAL`

Case, spelling, and underscores are exact. `yes`, `true`, `1`, or environment
variables alone are rejected.

## 13. Expected output and exit codes

Results use `goalvision_official_operations_result_v1`. Codes: 0 success; 2
argument/safety failure; 3 fixture invalid; 4 provenance/candidate rejected; 5
gate rejected/review; 6 active/retry/uncertain; 7 publication/orchestration
failure; 8 conflict; 9 persistence failure; 10 unexpected failure.

## 14. Idempotent replay procedure

Replay only the exact same request and immutable inputs. A successful replay
must return the persisted terminal outcome and create zero additional sends.
Never change a timestamp while reusing a request identity.

## 15. Retry procedure

Run diagnostics and recovery analysis first. Only
`RETRYABLE_BEFORE_CLAIM` or `RETRYABLE_SEND_FAILURE` may retry. Use
`retry-execution --retry --confirm-retry YES_RETRY_OFFICIAL` with explicit new
execution/publication times and application-injected destination/transport.
The approved persisted gate is reused; candidate, selection, and risk are not
recreated.

## 16. Active claim handling

For `ACTIVE_CLAIM`, stop. Do not send, delete, expire, or replace the claim.
Inspect external delivery evidence and immutable publication history. Escalate
using the existing incident process.

## 17. Post-send finalization uncertainty

`INDETERMINATE_POST_SEND` means delivery may have happened. Resend is forbidden.
Reconcile Telegram evidence, message identity, and audit records. Never convert
uncertainty to confirmed failure without evidence.

## 18. Quality Gate rejection handling

Exit 5 with `NO_PUBLICATION_QUALITY_GATE_REJECTED` is a valid no-publication
result, not permission to bypass the gate. Preserve reasons and correct the
upstream data through its normal immutable versioning workflow.

## 19. Review-required handling

Exit 5 with `NO_PUBLICATION_REVIEW_REQUIRED` sends nothing. Record the review
facts. Do not edit the persisted decision or force publication through this CLI.

## 20. Rollback limitations

Claims, gate evaluations, orchestration records, messages, pipeline stages, and
candidate histories are append-only evidence. A sent Telegram message and
immutable history cannot be rolled back by deleting rows. Use the existing
correction/communication process when required.

## 21. Audit and evidence collection

Retain fixture fingerprint, code revision, database backup identity, environment,
request/execution/candidate IDs, gate/orchestration/publication IDs, destination
verification, message fingerprint, timestamps, result JSON, diagnostics, and
external delivery evidence. Never capture credentials.

## 22. Startup safety verification

Run `smoke-startup --json-output`. All five counts must be zero. Application
startup/import must not discover candidates, execute gates, create claims, send
Telegram messages, or run fixture commands.

## 23. Known deferred features

Automatic discovery, scheduling, startup execution, real odds/model/bankroll/
exposure ingestion, live betting, combos, High Risk, Lab, AutoTrader, bot
polling, and deployment-specific credential/bootstrap commands remain deferred.

## 24. Troubleshooting matrix

| Symptom | Required action |
|---|---|
| Fixture validation fails | Correct the source fixture and regenerate its canonical fingerprint; do not weaken validation |
| Database path refused | Use an explicit file, existing parent, and `--create-database` only for a new dedicated file |
| Candidate mismatch | Stop and inspect the exact READY version; never substitute an inferred ID |
| Gate rejected/review | Preserve reasons; follow sections 18 or 19 |
| Destination unknown/disabled/mismatch | Stop; correct application-owned destination configuration |
| Active claim | Follow section 16; zero resend |
| Confirmed send failure | Analyze recovery, then use the exact retry flow |
| Indeterminate send/finalization | Follow section 17; zero resend |
| Persistence/linkage/trigger failure | Preserve database and backup, stop publication, escalate |

## 25. Emergency stop procedure

Disable the external Telegram transport/configuration through existing
deployment controls using `<environment-specific control>`. Stop all manual
publish commands. Preserve the database state and current backup; do not delete
claims, gate evaluations, orchestration records, publication events, or pipeline
history. Run read-only diagnostics and collect evidence.
Never manually mark an uncertain send as failed without external evidence. Keep scheduling and
automatic discovery disabled.
