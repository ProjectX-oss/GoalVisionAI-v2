# Controlled Lab Model Operations Rehearsal

Date: 2026-07-24

Base commit: `7707bbc835333003e0ff2b2afaba44fbe79daa6a`

Environment: isolated local Lab database

Scope string exercised: `OFFICIAL_GLOBAL` (database-local only)

Fixture label: `FICTIONAL_LAB_REHEARSAL_ONLY`

## Verdict

The manual model-operations workflow behaved safely and deterministically in
the isolated rehearsal database:

- the configured source database was read without mutation;
- a timestamped byte-identical backup was created first;
- only a separate rehearsal copy was migrated from schema v7 to v31;
- the uninitialized state failed closed in both human and JSON output;
- bootstrap succeeded exactly once;
- duplicate and conflicting bootstrap attempts were rejected;
- one activation plan was prepared from a complete typed evidence chain;
- the exact repeated preparation returned the same plan and fingerprint;
- conflicting immutable request content was rejected;
- no activation or rollback execution occurred;
- the original champion remained the resolved generation;
- no Telegram, publication, scheduler, startup, bankroll, settlement,
  prediction-statistics, or production integration was invoked or changed.

The final diagnostic status is `WARNING`, solely because an unexecuted
activation plan is intentionally pending review. This is the expected safe
terminal state.

## Isolation and database provenance

Redacted locations:

- configured source: `<MAIN_CHECKOUT>/data/goalvision.db`
- backup: `<LAB_REHEARSAL_DIR>/goalvision_backup_20260724T230000Z.db`
- working copy:
  `<LAB_REHEARSAL_DIR>/goalvision_lab_rehearsal_20260724T230000Z.db`

Source discovery found exactly one database candidate and confirmed it was the
project-default path. Before copying, the source was schema v7 and had none of
the modern model-artifact, comparison, shadow-evaluation, champion-registry, or
activation-plan tables. That made a production-derived evidence chain
impossible; deterministic fictional fixtures were therefore required.

SHA-256 evidence:

| Object | SHA-256 |
| --- | --- |
| Source before and after rehearsal | `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0` |
| Timestamped backup | `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0` |
| Rehearsal immediately after copy | `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0` |
| Rehearsal after fixtures and operations | `a87b5d980ec21bd61f55776eaf5d6010a5649f5e2baa0bbea360c4f933887afc` |

The backup and source hashes are identical. The rehearsal hash changed only
after its independent migrations, deterministic fixtures, bootstrap, and plan
preparation. Final `PRAGMA foreign_key_check` returned zero violations. The
rehearsal has schema version 31 and 184 append-only/integrity triggers.

## Deterministic fictional evidence inventory

These records exist only to rehearse the operations boundary. They are not
scientific evidence and confer no production approval. The default promotion
and activation policies were not modified.

Champion model:

- artifact ID:
  `historical-model-artifact-61292eade01cb6dc9e33981fe5b565990c65a8a2f37fe63deb6446b4088dfa63`
- artifact fingerprint:
  `61292eade01cb6dc9e33981fe5b565990c65a8a2f37fe63deb6446b4088dfa63`
- calibration set ID:
  `historical-calibration-artifact-set-b5da5055001b33f8894083d9924d7776d0336949418aa34058a8828fb81a6db7`
- calibration fingerprint:
  `b5da5055001b33f8894083d9924d7776d0336949418aa34058a8828fb81a6db7`
- preprocessing fingerprint:
  `3f9d3b3542aed20b1a8f8b16b7a68b2d15cc4849800b16a6ca465cae7c6ff345`

Challenger model:

- artifact ID:
  `historical-model-artifact-a71245558c393106cb5f76b65fe8ba9e85d94dd6b23552cba96767e0acc918c4`
- artifact fingerprint:
  `a71245558c393106cb5f76b65fe8ba9e85d94dd6b23552cba96767e0acc918c4`
- calibration set ID:
  `historical-calibration-artifact-set-9e9777992145e5b12e308291e0f54922a900e9accd6e27c161a1b073598014cc`
- calibration fingerprint:
  `9e9777992145e5b12e308291e0f54922a900e9accd6e27c161a1b073598014cc`
