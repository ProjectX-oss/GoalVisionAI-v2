# GoalVision AI Manual Model Operations Runbook

## 1. Purpose and safety boundary

This runbook controls the append-only champion registry through the existing
model-activation domain. Promotion is evidence, Shadow is evidence, and plan
preparation is review. Only an explicit confirmed execution appends a new
champion generation.

The CLI never schedules work, starts a worker, changes runtime inference,
publishes Telegram messages, places bets, or changes bankroll, settlement,
prediction, or Official publication state.

## 2. Required environment

Use a reviewed project checkout and its pinned Python environment. Supply an
explicit existing SQLite database path, one of `lab`, `staging`, or
`production`, and the supported scope `OFFICIAL_GLOBAL`. Do not use aliases,
`:memory:`, missing databases, or inferred artifact identifiers.

All examples below are fictional:

```powershell
$python = ".venv\Scripts\python.exe"
$database = "C:\goalvision\fictional-operations.db"
$scope = "OFFICIAL_GLOBAL"
$environment = "lab"
```

Never place secrets or `.env` contents on the command line.

## 3. Database backup guidance

Before any state-changing command, stop other writers using the reviewed
operational procedure and take a consistent SQLite backup. Keep the original
database and backup immutable until post-operation validation is complete.
Never copy only the main database file while a WAL writer is active.

Do not restore or edit individual activation tables. Recovery uses a complete
database restore only under a separately reviewed incident procedure.

## 4. Read-only preflight

Run all four read-only views:

```powershell
& $python -m app.model_operations.cli diagnose-state --database $database --environment $environment --scope $scope
& $python -m app.model_operations.cli show-champion --database $database --environment $environment --scope $scope
& $python -m app.model_operations.cli list-generations --database $database --environment $environment --scope $scope --limit 20
```

Proceed only from `HEALTHY`, or after a documented review of an expected
pending-plan warning. `RECOVERY_REQUIRED` and `INVALID_STATE` block execution.

## 5. Initial champion bootstrap

Bootstrap is allowed once per scope. Copy every exact reference from reviewed
immutable artifact inspection:

```powershell
& $python -m app.model_operations.cli bootstrap-champion `
  --database $database --environment $environment --scope $scope `
  --model-artifact-id model-artifact-fictional-a `
  --model-artifact-fingerprint aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa `
  --preprocessing-fingerprint bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb `
  --calibration-artifact-set-id calibration-set-fictional-a `
  --calibration-artifact-set-fingerprint cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc `
  --feature-schema-version historical_training_features_v1 `
  --feature-schema-fingerprint dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd `
  --target-contract-version official_prediction_targets_v1 `
  --probability-contract-version canonical-11-target-contract-v1 `
  --runtime-compatibility-version probability-calibration-v1 `
  --timestamp 2026-08-01T10:00:00Z `
  --reason "Reviewed initial registry bootstrap" `
  --operator operator-fictional
```

Duplicate or conflicting bootstrap is rejected and never replaces a champion.

## 6. Review promotion evidence

Before activation, inspect the immutable comparison run and confirm:

- final recommendation is exactly `PROMOTE_CHALLENGER`;
- every mandatory gate passed;
- champion and challenger artifact identities match;
- settled Shadow evidence is for the exact model pair;
- the evidence cutoff and fingerprint are recorded;
- the runtime artifact and calibration chains verify.

Promotion alone never activates a model.

## 7. Prepare activation

Provide the exact current generation, both complete runtime references, final
recommendation, explicit Shadow evidence fingerprint, operator, and reason:

