# Controlled Lab Activation Execution and Rollback Rehearsal

Date: 2026-07-25

Source commit: `9b7264fa49d2387f94a71b68548413fdb2062ad4`

Final commit: the commit containing this report; its exact hash is recorded in
the completion response.

Marker: `FICTIONAL_LAB_EXECUTION_REHEARSAL_ONLY`

## Purpose and verdict

This rehearsal proves the existing manual activation and rollback execution
boundaries on one fully isolated disposable SQLite database. The real
`app.model_operations.cli` ran in fresh subprocesses with its exact
confirmation phrases. No domain table was edited by the rehearsal helper.

The rehearsal passed:

- activation executed atomically exactly once;
- exact activation replay was typed as already executed;
- activation conflict and wrong-confirmation attempts were rejected;
- rollback preparation was deterministic and did not change the champion;
- rollback executed atomically exactly once;
- exact rollback replay was typed as already executed;
- rollback conflict and wrong-confirmation attempts were rejected;
- the resolver sequence was original, challenger, then a new rollback
  generation using the original artifact chain;
- all non-model-operations table fingerprints stayed unchanged;
- the original source and prepared foundation stayed byte-for-byte unchanged;
- no Telegram call or message occurred.

## Safety boundary and disposable database

Redacted runtime locations:

- source: `<MAIN_CHECKOUT>/data/goalvision.db`
- ignored runtime directory: `<LAB_REHEARSAL_DIR>`
- prepared foundation:
  `<LAB_REHEARSAL_DIR>/goalvision_lab_rehearsal_20260725T003000Z.db`
- disposable execution database:
  `<LAB_REHEARSAL_DIR>/goalvision_activation_rollback_20260725T003000Z.db`
- redacted machine-readable result:
  `<LAB_REHEARSAL_DIR>/goalvision_activation_rollback_20260725T003000Z.result.json`

The helper first created a timestamped byte-identical backup of the source,
seeded the deterministic fictional evidence chain, bootstrapped the original
champion through the real CLI, and prepared the known activation plan through
the real CLI. It then fingerprinted the prepared foundation and copied it to a
new disposable database. Only the disposable database was used for activation
and rollback execution.

SHA-256 evidence:

| Object | SHA-256 |
| --- | --- |
| Original source before and after | `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0` |
| Timestamped source backup | `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0` |
| Prepared foundation | `55bba08de468f0ddb886db0459f1ad6d501fce01226e6e0309e5272da0ff6ac8` |
| Disposable before execution | `55bba08de468f0ddb886db0459f1ad6d501fce01226e6e0309e5272da0ff6ac8` |
| Disposable after rollback | `8423d16d067ae62b3a6c822c177534d14ad926afbfc60c637cca4a870c95f93e` |

Starting-state checks:

- schema version: 31;
- foreign keys enabled: yes;
- foreign-key violations: 0;
- append-only/integrity triggers: 184;
- original champion generations: 1;
- pending activation plans: 1;
- activation validations: 9 `PASS`;
- activation evidence links: 30;
- activation executions: 0;
- rollback requests, plans, and executions: 0.

Any mismatch fails closed and removes the disposable output.

## Pre-execution state

Original champion generation:

`champion-generation-71e13a42f2c88473193a24e560b263cd50ab8ffc5f2471bc00031e4cbcf9657f`

Activation plan ID and fingerprint:

`activation-plan-08d026d15b5d343030560befb25b1504c70939bc17dbb1fc4f560da62fa086b7`

The plan was pending, all nine policy validations passed, and the resolver
returned the original champion. Both human and JSON inspection paths were
captured for diagnostics, champion display, activation display, and generation
listing.

Initial diagnostic status was the expected `WARNING` with exit 5 because a
reviewed activation plan was intentionally pending. All other pre-execution
inspection commands exited 0.

## Activation execution

Primary command:

```text
python -m app.model_operations.cli execute-activation --database <DISPOSABLE_DB> --environment lab --scope OFFICIAL_GLOBAL --output json --execution-request-id fictional-lab-execution-rehearsal-activation-1 --plan-id activation-plan-08d026d15b5d343030560befb25b1504c70939bc17dbb1fc4f560da62fa086b7 --plan-fingerprint 08d026d15b5d343030560befb25b1504c70939bc17dbb1fc4f560da62fa086b7 --executed-at 2026-08-01T14:00:00Z --operator FICTIONAL_LAB_EXECUTION_REHEARSAL_ONLY --confirm ACTIVATE_CHAMPION
```

Outcome:

- typed status: `ACTIVATION_EXECUTED`;
- exit code: 0;
- execution fingerprint:
  `b892eca23634b2fd9a12ef72d893011b86a2385e44139d56e06afe2eac745c23`;
