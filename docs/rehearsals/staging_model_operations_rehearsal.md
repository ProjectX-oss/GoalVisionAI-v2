# Controlled REAL_ONLY Staging Model Operations Rehearsal

## Result

Status: `STAGING_REHEARSAL_COMPLETED`

The controlled staging rehearsal completed the genuine historical ML artifact
chain and the activation/rollback workflow. This is staging evidence only and
does not authorize production activation.

- Source commit: `5387bd62cd8b435af5d444aca186219b9c879514`
- Environment/scope: `STAGING` / `OFFICIAL_GLOBAL`
- Fixed rehearsal timestamp: `20260728T160000Z`
- Artifact mode: `REAL_ONLY`
- Fixture fallback used: `false`
- Real artifact chain complete: `true`
- Controlled source label: `CONTROLLED_SYNTHETIC_STAGING_SOURCE`
- Chain fingerprint:
  `4ac5ea5879122417ebfa426c38686c104d61c4355da046c21f81934154f165f5`
- Evidence fingerprint:
  `39abc9d897e0cdb15c5166567acb251a7501c9457a0a8a30312871e302400ac1`

The complete canonical machine-readable evidence is
`docs/rehearsals/staging_model_operations_real_only_20260728.json`; the
companion `staging_model_operations_rehearsal.json` is a compact summary.

## Source safety

The supplied SQLite database was not used as an ML-label source. It was opened
read-only for integrity checks and copied byte-for-byte before the isolated
controlled source was created.

- Source schema: `7`
- Source size: `286720` bytes
- SHA-256 before, after, and backup:
  `61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0`
- Foreign-key violations: `0`

All ML and model-operations writes were confined to the ignored
`var/staging_rehearsal/` destination. No source or production database was
mutated.

## Genuine artifact chain

Every step used the production domain service and persisted its normal
provenance:

1. Imported `1200` controlled historical matches.
2. Built `1188` leakage-safe training examples.
3. Created chronological champion and challenger splits. The challenger fold
   contains `688` TRAIN, `200` VALIDATION, and `300` TEST examples.
4. Trained two real logistic model artifacts and fitted real calibration
   artifacts.
5. Reproduced predictions and ran both backtests on the same `300` TEST
   examples with pre-kickoff controlled odds.
6. Completed the default comparison policy with
   `PROMOTE_CHALLENGER` and score
   `0.6474693837108956663057189680`.
7. Settled `30` shadow evaluations over `29` observation days and built
   activation evidence from the persisted results.

Key evidence:

- Comparison:
  `model-comparison-run-ccb115a90ea49ee2555e4567d2d11286c6296f44d755f28381bad83d4c959e37`
- Recommendation:
  `model-comparison-recommendation-645847420f0840a4222f7bd47ca7c1862885419369724dd7fa7af670b6fd8996`
- Shadow evidence:
  `cd7dd67c682b65399d54eb66b14576b8a6cdff5a2f41fd358dfd525c7aa69575`

The controlled odds are derived before outcomes. The shadow market is
deliberately conservative so both genuine runtime paths select no bet; later
settlement still uses the imported final scores.

## Activation, rollback, and audit evidence

The independent audits all passed:

| Phase | PASS | INFO | WARNING | BLOCKER | Fingerprint |
|---|---:|---:|---:|---:|---|
| Pre-bootstrap | 16 | 1 | 0 | 0 | `908610c80c442dcbc38baa7b886eef7b0d9cb35a00616b8b21c62e35ded61a2b` |
| Pre-execution | 17 | 0 | 0 | 0 | `5e0ab9e8ac0ceb84f47f7e139ec3ee31d4ec76846bc86d6ca53152eceebf2129` |
| Final | 35 | 0 | 0 | 0 | `d3ca7c33c23f230f75ec8595d2e80b42b7ee2b3ead1d16323bb1b2536166d7dc` |

Bootstrap, activation preparation, activation, rollback preparation, and
rollback each succeeded. Exact replays were idempotent or rejected as already
executed; changed requests and incorrect confirmations failed closed. The
resolver observed the exact three-generation append-only sequence. Final
counts were one activation, one rollback, three generations, five registry
events, and thirty evidence links.

Injected activation and rollback persistence failures left no partial state;
exact retries succeeded. The final database had `184` append-only triggers,
zero foreign-key violations, and unchanged protected upstream state.

## Verification

- Complete suite: `1094` tests passed.
- Focused staging suite: `12` loaded tests passed; the added exact replay check
  was also exercised independently.
- Application import smoke: `562` modules, zero failures.
- Controlled startup smoke: `HEALTHY`; gate, orchestration, pipeline,
  publication-claim, and Telegram-send counts were all zero.
- Compilation and evidence JSON validation: passed.
- Final source SHA-256 recheck: unchanged.

## Safety conclusion

No Telegram message, Official prediction, bankroll change, settlement,
statistics update, scheduler, worker, startup integration, automatic
activation, automatic rollback, or runtime inference wiring was introduced or
executed. Production activation remains unauthorized.