```powershell
& $python -m app.model_operations.cli prepare-activation `
  --database $database --environment $environment --scope $scope `
  --request-id activation-request-fictional-001 `
  --name "Fictional challenger review" `
  --current-generation-id champion-generation-fictional-001 `
  --current-generation-fingerprint 1111111111111111111111111111111111111111111111111111111111111111 `
  --current-model-artifact-id model-artifact-fictional-a `
  --current-model-artifact-fingerprint aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa `
  --current-preprocessing-fingerprint bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb `
  --current-calibration-artifact-set-id calibration-set-fictional-a `
  --current-calibration-artifact-set-fingerprint cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc `
  --current-feature-schema-version historical_training_features_v1 `
  --current-feature-schema-fingerprint dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd `
  --current-target-contract-version official_prediction_targets_v1 `
  --current-probability-contract-version canonical-11-target-contract-v1 `
  --current-runtime-compatibility-version probability-calibration-v1 `
  --challenger-model-artifact-id model-artifact-fictional-b `
  --challenger-model-artifact-fingerprint eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee `
  --challenger-preprocessing-fingerprint ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff `
  --challenger-calibration-artifact-set-id calibration-set-fictional-b `
  --challenger-calibration-artifact-set-fingerprint 2222222222222222222222222222222222222222222222222222222222222222 `
  --challenger-feature-schema-version historical_training_features_v1 `
  --challenger-feature-schema-fingerprint dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd `
  --challenger-target-contract-version official_prediction_targets_v1 `
  --challenger-probability-contract-version canonical-11-target-contract-v1 `
  --challenger-runtime-compatibility-version probability-calibration-v1 `
  --comparison-run-id comparison-fictional-001 `
  --comparison-run-fingerprint 3333333333333333333333333333333333333333333333333333333333333333 `
  --challenger-candidate-id challenger-fictional-001 `
  --recommendation-id recommendation-fictional-001 `
  --recommendation-fingerprint 4444444444444444444444444444444444444444444444444444444444444444 `
  --shadow-evidence-fingerprint 5555555555555555555555555555555555555555555555555555555555555555 `
  --evidence-cutoff 2026-08-15T10:00:00Z `
  --requested-at 2026-08-15T10:05:00Z `
  --reason "Reviewed comparison and settled Shadow evidence" `
  --operator operator-fictional
```

## 8. Review activation plan

Record the returned plan ID and deterministic fingerprint. Review it read-only:

```powershell
& $python -m app.model_operations.cli show-activation --database $database --environment $environment --scope $scope --plan-id activation-plan-fictional-001 --output json
```

Verify request, policy, validations, exact evidence links, current generation,
challenger, and fingerprints. The output must say production state is
unchanged.

## 9. Execute activation

Execute only the exact reviewed plan. Generic `--yes` is unsupported:

```powershell
& $python -m app.model_operations.cli execute-activation `
  --database $database --environment $environment --scope $scope `
  --execution-request-id activation-execution-fictional-001 `
  --plan-id activation-plan-fictional-001 `
  --plan-fingerprint 6666666666666666666666666666666666666666666666666666666666666666 `
  --executed-at 2026-08-15T10:10:00Z `
  --operator operator-fictional `
  --confirm ACTIVATE_CHAMPION
```

The domain revalidates champion, promotion, artifacts, calibration, and Shadow
evidence before one atomic generation append.

## 10. Post-activation validation

Immediately run `show-champion`, `show-activation`, `list-generations`, and
`diagnose-state`. Verify the previous generation, new generation, execution
fingerprint, registry event, artifact identities, and `HEALTHY` status.

Runtime inference is not wired to this resolver; registry success does not
claim that live inference changed.

## 11. Prepare rollback

Select an exact compatible historical generation and provide both reason and
incident reference:

```powershell
& $python -m app.model_operations.cli prepare-rollback `
  --database $database --environment $environment --scope $scope `
  --request-id rollback-request-fictional-001 `
  --name "Fictional incident rollback" `
  --current-generation-id champion-generation-fictional-002 `
  --current-generation-fingerprint 7777777777777777777777777777777777777777777777777777777777777777 `
  --target-generation-id champion-generation-fictional-001 `
  --reason "Observed reviewed runtime degradation" `
  --incident-reference INC-FICTIONAL-001 `
  --operator operator-fictional `
  --requested-at 2026-08-15T11:00:00Z
```

Preparation validates the target but does not change the champion.

## 12. Execute rollback

After independent plan review:

```powershell
& $python -m app.model_operations.cli execute-rollback `
  --database $database --environment $environment --scope $scope `
  --execution-request-id rollback-execution-fictional-001 `
  --plan-id rollback-plan-fictional-001 `
  --plan-fingerprint 8888888888888888888888888888888888888888888888888888888888888888 `
  --executed-at 2026-08-15T11:05:00Z `
  --operator operator-fictional `
  --confirm ROLLBACK_CHAMPION
