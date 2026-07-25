# Controlled Staging Model Operations Rehearsal

## Result

Status: `STAGING_REHEARSAL_COMPLETED`

The controlled staging rehearsal passed. This is technical staging evidence,
not production authorization.

- Source commit:
  `78f218632fafe4ceeab708b5dd92dbd1e48a890f`
- Final commit: the atomic commit containing this report, with message
  `feat: add controlled staging model operations rehearsal`; its hash is
  recorded in the completion handoff because a commit cannot contain its own
  hash.
- Environment/scope: `STAGING` / `OFFICIAL_GLOBAL`
- Fixed rehearsal timestamp: `20260725T120000Z`
- Evidence schema:
  `goalvision-staging-model-operations-rehearsal-v1`
- Evidence fingerprint:
  `7e8f4d6b307009b5d085e5cdb40695a9f4e62e0bbd0cb60a11be33122ab45d91`

The canonical machine-readable evidence is
`docs/rehearsals/staging_model_operations_rehearsal.json`.

## Source safety and artifact selection

The explicitly supplied `data/goalvision.db` source was opened read-only for
inventory and integrity checks.

- Source schema version: `7`
- Source size: `286720` bytes
- Source SHA-256 before:
  `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0`
- Source SHA-256 after:
  `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0`
- Byte-identical backup SHA-256:
  `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0`
- Source foreign-key violations: `0`

The v7 source has no complete persisted modern
model/calibration/backtest/comparison/promotion/settled-Shadow chain.
The explicitly authorized fallback was therefore selected with reason codes
`SOURCE_SCHEMA_LACKS_COMPLETE_ML_CHAIN` and
`DETERMINISTIC_FIXTURE_FALLBACK_SELECTED`. Every generated artifact is marked
`FICTIONAL_STAGING_REHEARSAL_ONLY`.

No candidate chain was rejected individually because the source has none of
the required modern chain tables. The selected complete fictional chain used:

- champion model:
  `historical-model-artifact-61292eade01cb6dc9e33981fe5b565990c65a8a2f37fe63deb6446b4088dfa63`;
- champion calibration:
  `historical-calibration-artifact-set-b5da5055001b33f8894083d9924d7776d0336949418aa34058a8828fb81a6db7`;
- challenger model:
  `historical-model-artifact-a71245558c393106cb5f76b65fe8ba9e85d94dd6b23552cba96767e0acc918c4`;
- challenger calibration:
  `historical-calibration-artifact-set-9e9777992145e5b12e308291e0f54922a900e9accd6e27c161a1b073598014cc`;
- comparison:
  `model-comparison-run-6e894f65db1a0b8ba8d4ada923d6b441244ca08219d1b25c12e139f39c84b14e`;
- promotion recommendation:
  `model-comparison-recommendation-187fbd8fdbc15cc517174b6e9c2b5482ffb49b53d9853ee4cb0211e907f76ddb`;
- settled Shadow evidence fingerprint:
  `d4d16b49baabd3d1b05d062a9b8cc13961d2b4975bc797feb42f4d3ce13a038c`.

## Mandatory audit gates

All audit invocations used both human and JSON output.

| Phase | Status | PASS | INFO | WARNING | BLOCKER | Fingerprint |
|---|---:|---:|---:|---:|---:|---|
| Pre-bootstrap | `AUDIT_PASSED` | 16 | 1 | 0 | 0 | `1445cab990f73d68b24cdda6f0ac76366d0c49f656a97a1d847eedab76b1f531` |
| Pre-execution | `AUDIT_PASSED` | 17 | 0 | 0 | 0 | `6da8fc7591257e5c0d8884b2c9988e4e0675091f9e67304a2f172594d69f140b` |
| Final independent audit | `AUDIT_PASSED` | 35 | 0 | 0 | 0 | `7f95c55b2a79446aad8e95003688cc1fab10b903d5955bb3f241d4c5f7a995cd` |

The pre-bootstrap INFO is the expected explicit unbootstrapped staging
registry. Final staging readiness is `STAGING_REHEARSAL_READY`.

## Model operation transitions

Bootstrap executed once. A second bootstrap was rejected because initialization
is intentionally one-shot; both its exact re-attempt and changed-content
conflict exited `6` with `BOOTSTRAP_REJECTED`. Exact activation preparation
replay exited `0` and returned the same prepared plan; changed content under
the request ID exited `6` with `ACTIVATION_CONFLICT`.