- preprocessing fingerprint:
  `3f9d3b3542aed20b1a8f8b16b7a68b2d15cc4849800b16a6ca465cae7c6ff345`

Shared runtime contracts:

- feature schema: `historical_training_features_v1`
- feature schema fingerprint:
  `e80f41151adce7a0872eafe39733ffc5293579cdd3c81f644465ff74d2d0f478`
- target contract: `historical_raw_market_targets_v1`
- probability contract: `canonical-11-target-contract-v1`
- runtime compatibility: `probability-calibration-v1`

Promotion and shadow evidence:

- comparison run:
  `model-comparison-run-27d342c510a29ba04379d723c66b2026d0b8aa0e136efd54b010490cdd8eb1c6`
- comparison fingerprint:
  `27d342c510a29ba04379d723c66b2026d0b8aa0e136efd54b010490cdd8eb1c6`
- challenger candidate: `challenger-a`
- final recommendation: `PROMOTE_CHALLENGER`
- recommendation ID:
  `model-comparison-recommendation-21d334c12bd163d324d35527c5042b41c91188aeb90855539f257f2e4993e45b`
- recommendation fingerprint:
  `21d334c12bd163d324d35527c5042b41c91188aeb90855539f257f2e4993e45b`
- settled shadow observations: 30
- observation duration: 14 days
- agreement: 1.0
- critical disagreement: 0
- evidence completeness: 1.0
- activation evidence fingerprint:
  `5ccc5487bb146af54ac312ac69c66be6d2fa1aa20fed17f5b53050e05f6be6a3`

Both model and calibration integrity inspectors returned no failures.
Comparison fingerprint and score reproduction returned no failures. Replaying
the unchanged default recommendation policy produced
`PROMOTE_CHALLENGER / PROMOTION_POLICY_SATISFIED`. All nine unchanged
activation-policy validations returned `PASS`.

## CLI observations

Before bootstrap:

- human output: `INVALID_STATE`, exit 5, with `MISSING_CHAMPION` and
  `RUNTIME_RESOLUTION_FAILED`;
- JSON output: the same status, exit, findings, zero generations, schema v31,
  and no pending plans.

Bootstrap:

- first explicit invocation: `BOOTSTRAP_EXECUTED`, exit 0;
- exact duplicate: `BOOTSTRAP_REJECTED`, exit 6;
- altered reason with the initialized scope: `BOOTSTRAP_REJECTED`, exit 6;
- resulting generation count: exactly 1.

Registered generation:

- ID:
  `champion-generation-71e13a42f2c88473193a24e560b263cd50ab8ffc5f2471bc00031e4cbcf9657f`
- fingerprint:
  `71e13a42f2c88473193a24e560b263cd50ab8ffc5f2471bc00031e4cbcf9657f`
- generation number: 1
- reason: `INITIAL_REGISTRATION`

After bootstrap, diagnostics returned `HEALTHY`, exit 0.

Activation preparation:

- an initial chronologically invalid request was rejected, exit 6, because its
  evidence cutoff followed its request timestamp; no plan was persisted;
- the corrected request prepared one plan, exit 0;
- an exact rerun returned the same plan ID and fingerprint, exit 0;
- a different reason under the same request ID returned
  `ACTIVATION_CONFLICT`, exit 6;
- plan ID:
  `activation-plan-08d026d15b5d343030560befb25b1504c70939bc17dbb1fc4f560da62fa086b7`
- plan fingerprint:
  `08d026d15b5d343030560befb25b1504c70939bc17dbb1fc4f560da62fa086b7`

The plan audit showed 30 evidence links, nine `PASS` validations, no execution,
no registry event, and no resulting champion generation.

## Commands executed

Paths below use the redacted aliases defined above. Artifact arguments were
expanded exactly from the adjacent inventory.