```

Rollback atomically appends a new generation using the historical artifact. It
does not rewrite history or reactivate an old row in place.

## 13. Post-rollback validation

Repeat all read-only views. The newest generation must point to the replaced
champion as its previous generation and to the rollback plan. Its artifact may
match an older generation, but its generation ID and fingerprint must be new.

## 14. Stale-plan recovery

If the current champion, artifact chain, recommendation, or Shadow evidence
changed after preparation, execution returns a stale-plan outcome. Do not edit
or reuse the plan. Inspect the old plan, diagnose state, then create a new
request ID and prepare a new plan from current immutable evidence.

## 15. Ambiguous execution recovery

After a connection loss or unknown client result, never execute again
automatically. Run `show-activation`, `show-champion`, `list-generations`, and
`diagnose-state`.

- If an execution fingerprint and resulting generation exist, treat the
  operation as executed.
- If no execution or generation exists and state is healthy, use the existing
  exact idempotent request only after operator review.
- If evidence is incomplete or contradictory, stop with `RECOVERY_REQUIRED`.

## 16. Idempotent replay

Exact domain execution requests are idempotent. The CLI reports an
already-executed typed outcome instead of silently retrying. Changed content
under a reused request ID is a conflict.

## 17. Audit inspection

`show-activation` displays request, plan, validations, evidence links,
execution, registry events, resulting generation, and fingerprints.
`--output json` is deterministic and versioned for review tooling.

## 18. Champion generation interpretation

The highest valid generation number is current for the scope. Generation 1 is
bootstrap. Approved activation and manual rollback each append exactly one new
generation. `previous_champion_generation_id` forms the immutable chain.

## 19. Artifact and fingerprint verification

Never transcribe shortened fingerprints. Verify the full model artifact,
preprocessing, calibration set, feature schema, target contract, probability
contract, and runtime compatibility references. Missing or mismatched evidence
blocks bootstrap, activation, rollback, or runtime resolution.

## 20. Intentionally unavailable commands

There is no generic `--yes`, automatic promote, automatic activate, automatic
rollback, delete generation, update plan, repair row, force current champion,
schedule, worker, Telegram-send, publish prediction, settle bet, or change
bankroll command.

## 21. Scheduling and automatic activation

Scheduling, startup execution, background workers, metric-triggered switching,
automatic promotion, and automatic rollback remain deferred.

## 22. Runtime inference integration

The resolver remains read-only and disconnected from production inference.
Model operations manage an auditable registry only; wiring inference requires a
separate reviewed change.

## 23. Telegram and Official publication

Model operations never call Telegram. Official publication, statistics,
prediction selection, settlement, and bankroll behavior are unaffected.

## 24. Lab-only test-publication policy

Future technical test publications may target only:

- bot `@GoalVision_AI_Lab_Bot`;
- channel `-1003510920417`.

The separate Lab sender remains manual-only and disabled for automatic use.
Model operations produce only a preview formatter and never send it.

## 25. Emergency operator checklist

1. Stop and record the incident reference.
2. Do not retry an ambiguous execution.
3. Preserve the database and logs.
4. Run all read-only inspection commands.
5. Confirm migration v31+, append-only guards, and exact champion chain.
6. Verify artifacts and full fingerprints.
7. Determine whether an execution and generation committed.
8. Escalate `RECOVERY_REQUIRED` or `INVALID_STATE`.
9. Never edit append-only rows manually.
10. Prepare a new reviewed rollback only from a healthy current state.

## Controlled staging rehearsal

The staging rehearsal is a separate manual proof procedure. It is not a
production change procedure and grants no authority to activate or roll back a
production model. Run it only with an explicitly reviewed source database,
destination below `var/staging_rehearsal`, full source commit, fixed UTC
timestamp, `STAGING`, and `OFFICIAL_GLOBAL`.

```powershell
& $python -m app.staging_model_operations_rehearsal.cli run `
  --source-database data\goalvision.db `
  --destination-directory var\staging_rehearsal\20260725T120000Z `
  --environment STAGING `
  --scope OFFICIAL_GLOBAL `
  --timestamp 20260725T120000Z `
  --source-commit 78f218632fafe4ceeab708b5dd92dbd1e48a890f `
  --artifact-mode prefer-real `
  --allow-fixture-fallback `
  --audit-output-mode both `
  --evidence-report-destination docs\rehearsals\staging_model_operations_rehearsal.json `
  --output json
```

Omit `--allow-fixture-fallback` unless the authorization explicitly permits
fictional evidence. `real-only` fails closed when the supplied source does not
contain one complete eligible chain. Fixture evidence is always labeled
`FICTIONAL_STAGING_REHEARSAL_ONLY` and cannot be mistaken for production
evidence.

The source is opened read-only for inventory and integrity checks. All schema
advancement, bootstrap, preparation, activation, rollback, injected failure,
and replay work occurs on new copies. Before accepting the report, verify:

- source SHA-256 before and after equals the backup SHA-256;
- both staging preflights and the final independent audit passed;
- no `WARNING` or `BLOCKER` remains in the final audit;
- bootstrap, activation preparation/execution, rollback preparation/execution,
  exact replay, changed-request conflict, and wrong-confirmation outcomes are
  typed as expected;
- the resolver sequence equals the three-generation append-only chain;
- injected activation and rollback failures leave no partial state and exact
  retry succeeds;
- foreign-key violations are zero, protected upstream rows are unchanged, and
  append-only guards remain present;
- the output contains no secrets or machine-specific absolute paths.