Activation then executed exactly once. Exact execution replay returned
`ACTIVATION_ALREADY_EXECUTED` at exit `6`; changed content returned
`ACTIVATION_CONFLICT` at exit `6`; the wrong confirmation returned
`CONFIRMATION_REJECTED` at exit `2`.

Rollback preparation executed, replayed idempotently, and rejected changed
content with `ROLLBACK_CONFLICT` at exit `6`. Rollback executed exactly once.
Exact execution replay returned `ROLLBACK_ALREADY_EXECUTED` at exit `6`;
changed content returned `ROLLBACK_CONFLICT` at exit `6`; the wrong
confirmation returned `CONFIRMATION_REJECTED` at exit `2`.

The read-only resolver produced the exact append-only chain:

1. `champion-generation-7e0158680bf188ff09bc3131c03c160e030cafe4a3c9c1e40c5d8e9c58b19f8b`
2. `champion-generation-cd78dff99e156bfb6ca41c22a2d9d7181c94b59966c95a464130e887a034fec5`
3. `champion-generation-9c081a2c78dfb538fb57878ab9cc6cada4a760e0ee4a012741e743108c10d1f8`

The final registry event sequence was `INITIAL_REGISTERED`,
`RETIRED_BY_ACTIVATION`, `CHAMPION_ACTIVATED`,
`RETIRED_BY_ROLLBACK`, `CHAMPION_ROLLED_BACK`.

## Persistence and recovery evidence

- Foundation/disposable-before canonical-content SHA-256:
  `faea10afa7365bd6cc78b475f9948cd1fc06727a11b73ef7c1b14047c5037a6e`
- Disposable-after canonical-content SHA-256:
  `d43bba96446535edfe3b46d90ff7de2b18509606b958566087d2b7b38a6942ea`
- Generations: `3`
- Activation requests/plans/executions: `1 / 1 / 1`
- Rollback requests/plans/executions: `1 / 1 / 1`
- Registry events: `5`
- Evidence links: `30`
- Append-only triggers: `184`
- Foreign-key violations: `0`
- Protected upstream state unchanged: `true`

Injected persistence failures proved
`ACTIVATION_FAILURE_ATOMIC`, `ACTIVATION_EXACT_RETRY_SUCCEEDED`,
`ROLLBACK_FAILURE_ATOMIC`, and `ROLLBACK_EXACT_RETRY_SUCCEEDED`.

## Commands and verification

The exact authorized rehearsal command is documented in
`docs/model_operations_runbook.md` and was executed with the source, destination,
timestamp, source commit, `prefer-real`, explicit fixture fallback, both audit
formats, JSON evidence destination, and JSON output shown there. It exited `0`.
An independent run with the same inputs and human output also exited `0` and
returned the identical evidence fingerprint
`7e8f4d6b307009b5d085e5cdb40695a9f4e62e0bbd0cb60a11be33122ab45d91`.

- Focused staging rehearsal:
  `python -m unittest tests.test_staging_model_operations_rehearsal -v` —
  12 passed in 39.229 seconds.
- Cross-domain focused matrix: 186 passed in 139.496 seconds.
- Complete suite: 1091 passed in 215.801 seconds.
- Compilation: `python -m compileall -q app tests` — exit `0`.
- Complete import smoke: 566 application modules, zero failures.
- Controlled startup:
  `python -m app.official_prediction_operations.cli smoke-startup --json-output`
  — `HEALTHY`, exit `0`; gate, orchestration, pipeline, publication-claim, and
  Telegram-send counts were all zero.
- Staging rehearsal, independent audit, and model-operations CLI help smokes:
  exit `0`.
- Staging human and canonical JSON output smokes: exit `0`, matching evidence
  fingerprints.
- Source and backup byte SHA-256 re-verification: matched.

## Safety conclusion

No Telegram message was sent. No Official publication, bankroll, settlement,
statistics, scheduling, worker, automatic activation, automatic rollback,
startup execution, or runtime inference wiring was introduced or changed.
Production activation remains unauthorized.

## Known limitations and next step

The supplied v7 source contains no real persisted reviewed ML artifact chain,
so this first rehearsal necessarily proves the explicit deterministic fixture
path. Real-chain inventory remains read-only and fails closed on incomplete or
ambiguous evidence. The next logical step is to persist and independently
review a complete real candidate chain in an isolated staging source, then run
the same authorized procedure in `real-only` mode. That later action still
must not wire runtime inference or authorize production.
