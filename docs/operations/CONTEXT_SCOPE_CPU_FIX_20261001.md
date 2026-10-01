# Discovery context CPU root cause and scoped hotfix — 2026-10-01

Status: **PASS for deployment and first natural post-deployment cycle; settlement and longer-term stability NEEDS_MORE_EVIDENCE.**

The operator activated release `goalvision-prematch-context-scope-1a18dc0-20261001`.
Read-only checks confirmed the entire Python tree, release environment, drop-in,
loaded discovery route and unchanged protected service routes. The accuracy-combo
flag is preserved and the timer is active. Next scheduled run: 19:30 Europe/Riga.
Only the two-file CPU fix is deployed; the wider AI/ML batch remains prepared.
Deployment evidence: `docs/evidence/forward_ai_ml_20261001/context_scope_deployment.json`.

## Root cause

The operator's three bounded nonblocking samples at 15:27:44–15:27:55 UTC
contained two successful Python stacks and one sampler race. Both successful
stacks show `validate_retained_document → _validate → EvidenceRepository.load →
available_pins → ProspectiveObservation._sources → observe → LearningCoordinator.shadow`.
At the first sample, discovery had run 27:42 with lifetime CPU 93.4%.

`available_pins` fully validated every pre-cutoff source before filtering for
the three exact fixture/competition queries. Each new opportunity repeated
this work in diagnostic collection and snapshot assembly. This is a concrete
CPU hotspot before publication, not evidence of a SQLite lock or provider wait.
The evidence copy has 5594 pre-cutoff sources containing 91,613,453 material bytes.

## Change and integrity

The repository keeps one process-local index of fully verified source IDs by
exact kind/query, keyed by the exact durable decision receipt and SQLite
revision. It stores no source payloads, prediction values or selection results.

- A cold index still fully validates every earlier source, including unrelated scopes.
- A different cutoff, same-connection DML, another connection's commit, or schema
  changes invalidate the index. The revision is checked again after reading;
  an intervening change fails closed and discards the index.
- Partial/failed builds are never reused. Every lookup verifies the durable marker.
- Diagnostic selection and snapshot assembly still reload every scoped pin and
  validate material, registration, chronology, expiry and source scope.
- Ordering, sorted candidate manifests, snapshot bytes and fingerprints are unchanged.
- No schema migration, persistent cache, provider request, model or policy change.

## Verification

Read-only measurement used an isolated SQLite online backup and the same
cutoff/scope, without executing a discovery/publication cycle:

| Measurement | Seconds |
|---|---:|
| Original full lookup | 7.556705 |
| Fixed cold lookup, full validation retained | 8.184019 |
| Fixed warm lookup median, 100 calls | 0.000093 |
| Fixed warm lookup maximum | 0.000219 |

All candidate IDs match exactly (1 TARGET / 19 CURRENT / 0 PREVIOUS).
This is lookup timing, not an end-to-end runtime claim. The first scan still
grows with retained history; warm lookups avoid multiplying it by opportunities.

Three existing production snapshots were rebuilt from their retained inputs on
the isolated source copy. All three match the full saved snapshot exactly,
including hashes, and pass pinned reproduction.

- 200 targeted source/capture/snapshot/readiness tests PASS (30.53 s).
- 1498 wider PREMATCH/adaptive/Lab/COMBO tests + 34 subtests PASS (195.03 s).
- 6 installer tests PASS (0.30 s), including no-kill drain refusal and rollback.
- Counts overlap; do not sum them as distinct tests.
- During pre-deployment verification no production service control, manual provider
  request, Telegram send, champion change, Official change or LIVE enablement occurred.
  The subsequent operator-approved deployment is recorded above.

Structured evidence: `docs/evidence/forward_ai_ml_20261001/context_scope_cpu_fix.json`.

## Operator package

Prepared directory: `/home/arvis/goalvision-operations/context-scope-cpu-20261001`.
Short entry point: `/home/arvis/goalvision-operations/cpu-fix.py`.

Read-only package check:

    python3 ~/goalvision-operations/cpu-fix.py

Only after separate operator deployment approval:

    sudo python3 ~/goalvision-operations/cpu-fix.py --apply

Rollback after approval:

    sudo python3 ~/goalvision-operations/cpu-fix.py --apply --rollback

The package overlays ONLY `capture/repository.py` and `snapshot/service.py`
under `app/prematch_football_context` onto the active c490866 discovery release.
It preserves the existing accuracy-combo flag. It does not deploy the separate
AI/ML research batch. Hash checks cover the base Python tree, overlay and updater.
It changes only the discovery route; other listed service routes are verified
unchanged. Rollback restores the c490866 route without touching any data.

The updater pauses the discovery timer and allows an active run up to 60 seconds
to drain. If still running, it refuses and restores the previous timer state.
It never stops/kills an active discovery or manually starts a discovery/send.
Naturally scheduled discovery resumes only if the timer was previously active.
A successful natural post-deployment cycle and delivery evidence remain required.

## Changed files

- `app/prematch_football_context/capture/repository.py`
- `app/prematch_football_context/snapshot/service.py`
- `tests/test_prematch_football_context_scope_index.py`
- `operations/context-scope/update.py`
- `tests/test_prematch_context_scope_upgrade.py`
- This runbook, structured evidence, integrated status and `TASKS.md`.

## First natural post-deployment cycle

2026-10-01 19:30:01–19:36:46 Europe/Riga: 405 seconds elapsed,
246.099231 CPU seconds, exit 0 and service result success. The scheduled run
evaluated 1391 candidate markets from 143 fixtures with current odds, using
262 API calls. Accuracy COMBO found 72 eligible fixtures and prepared three.
Three SINGLE and three COMBO messages were accepted and all six immutable
receipt fingerprints/message IDs were independently verified in the read-only
Lab ledger (SINGLE 305–307; COMBO 308–310). No terminal error or unknown delivery.

This establishes natural publication/receipt success, not settlement or model
quality. Different cycle workloads prevent attributing an exact end-to-end
speedup factor. Optional context diagnostics still report 147 unavailable target
snapshot attempts; data readiness is a separate remaining limitation.
Evidence: `docs/evidence/forward_ai_ml_20261001/context_scope_natural_cycle.json`.