- replaced generation: original champion above;
- activated challenger generation:
  `champion-generation-bccc6854dda7b44ceb6a4f7a5707e55e7c8793413ee404895c9e8aa9d16f0727`.

The transaction appended the challenger generation, the retirement and
activation registry events, and one execution record. The original generation
remained immutable. Exactly one latest champion existed and the resolver
returned the challenger.

Activation negative checks:

| Check | Typed status | Exit | Mutation |
| --- | --- | ---: | --- |
| Exact replay | `ACTIVATION_ALREADY_EXECUTED` | 6 | None |
| Same request/plan with zero fingerprint | `ACTIVATION_CONFLICT` | 6 | None |
| Confirmation `WRONG` | `CONFIRMATION_REJECTED` | 2 | None |

No traceback was emitted for any known failure. Post-activation diagnostics
were `HEALTHY`, exit 0. Generation count was exactly two and activation
execution count was exactly one.

## Rollback preparation

Primary command:

```text
python -m app.model_operations.cli prepare-rollback --database <DISPOSABLE_DB> --environment lab --scope OFFICIAL_GLOBAL --output json --request-id fictional-lab-execution-rehearsal-rollback-1 --name "FICTIONAL_LAB_EXECUTION_REHEARSAL_ONLY rollback preparation" --current-generation-id champion-generation-bccc6854dda7b44ceb6a4f7a5707e55e7c8793413ee404895c9e8aa9d16f0727 --current-generation-fingerprint bccc6854dda7b44ceb6a4f7a5707e55e7c8793413ee404895c9e8aa9d16f0727 --target-generation-id champion-generation-71e13a42f2c88473193a24e560b263cd50ab8ffc5f2471bc00031e4cbcf9657f --reason "FICTIONAL_LAB_EXECUTION_REHEARSAL_ONLY controlled rollback" --incident-reference FICTIONAL-LAB-INCIDENT-001 --operator FICTIONAL_LAB_EXECUTION_REHEARSAL_ONLY --requested-at 2026-08-01T15:00:00Z
```

Outcome:

- typed status: `ROLLBACK_PLAN_PREPARED`;
- exit code: 0;
- rollback plan ID and fingerprint:
  `rollback-plan-2fd77f078662b5898a1ea810f7079bb5f72d2e5b4cfa5d66a99113fea9dfedea`;
- active champion after preparation: unchanged challenger generation.

Exact replay returned the same rollback plan and exit 0. Changing the immutable
reason under the same request ID returned `ROLLBACK_CONFLICT`, exit 6, with no
state mutation.

## Rollback execution

Primary command:

```text
python -m app.model_operations.cli execute-rollback --database <DISPOSABLE_DB> --environment lab --scope OFFICIAL_GLOBAL --output json --execution-request-id fictional-lab-execution-rehearsal-rollback-execution-1 --plan-id rollback-plan-2fd77f078662b5898a1ea810f7079bb5f72d2e5b4cfa5d66a99113fea9dfedea --plan-fingerprint 2fd77f078662b5898a1ea810f7079bb5f72d2e5b4cfa5d66a99113fea9dfedea --executed-at 2026-08-01T16:00:00Z --operator FICTIONAL_LAB_EXECUTION_REHEARSAL_ONLY --confirm ROLLBACK_CHAMPION
```

Outcome:

- typed status: `ROLLBACK_EXECUTED`;
- exit code: 0;
- execution fingerprint:
  `1330e58953ac80166f43f2546937731b3745573c0360ad9279ed82ab2426eb33`;
- replaced generation: activated challenger;
- new rollback generation:
  `champion-generation-94f1b63c3713216140d9bc753d1002158901cd8ffaad05222d0c0fecef127cce`.

The rollback created a new immutable generation using the original model,
preprocessing, calibration, feature schema, target/probability contracts, and
runtime compatibility references. It did not reactivate or modify generation
1. Its predecessor points to the challenger.

Rollback negative checks:

| Check | Typed status | Exit | Mutation |
| --- | --- | ---: | --- |
| Exact replay | `ROLLBACK_ALREADY_EXECUTED` | 6 | None |
| Same request/plan with zero fingerprint | `ROLLBACK_CONFLICT` | 6 | None |
| Confirmation `WRONG` | `CONFIRMATION_REJECTED` | 2 | None |

Final diagnostics were `HEALTHY`, exit 0.

## Resolver sequence and final generation chain

1. Before activation:
   `champion-generation-71e13a42f2c88473193a24e560b263cd50ab8ffc5f2471bc00031e4cbcf9657f`
2. After activation:
   `champion-generation-bccc6854dda7b44ceb6a4f7a5707e55e7c8793413ee404895c9e8aa9d16f0727`
3. After rollback:
   `champion-generation-94f1b63c3713216140d9bc753d1002158901cd8ffaad05222d0c0fecef127cce`

