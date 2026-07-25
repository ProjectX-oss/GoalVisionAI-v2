# Independent model activation audit

## Audit identity

- Audited source commit:
  `5ad132885b876d59b3e4c1f7f811980e77784b5e`
- Audit schema: `goalvision-model-activation-audit-v1`
- Deterministic generated timestamp: `2026-07-25T00:30:00Z`
- Environment: `LAB`
- Model scope: `OFFICIAL_GLOBAL`
- Database type: SQLite disposable rehearsal copy, opened URI `mode=ro` with
  `query_only=ON` and a bounded timeout
- Overall status: `AUDIT_PASSED`
- Staging assessment: `STAGING_REHEARSAL_READY`
- Audit fingerprint:
  `568552dfeb98b8ebb44230b4001b76c508eca3db9702081e38fbf2a88265f8e6`
- Final commit: the commit containing this report, titled
  `feat: add independent model activation audit`

Technical readiness does not authorize or start staging. Explicit human staging
authorization is still required.

## Scope and methodology

The review independently inspected migration v31 schema objects, foreign keys,
constraints, indexes, append-only triggers, persisted champion generations and
events, activation/rollback requests, plans, validations, execution records,
promotion and settled shadow evidence, historical model/calibration artifacts,
the fail-closed resolver, manual operations CLI, rehearsal evidence, and the
operator runbook.

The evidence database was the completed activation-and-rollback Lab rehearsal
copy. The audit opened it read-only and did not invoke bootstrap, preparation,
activation, rollback, Telegram, publication, inference, scheduling, or startup
entry points. Corruption-path tests used disposable test copies only.

## Complete check inventory

| Category | Checks | Result |
| --- | --- | --- |
| Schema | version, tables, indexes, append-only triggers, foreign keys, uniqueness/idempotency | 6 PASS |
| Registry | current enforcement, generation chain, bootstrap uniqueness, event references, event sequence | 5 PASS |
| Activation | plan/execution chain, validations, settled shadow evidence, promotion, staleness, artifact provenance, idempotency | 7 PASS |
| Rollback | plan/execution chain, target validity, generation semantics, incident evidence, validations, idempotency | 6 PASS |
| Resolver | exact persisted resolution, fail-closed verification, runtime unwired, switching manual-only | 4 PASS |
| CLI | confirmations, read-only inspection, no side-effect integrations, known-failure guidance | 4 PASS |
| Rehearsal | isolation/hash/replay/atomicity/no Telegram or runtime change | 1 PASS |
| Runbook/staging | CLI consistency, explicit human staging authorization | 2 PASS |

Summary: **PASS 35, INFO 0, WARNING 0, BLOCKER 0**.

## Findings

### Schema and registry

Migration v31 is present, and all ten activation/rollback tables, five explicit
indexes, declared foreign keys, uniqueness/idempotency constraints, and twenty
update/delete prevention triggers exist. `PRAGMA foreign_key_check` is clean.
The registry uses the unique highest generation for a scope as the current
champion instead of a mutable active flag. The reviewed three-generation chain
is contiguous and acyclic, has exactly one bootstrap generation, and has a
consistent five-event creation/retirement sequence with no orphan event.

### Activation

The execution references one request and immutable prepared plan. Nine
deterministically ordered validations are PASS. Thirty evidence links match
their exact shadow execution and settlement fingerprints. The retained
recommendation is `PROMOTE_CHALLENGER`, the plan matched the champion it
replaced, artifact/provenance references match, and no plan has duplicate
execution rows.

### Rollback

The execution references one request and immutable plan. The target was a
previously active compatible generation. Rollback appended generation three
rather than mutating or reusing generation one, and its previous link points to
the replaced generation two. Incident reference, operator reason, and operator
identity exist. No rollback plan has duplicate execution rows.

### Resolver and CLI

The resolver returns the unique highest generation only after exact model,
preprocessing, estimator, calibration, feature-schema, probability-contract,
provenance, and runtime-compatibility verification. Missing or corrupt evidence
fails closed with no fallback. Runtime inference remains unwired.

The manual CLI distinguishes read-only and state-changing commands, requires
`ACTIVATE_CHAMPION` or `ROLLBACK_CHAMPION`, exposes no generic `--yes`, opens
inspection commands read-only, returns non-zero typed failures without known
tracebacks, and gives stop/inspect/idempotent-replay guidance for ambiguity.
There are no Telegram, Official publication, bankroll, or scheduler calls.

### Rehearsals

The retained reports show isolated disposable databases, source SHA-256
preservation, real CLI/domain boundaries, exact confirmation failures, exact
idempotent replay and conflict handling, resolver transitions, append-only
rejection, and injected-failure atomicity. They report no Telegram send and no
runtime or Official behavior change.

### Runbook deviations and remediation

The initial independent check found one documentation blocker: the existing
runbook covered the commands and recovery concepts but did not state the full
25-step staging/production authorization, automation prohibition, incident
record, and evidence-retention flow in one normative sequence.

Remediations applied:

- **documentation correction:** added the reviewed 25-step operator flow;
- **operational guidance correction:** added explicit staging and production
  authorization boundaries, forbidden automation, incident records, and
  evidence retention;
- **test coverage correction:** added deterministic static consistency checks
  and a second-person reviewer checklist;
- **code correction:** none was required in activation, rollback, registry,
  resolver, or product behavior.

Unresolved warnings: none. Blockers found: one documentation blocker; fixed and
re-audited to PASS.

## Verification evidence

- Focused independent audit tests: **18 passed**
- Cross-domain focused matrix: **299 passed**
- Full suite: **1079 passed**
- Fresh v31 migration, upgrade migration, append-only enforcement, injected
  atomic failures, resolver transitions, Lab Telegram boundaries, transport,
  and Official pipeline regressions are covered by the passing matrix/suite.
- CLI help, human audit, and canonical JSON audit smoke checks passed.
- Compilation, complete import smoke, and controlled startup passed.

No secret, credential, absolute local path, database, backup, Telegram response,
or environment file is included in this report.

## Recommendation and unchanged boundaries

The reviewed foundation is technically `STAGING_REHEARSAL_READY`, subject to a
new explicit human staging authorization and a separately scoped staging
procedure. This audit did not start a staging rehearsal.

Runtime inference remains unwired. No Telegram message was sent. Official
publication, prediction logic, model activation state, bankroll, settlement,
statistics, scheduling, startup behavior, workers, and automatic activation or
rollback remain unchanged.