```text
python -m app.model_operations_rehearsal.cli prepare-lab-db --source-database <MAIN_CHECKOUT>/data/goalvision.db --destination-directory <LAB_REHEARSAL_DIR> --timestamp 20260724T230000Z

python -m app.model_operations.cli diagnose-state --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output human
python -m app.model_operations.cli diagnose-state --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output json

python -m app.model_operations.cli bootstrap-champion --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output json <CHAMPION_ARTIFACT_ARGUMENTS> --timestamp 2026-07-24T23:10:00Z --reason "FICTIONAL_LAB_REHEARSAL_ONLY initial champion" --operator codex-lab-rehearsal
```

The bootstrap command was invoked three times: first normally, then as an exact
duplicate, then with reason
`FICTIONAL_LAB_REHEARSAL_ONLY conflicting bootstrap`.

```text
python -m app.model_operations.cli diagnose-state --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output json
python -m app.model_operations.cli show-champion --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output json
python -m app.model_operations.cli list-generations --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output json --limit 20

python -m app.model_operations.cli prepare-activation --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output json --request-id lab-rehearsal-activation-prepare-1 --name "FICTIONAL_LAB_REHEARSAL_ONLY activation preparation" --current-generation-id champion-generation-71e13a42f2c88473193a24e560b263cd50ab8ffc5f2471bc00031e4cbcf9657f --current-generation-fingerprint 71e13a42f2c88473193a24e560b263cd50ab8ffc5f2471bc00031e4cbcf9657f <CURRENT_AND_CHALLENGER_ARTIFACT_ARGUMENTS> --comparison-run-id model-comparison-run-27d342c510a29ba04379d723c66b2026d0b8aa0e136efd54b010490cdd8eb1c6 --comparison-run-fingerprint 27d342c510a29ba04379d723c66b2026d0b8aa0e136efd54b010490cdd8eb1c6 --challenger-candidate-id challenger-a --recommendation-id model-comparison-recommendation-21d334c12bd163d324d35527c5042b41c91188aeb90855539f257f2e4993e45b --recommendation-fingerprint 21d334c12bd163d324d35527c5042b41c91188aeb90855539f257f2e4993e45b --shadow-evidence-fingerprint 5ccc5487bb146af54ac312ac69c66be6d2fa1aa20fed17f5b53050e05f6be6a3 --evidence-cutoff 2026-08-01T12:00:00Z --requested-at 2026-08-01T13:00:00Z --reason "FICTIONAL_LAB_REHEARSAL_ONLY reviewed preparation" --operator codex-lab-rehearsal
```

The corrected prepare command was invoked twice identically, then once with
reason `FICTIONAL_LAB_REHEARSAL_ONLY conflicting preparation`. Before those
three calls, the same command was invoked once with
`--requested-at 2026-07-24T23:20:00Z` and was safely rejected.

```text
python -m app.model_operations.cli show-activation --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output json --plan-id activation-plan-08d026d15b5d343030560befb25b1504c70939bc17dbb1fc4f560da62fa086b7
python -m app.model_operations.cli diagnose-state --database <LAB_REHEARSAL_DB> --environment lab --scope OFFICIAL_GLOBAL --output json
```

No `execute-activation`, `prepare-rollback`, or `execute-rollback` command was
run.

## Verification

- focused rehearsal and model-operations tests: 43 passed;
- complete repository suite: 1,050 passed in 78.948 seconds, exit 0;
- source database SHA-256 after verification remained
  `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0`.

## Final database state

| Record family | Count |
| --- | ---: |
| Model artifacts | 2 |
| Calibration artifact sets | 2 |
| Comparison runs | 2 |
| Comparison recommendations | 4 |
| Shadow executions | 30 |
| Shadow settlements | 30 |
| Champion generations | 1 |
| Activation plans | 1 |
| Activation executions | 0 |
| Rollback plans | 0 |
| Rollback executions | 0 |

The final current champion is the original generation 1 model. The challenger
appears only in the unexecuted plan. Final diagnostics report one expected
`PREPARED_PLAN_REVIEW_REQUIRED` warning.

## Safety boundary confirmation

No source database row was changed. No production state was accessed. No
activation or rollback was executed. No background worker, scheduler, startup
hook, model resolver integration, prediction path, publication path, Telegram
transport, bankroll record, prediction statistic, or settlement outside the
fictional shadow fixture was modified. No message was sent.
