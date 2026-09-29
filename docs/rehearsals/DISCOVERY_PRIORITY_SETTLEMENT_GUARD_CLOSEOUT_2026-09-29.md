# Discovery Priority / Settlement Guard — production audit closeout

Final audit verdict: **DISCOVERY_PRIORITY_SETTLEMENT_GUARD_VALIDATED**.

Recorded 2026-09-29 from the operator-supplied successful VPS/systemd result.
This closes only the Discovery Priority / Settlement Guard phase. No subsequent
development phase is started or authorized by this record.

## Evidence provenance and preservation

The production findings below are the operator's reported results. This audit
does not claim a new independent production validation. The supplied result
contains installed status, a top-level forward evidence PASS, its exact window,
and discovery counter/output observations, but no complete per-service report,
raw journal export, exact cycle totals or `guard_counts` object.

The companion [structured record](discovery_priority_settlement_guard_closeout_2026-09-29.json)
distinguishes supplied facts, conclusions implied by PASS, and unavailable fields.
The [SHA-256 sidecar](discovery_priority_settlement_guard_closeout_2026-09-29.sha256)
fingerprints the Markdown and JSON bytes. These are new immutable audit artifacts:
retain them unchanged after commit; record later corrections in a separate dated
addendum. Their hashes identify this closeout, not an unavailable raw production
export. Historical preparation reports and package evidence remain unchanged.

The audit branch starts at the exact recovery-v2 commit. The unrelated current
workspace and its pre-existing changes are preserved.

## Implementation and manifest lineage

| Item | Exact value |
| --- | --- |
| Source implementation commit | `ec0fa32789476d5fad497c05cbf93e3c78e09d18` |
| Recovery-v1 commit | `9ff50c2380280c8343833bd08658600e64937d83` |
| Recovery-v2 / audit base commit | `26391232cb2e31a1d636ea20b6198af0a452c4ae` |
| Preserved predecessor manifest | `c50abe7fc9f7f44a3c05d12fbc81fb41cf53be847d17a09b5f316f0ac85bcfb5` |
| Installed recovery-v2 package manifest | `b32966e45f178e0f74ff005b25adbe684933bf372b62c4da16cd4b22a32c7cc7` |
| `recovered_at` | `2026-09-29T10:07:25.396888+00:00` |
| `installed_at` | `2026-09-29T10:07:25.396888+00:00` |
| `guard_seconds` | **180** |

The predecessor digest remains the transaction's top-level manifest. Recovery
provenance binds it to the recovery-v2 package. The original receipt text/hash and
application argv remain part of the recovery contract; this closeout does not
invent or reproduce an original receipt hash that was not supplied.

## Successful production result

| Stage / field | Operator-reported result |
| --- | --- |
| Production preflight | PASS |
| Recovery finalization | Successful |
| `guard_installed` | `true` |
| `phase` | `installed` |
| Post-recovery status `pins` | PASS |
| Forward evidence top-level `verdict` | **PASS** |
| Evidence `since` | `2026-09-29T10:07:25.396888+00:00` |
| Evidence `until` | `2026-09-29T13:42:00.990951+00:00` |

Preflight and finalization are recorded from the operator's stated successful
production outcome; their full command outputs were not supplied. The installed
status and timestamps substantiate completed recovery. This is the later
production outcome for the earlier preparation-only handoffs, whose historical
"pending" and "not executed here" statements remain intact.

### Required scheduled cycles

| Service | Required qualifying cycles | Exact observed count | Conclusion from reported PASS |
| --- | ---: | --- | --- |
| `goalvision-lab-v2-discover.service` | 2 completed | Unavailable | At least 2 |
| `goalvision-lab-combo-settle.service` | 3 successfully completed `SETTLEMENT_EXECUTED` | Unavailable | At least 3 |
| `goalvision-adaptive-learning-observer.service` | 2 completed | Unavailable | At least 2 |

These lower bounds follow from the reviewed evidence implementation and the
operator's top-level PASS; they are not substituted exact counts. Settlement
ACTIVE/IMMINENT deferrals do not satisfy the executed-cycle threshold. An execution
marker alone is insufficient: scheduled manager completion and exit status zero
are required. Calendar alignment alone does not prove timer causation; the
production scheduling assertion comes from the operator's result.

### Blocking counters and guard records

Explicitly supplied for completed discovery evidence:

| Field | Value |
| --- | --- |
| `QUOTA_DB_CONTENTION_EXHAUSTED` | 0 |
| `QUOTA_DB_CONTENTION_RETRY` | 0 |
| `DATABASE_LOCK` | 0 |
| `SERVICE_FAILURE` | 0 |
| `exit_status` | 0 |
| `expected_output_seen` | `true` |
| `missing_scheduled_starts` | `[]` |