Never rerun into an existing destination or evidence path. Preserve the
database copies and JSON report under the reviewed retention policy. A passed
staging rehearsal proves technical behavior only; runtime inference remains
unwired and production still requires a separate human-authorized change.

## Independently reviewed 25-step operator flow

This sequence is normative. A second person reviews the evidence and exact
command before every state-changing step.

1. **Preflight environment validation:** name the environment, explicit
   database file, and `OFFICIAL_GLOBAL` scope; reject aliases and ambiguity.
2. **Database backup:** stop writers under the operational procedure, take a
   consistent backup, hash it, and prove it opens before a state change.
3. **Read-only diagnostic:** retain `diagnose-state`, `show-champion`, and
   `list-generations` outputs and exit codes.
4. **Bootstrap eligibility:** bootstrap only an empty, healthy scope with
   separately recorded authorization; never use it to recover corrupt state.
5. **Evidence review:** independently verify promotion, exact artifact pair,
   settled shadow evidence, fingerprints, and policy thresholds.
6. **Activation preparation:** `prepare-activation` is **STATE-CHANGING (PLAN
   PERSISTENCE ONLY)**; it does not activate a model.
7. **Independent plan review:** compare the persisted plan ID, fingerprint,
   expected generation, registry fingerprint, validations, and evidence links.
8. **Activation execution confirmation:** `execute-activation` is
   **STATE-CHANGING** and requires exactly `--confirm ACTIVATE_CHAMPION`;
   generic confirmation and `--yes` are forbidden.
9. **Immediate post-activation checks:** verify one appended generation, event
   sequence, exact resolver output, and execution fingerprint read-only.
10. **Observation period:** retain evidence and monitor only through the
    separately authorized process; do not automate rollback.
11. **Rollback preparation:** `prepare-rollback` is **STATE-CHANGING (PLAN
    PERSISTENCE ONLY)** and requires an incident, reason, current generation,
    and historical target.
12. **Rollback execution:** `execute-rollback` is **STATE-CHANGING** and
    requires exactly `--confirm ROLLBACK_CHAMPION`.
13. **Ambiguous failure handling:** stop writes, retain output, and inspect the
    plan, execution, and registry read-only. Do not edit registry rows.
14. **Idempotent replay:** replay only the identical request ID, plan ID,
    fingerprint, timestamp, operator, and confirmation after review.
15. **Registry audit:** verify contiguous generations, previous links,
    creation/retirement events, execution links, and the unique highest row.
16. **Artifact verification:** verify model, preprocessing, estimator,
    calibration, feature schema, probability contract, provenance, and runtime
    compatibility fingerprints.
17. **Append-only verification:** verify all v31 update/delete triggers and
    uniqueness constraints; never disable triggers or update/delete rows.
18. **Resolver verification:** confirm the exact highest generation and
    artifact chain; missing, duplicate, or corrupt evidence must fail closed.
19. **Lab-only testing rules:** publication is a separate manual boundary;
    model operations never call Telegram or treat publication as evidence.
20. **Staging authorization boundary:** technical readiness is not authority.
    Explicit human staging authorization is still required; the controlled
    rehearsal above must use disposable copies and never grants production
    authority.
21. **Production authorization boundary:** require a separate recorded human
    authorization and production change procedure.
22. **Commands forbidden in automation:** bootstrap, both preparations, and
    both executions are forbidden in startup, schedulers, workers, unattended
    scripts, and retry loops.
23. **Emergency stop checklist:** stop state-changing commands, preserve the
    database and backup, capture diagnostics, record the incident, and escalate.
24. **Incident record requirements:** retain environment, scope, database
    identifier (not credentials), timestamps, identities, IDs, fingerprints,
    exit codes, reason codes, decisions, and hashes.
25. **Evidence retention requirements:** retain immutable backup hashes, audit
    JSON/fingerprint, CLI outputs, plans, registry/artifact diagnostics,
    rehearsal reports, authorizations, and incident records under the
    controlled retention policy. Never retain secrets in audit output.

Runtime inference remains unwired. This flow never implies automatic
activation, rollback, publication, or fallback.

## Second-person reviewer checklist

- You verify environment, database, scope, backup hash, and read-only
  diagnostics before reviewing a write.
- You verify plan and evidence fingerprints against retained sources.
- You identify every state-changing command and its exact confirmation.
- You reject stale plans and never repair state by direct database edits.
- You handle ambiguous execution through inspection and exact idempotent replay.
- You verify append-only controls, registry, artifacts, and resolver afterward.
- You keep Lab, staging, and production authorizations separate.
- You confirm state-changing commands are forbidden in automation.
- You retain required evidence without secrets.
- You stop on any ambiguous identity, database, fingerprint, or authorization.
