# PREMATCH calibration readiness observer — 2026-10-03

Status: implementation and offline verification; operator installation remains pending.
This work follows the operator's approval to expose the frozen calendar readiness
in the existing settlement observer. It does not run a new research cycle.

## Runtime behavior

The optional `GOALVISION_LAB_CALIBRATION_READINESS=1` flag adds one compact
`CALIBRATION_READINESS` field to the existing observer document and immutable
`observer_runs` entry. With the flag absent or zero, the observer behavior is
unchanged. Any optional import, database, integrity, plan or output-bound failure
produces a sanitized `UNAVAILABLE` field while the core observer continues.

The module reads a separate query-only audit transaction and the observer's
existing verified ledger snapshot. It closes the audit transaction before
calculating. It uses only stored predictions and stored results. It does not
construct a provider client, send a message, train, evaluate holdout quality,
consume holdout, change selection or touch champion state.

The packaged plan is byte-identical to the prospectively declared October 2 plan:
`9b154abc5b1ca4f18187150c2ca0a8d4d37b93b9c3893e97b2e61457329ca439`.
Runtime loading verifies that fingerprint and the policy contract. Dates never
rebase as samples arrive.

| Window | Start UTC, inclusive | End UTC, exclusive | Minimum observations and independent fixtures |
| --- | --- | --- | --- |
| TRAIN | 2026-09-18 00:00 | 2026-10-02 00:00 | Existing calendar contract, including both classes |
| CALIBRATION_FIT | 2026-10-03 00:00 | 2026-10-10 00:00 | 300 / 300 |
| VALIDATION_EVALUATION | 2026-10-11 00:00 | 2026-10-18 00:00 | 30 / 30 |
| SEALED_HOLDOUT | 2026-10-19 00:00 | 2026-10-26 00:00 | 100 / 100 |

The existing 24-hour gaps, strict label availability, exact model/policy cohort,
fixture grouping, class diversity and reserved/consumed holdout guards remain.
Readiness can become `READY_FOR_OFFLINE_REVIEW`; this grants no runtime fitting
or promotion permission.

## Counts and interpretation

Each window includes eligible resolved observations, independent fixtures,
missing sample counts, window state and all calendar blocking reasons.
Separate descriptive progress counts unique fixture/market opportunities and
whole-fixture lifecycle:

- pending, subdivided into upcoming and awaiting result;
- result available but not yet linked to an accepted learning observation;
- completed;
- excluded, with aggregate reasons.

Canonical captures are superseded by acknowledged PREMATCH SINGLE publications,
then by immutable learning evidence. Repeated SINGLEs are deterministic; COMBO
publications/legs and LIVE/Official records cannot inflate forecast progress.
The learning readiness counts continue to use the exact calendar research
contract, rather than substituting publication counts or treating pending games
as resolved. Lifecycle progress and eligible sample totals need not be equal.

Each source is bounded by the existing 20,000-row policy. SQLite work has the
existing five-second progress deadline; the compact field is bounded to 8 KiB.
Exceeding a bound fails the optional field, without trimming the research sample
or altering the frozen plan. A later capacity change requires separate review.

## Evidence

- `docs/evidence/calibration_observer_20261003/readonly_snapshot.json`:
  query-only projection at **2026-10-03 10:13:07 Europe/Riga**.
- TRAIN: 1,804 eligible observations / 560 independent fixtures.
- FIT: 312 observed opportunities / 101 upcoming fixtures; eligible resolved
  sample 0 / 0, still BLOCKED. Evaluation and sealed holdout remain future.
- Read-only calculation: 1.760 seconds. Projected existing natural observer
  output plus new field: 11,180 bytes, below the installed ADMIN 131,072-byte
  limit; installed ADMIN observer output contract accepts it.
- Before/after protected counts match: 3 learning cycles, 133 training runs,
  59 model artifacts, zero holdout results, zero shadow runs, one activation,
  one champion generation, zero LIVE publications. Champion unchanged.
- `readonly_routes.json`: installed observer remains on de-vig release
  `/opt/goalvision-prematch-devig-83958d1-20261002`; ADMIN Codex systemd
  worker inactive, PID zero, timer disabled/inactive.
- Full source parity checked: installed base plus exactly five reviewed overlay
  files equals the candidate application (813 Python files plus the plan JSON).
  Discovery, settlement, research, weekly and ADMIN routes are protected.

The evidence script calls the read-only report directly and reuses an already
stored natural observer document to validate output compatibility. It never
calls `observe()` or any operational entry point. Its database/contract execution
ran under the network-denying offline runner. Systemd readback was collected
separately because the runner also blocks the local systemd socket.

## Offline verification

See `docs/evidence/calibration_observer_20261003/validation.json` for final
commands, counts and log hashes. Targeted verification covered lifecycle,
deduplication, rejected publications, source scope, excluded fixtures,
unavailable/future labels, frozen-plan tampering, source bounds, query-only
reads, fail-open import/snapshot failure and observer noninterference.
Shared installer regressions cover atomic route recovery, timer restoration,
busy-service drain, hashes, symlinks, protected-route drift and disabled ADMIN
guards; the new plan JSON is included in release integrity checks.

## Operator installation

Only `goalvision-adaptive-learning-observer.service` moves to the new immutable
release. The installer pins the actual de-vig base, package hashes, complete
application source manifest, service argv and protected routes. It pauses only
the observer timer, waits up to 45 seconds for natural service completion,
switches the override atomically, checks invariants and restores the original
timer state. It never starts or kills a service. Failed route changes restore
the prior configuration and timer state.

Normal-user plan mode is read-only. Root apply additionally requires
`autorepair.enabled=false` and the installed ADMIN `DISABLED` marker. Root files
cannot be verified by the normal-user preflight; this check stays mandatory at
apply. The existing operator lock serializes installation with related upgrades.

After package preparation:

```bash
python3 ~/goalvision-operations/calibration-readiness.py
sudo python3 ~/goalvision-operations/calibration-readiness.py --apply
```

Compatible rollback:

```bash
sudo python3 ~/goalvision-operations/calibration-readiness.py --apply --rollback
```

Rollback disables only readiness reporting, retaining compatible code, history,
de-vig research, SINGLE >=1.30, COMBO without a floor, today-only and early COMBO
loss/remaining-leg tracking. Official, LIVE, ADMIN Codex, weekly and the other
PREMATCH service routes stay unchanged.

Package pins and preparation results are recorded in
`docs/evidence/calibration_observer_20261003/package.json` after the source commit.
Installation is not performed by this task. After operator apply, verify the
loaded route and the next natural observer entry; no manual cycle or test send.

## Remaining work

Collect natural results inside the fixed windows. Only after all calendar,
cohort, independent-sample and class gates pass, prepare a separate offline
calibration/evaluation review. Research service integration, holdout evaluation,
shadow qualification and champion promotion remain separately reviewed work.