The final generation uses the complete original generation-1 artifact chain.
The registry event order is:

1. `INITIAL_REGISTERED`
2. `RETIRED_BY_ACTIVATION`
3. `CHAMPION_ACTIVATED`
4. `RETIRED_BY_ROLLBACK`
5. `CHAMPION_ROLLED_BACK`

## Final row counts

| Record family | Count |
| --- | ---: |
| Champion generations | 3 |
| Activation requests | 1 |
| Activation plans | 1 |
| Activation executions | 1 |
| Rollback requests | 1 |
| Rollback plans | 1 |
| Rollback executions | 1 |
| Registry events | 5 |
| Activation evidence links | 30 |
| Pending activation plans | 0 |
| Pending rollback plans | 0 |
| Foreign-key violations | 0 |

Exactly one latest champion resolves, and no duplicate execution or event chain
exists.

## Atomic failure verification

Integration tests used real file-backed SQLite transactions and temporary
failure triggers. Production behavior and application code were not patched.

Activation failure was injected immediately before insertion of the activation
execution row, after the generation and registry-event inserts had been
attempted. The complete transaction rolled back:

- original champion remained current;
- generation count remained one;
- execution count remained zero;
- registry event count remained one;
- after removal of the test-only failure trigger, the same CLI retry succeeded.

Rollback failure was injected immediately before insertion of the rollback
execution row, after the rollback generation and events had been attempted. The
complete transaction rolled back:

- challenger remained current;
- generation count remained two;
- rollback execution count remained zero;
- registry event count remained three;
- after removal of the test-only failure trigger, the same CLI retry succeeded.

Append-only tests also proved that direct updates to generation history and
deletes from rollback execution history are rejected by SQLite triggers.

## Verification results

- execution-rehearsal integration tests: 11 passed in 35.504 seconds;
- focused activation, rollback, model, evidence, Lab Telegram, and Official
  regression matrix: 264 passed in 75.719 seconds;
- complete repository suite: 1,061 passed in 104.847 seconds, exit 0;
- compilation: `python -m compileall -q app tests`, exit 0;
- complete import smoke: 538 application modules imported, zero failures;
- model-operations CLI help: exit 0;
- rehearsal CLI and execution-command help: exit 0;
- controlled startup: `HEALTHY`, exit 0, with zero gate executions,
  orchestrations, pipeline executions, publication claims, and Telegram sends;
- fresh and upgrade-to-v31 migrations, append-only enforcement, atomic
  failures, historical training/calibration/backtesting, comparison, shadow,
  Lab Telegram, and Official pipeline regressions are included in the focused
  and complete passing suites.

## Command and exit-code inventory

| Phase | Command | Exit |
| --- | --- | ---: |
| Pre | `diagnose-state` human / JSON | 5 / 5 |
| Pre | `show-champion` human / JSON | 0 / 0 |
| Pre | `show-activation` human / JSON | 0 / 0 |
| Pre | `list-generations` human / JSON | 0 / 0 |
| Activation | execute / replay / conflict / wrong confirm | 0 / 6 / 6 / 2 |
| Post-activation | show/list/diagnose human and JSON | all 0 |
| Rollback preparation | first / replay / conflict | 0 / 0 / 6 |
| Rollback | execute / replay / conflict / wrong confirm | 0 / 6 / 6 / 2 |
| Final | show/list/diagnose human and JSON | all 0 |
| Final | show rollback audit | 0 |

The top-level manual invocation was:

```text
python -m app.model_operations_rehearsal.cli execute-activation-rollback-rehearsal --source-database <MAIN_CHECKOUT>/data/goalvision.db --destination-directory <LAB_REHEARSAL_DIR> --timestamp 20260725T003000Z
```

## Protected-state and Telegram proof

Before activation, the helper fingerprinted every table outside the activation,
rollback, and champion-registry boundary. Every protected table fingerprint was
identical after rollback. This includes Official prediction, publication,
bankroll, statistics, ordinary settlements, shadow evidence, training,
calibration, comparison, and Telegram-related persistence.

The rehearsal package does not import a Telegram transport or sender. No
Telegram endpoint appeared in output, no Telegram record changed, and no
message was sent. The default no-Telegram behavior was retained.

There was no runtime-resolver wiring, inference change, scheduler, worker,
startup hook, automatic activation, automatic rollback, publication, or
production deployment.

## Known limitations and next step

All artifacts and evidence are deterministic fictional Lab fixtures. Passing
this rehearsal proves operational correctness, atomicity, and auditability; it
does not establish predictive quality or authorize production activation.

The next logical step is independent human review of this report and the
existing operator runbook, followed—only under separate explicit authority—by
a staging rehearsal using real reviewed evidence. Production activation remains
out of scope.