Across the required services, the reported top-level PASS implies no
`QUOTA_DB_CONTENTION_EXHAUSTED`, `DATABASE_LOCK` or `SERVICE_FAILURE`, no failed
discovery, no missing required evidence, and complete valid guard records. It
also implies zero `SETTLEMENT_DEFERRED_DISCOVERY_STATE_UNAVAILABLE` records.
These are implementation-backed implications, not newly captured counter rows.
Retry counts outside discovery were not supplied; retries are informational in
the evidence implementation.

Exact `guard_counts` for `SETTLEMENT_EXECUTED`,
`SETTLEMENT_DEFERRED_DISCOVERY_ACTIVE`,
`SETTLEMENT_DEFERRED_DISCOVERY_IMMINENT`, and
`SETTLEMENT_DEFERRED_DISCOVERY_STATE_UNAVAILABLE` were not supplied. No counts
were inferred from elapsed time or timer calendars.

### Read-only attempt to obtain exact totals

The existing recovery-v2 package was verified locally: its `SHA256SUMS` digest
matches the recovery manifest above and all 13 listed files pass checksum checks.
The following existing read-only command was attempted once:

```bash
sudo -n /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v2-20260929/control.py evidence --manifest-sha256 b32966e45f178e0f74ff005b25adbe684933bf372b62c4da16cd4b22a32c7cc7 --since 2026-09-29T10:07:25.396888+00:00
```

It exited 1 with `sudo: a password is required`; the evidence program did not
start. No fresh report or exact totals were obtained. The command uses capture
time as its end boundary, so a later successful run would be a separate evidence
window, not a reproduction of the supplied 13:42:00.990951 result. No privilege
configuration was changed. Exact counts are optional for this closeout because
the operator supplied the gated production PASS.

## Diagnosed false-positive recovery issues

1. **Unordered systemd dependency properties.** The interrupted install reported
   `UNIT_PROPERTY_DRIFT_After` when daemon-reload changed member order while
   membership was unchanged. Recovery-v1 compares only `After`, `Before`,
   `Requires`, `Wants`, `OnFailure`, and `OnSuccess` as exact case-sensitive token
   sets. Ordering, whitespace between tokens and duplicate identical members are
   immaterial. Missing properties, including pinned-empty dependency properties,
   and missing, extra or changed members still fail. There is no substring,
   alias, path or unit-name normalization.
2. **Omitted empty execution properties.** Recovery-v1's unconditional presence
   check rejected production output that omitted empty `ExecCondition`,
   `ExecStartPre`, `ExecStartPost`, `ExecStop`, and `ExecStopPost`, reporting
   `UNIT_PROPERTY_DRIFT_ExecCondition`. Recovery-v2 restores the predecessor's
   `props.get(key, '') == expected` semantics for non-dependency stable properties.
   An omitted property passes only if the pinned value is empty. Nonempty values
   still require exact equality, including whitespace. Dependency presence and
   exact membership checks remain mandatory.

Both fixes correct representation comparisons without weakening the safety
invariants: exact predecessor authorization, original argv, package inventory and
hashes, installed runtime/drop-in bytes, loaded wrapper ExecStart,
`NeedDaemonReload=no`, inactive/dead settlement at recovery, all five timers
active/waiting, unit/environment/calendar/security pins, ownership and symlink
checks, disabled ADMIN sender, and installed stagger-v4 provenance remain required.
Finalization rechecks full preflight under the existing exclusive lock and changes
only transaction metadata atomically. Baseline, runtime wrapper and evidence
helpers are byte-identical from the source implementation through recovery-v2.

See the preserved [recovery-v1 handoff](../operations/PREMATCH_SETTLEMENT_GUARD_RECOVERY.md)
and [recovery-v2 handoff](../operations/PREMATCH_SETTLEMENT_GUARD_RECOVERY_V2.md).

## Rollback compatibility and scope

Rollback compatibility remains intact. The recovery-v2 package accepts the
preserved predecessor manifest only with valid package-bound recovery provenance,
retains that provenance through rollback/retry, and restores the exact original
application argv. The preserved
[offline validation record](../../operations/prematch-settlement-guard/evidence/recovery-validation.json)
reports 33 recovery, 38 guard and 61 stagger tests (132 total), including exact
rollback and reload-failure retry checks. Those are historical test results;
they were not rerun or represented as production rollback evidence in this task.
No rollback was attempted.

Closeout checks are limited to documentation and evidence consistency: JSON
validity, exact supplied values and provenance distinctions, source lineage,
unchanged package/runtime/evidence hashes, local links, SHA-256 sidecar, and Git
diff scope/whitespace. No application tests or backtests are needed for this
documentation-only change.

Closeout actions made no runtime or configuration changes: no systemd mutation,
daemon-reload, service/timer controls, API calls, Telegram sends, business DB
access/writes, prediction/model/policy changes, or production receipt changes.
Only the new audit artifacts and an appended TASKS completion entry are committed
locally. No push or further development phase is part of this closeout.
