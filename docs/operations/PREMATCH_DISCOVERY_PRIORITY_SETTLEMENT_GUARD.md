# PREMATCH discovery priority settlement guard — evidence blocker

Status: **BLOCKED_REQUIRED_PRODUCTION_EVIDENCE_UNAVAILABLE**.

Branch: `ops/prematch-discovery-priority-guard`, based on
`fca075d4e01028ab17f0b8c1d1d3dc5378beedb4`.
Inspection date: 2026-09-29. No installable package has been prepared.

## Why implementation stopped

Task section 8 requires reviewing completed settlement runtimes from at most
seven days of production systemd journals before choosing a horizon. It explicitly
requires stopping if a defensible horizon cannot be established.

The current `arvis` account can read application journal records, but cannot read
the system journal containing PID 1 service start/completion records. A bounded
seven-day query returned **zero visible manager records**. This does not mean
there were zero completed invocations. `sudo -n -l` reports that a password is
required. Protected ADMIN configuration and the installed timer-stagger transaction
are also unreadable. No access controls were changed.

An existing 2026-09-25 audit export was checked:
`/home/arvis/goalvision-operations/prematch-audit-20260925/journal-invocations.json`.
It reports visible application-log spans and traceback counts, without verified
completion durations or the requested distribution. Those spans are unsuitable
as settlement execution bounds.

| Required evidence | Result |
| --- | --- |
| Completed settlement invocation count | Unavailable |
| Minimum / median / p95 / maximum runtime | Unavailable |
| Loaded `TimeoutStartUSec` | `10min` |
| Loaded `TimeoutStopUSec` | `1min 30s` |
| Loaded `KillMode` / `SendSIGKILL` | `control-group` / `yes` |
| Selected pre-discovery horizon | None; review blocked |

The start timeout alone does not replace the required runtime distribution.
Termination can also consume the stop timeout. No timeout was changed, and no
unsupported horizon was selected.

## Read-only production findings

The sanitized capture is
[`read-only-inspection.json`](../../operations/prematch-settlement-guard/evidence/read-only-inspection.json).
SHA-256: `0bcd07d5055d9aed4ee481631b149cef360b7e35072d533e365f72f131b46781`.
It records loaded properties, unit/drop-in hashes, the settlement environment
value hash, and the environment-file hash. Environment values are withheld.
These are inspection pins, not a completed deployment baseline or package manifest.

All five loaded calendars match the requested installed stagger v4 schedules:

- Discovery: `*-*-* 09..22:00,30:00 Europe/Riga`.
- Settlement: `*-*-* *:05,15,25,35,45,55:00`.
- Observer: `*-*-* *:08,38:00`.
- Weekly: `Sun *-*-* 22:28:00 Europe/Riga`.
- Research: `*-*-* 04:12:00`.

All ten inspected PREMATCH service/timer units report `NeedDaemonReload=no`.
The loaded settlement drop-in is `90-reviewed-prematch-v2.conf`; its exact hash
and the original unit hash are in the capture. A complete foreign-drop-in
inventory check remains part of future preflight.

The actual loaded settlement argv is:

```text
/home/arvis/GoalVisionAI/.venv/bin/python -P -m app.lab_combo settle --send --adaptive-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db
```

Loaded settings: `Type=oneshot`, `User=arvis`, empty explicit `Group`,
`WorkingDirectory=/home/arvis/GoalVisionAI`, `StandardOutput=null`,
`StandardError=journal`. The loaded environment file is
`/opt/goalvision-prematch-quota-557d5af2-f24738b05fef/release.env`.
The location agrees with the reported quota-hardening release; application source
integrity has not been independently recertified by this inspection.

## Historical overlap and conditional projection

The operator supplied discovery invocation
`4d931713a53b4404bae23bd990ccebdb`, starting at 2026-09-28 14:30:20
Europe/Berlin and still running when settlement started at 14:35:00.
The accessible application journal independently contains seven retry records and
two exhaustion records for that invocation. The capture preserves only their
timestamps and codes. Systemd start/completion evidence is inaccessible here.

Timer staggering separates nominal start times. A discovery running longer than
five minutes can still overlap the next settlement activation. This supports a
runtime guard; it does not establish settlement as the exact SQLite writer at
every contention moment.

Given the supplied active state at settlement start, the required projected
decision is `SETTLEMENT_DEFERRED_DISCOVERY_ACTIVE`. The intended deferred path
would launch no settlement Python process and perform zero API calls, Telegram
sends, database/ledger writes, or quota claims. This is a **conditional design
projection**, not an executable rehearsal or a measured historical counterfactual.
No cycle was replayed.

## Required design after evidence becomes available

Use a root-owned, read-only executable through a settlement-only `ExecStart`
drop-in. Preserve the exact business argv and inherited environment with exec
replacement. Keep all other service settings, timers, and discovery behavior.

1. Read discovery `ActiveState`, `SubState`, and `InvocationID`.
2. Defer on `activating`, `active`, or `deactivating`; validate other states.
3. Fail closed on missing, unreadable, invalid, or inconsistent observations.
4. Read the real systemd-resolved next discovery timer deadline. Defer inside
   the evidence-reviewed horizon, without calculating timezone offsets.
5. Re-read state/deadline immediately before exec; defer if discovery became
   active or observations are inconsistent.
6. Emit one sanitized structured deferral record and exit zero, with no retry,
   sleep, application import, background job, or business operation.

Because stdout is currently discarded, emit guard records on the existing
**journal-backed stderr**, preserving both stdout/stderr routing settings.
Do not use `ExecCondition`: deferred invocations must retain normal systemd
start/completion evidence. ACTIVE/IMMINENT are informational. STATE_UNAVAILABLE
remains local evidence and prevents forward PASS. ADMIN sender stays disabled.

The later controller must expose read-only `check`, `status`, and `evidence`,
plus operator-run `install` and `rollback`. Its only service-control operation
is conditional `daemon-reload`; active settlement causes safe refusal.
Rollback removes only verified package-owned routing/artifacts and cannot undo
an already-running settlement, completed business work, or past overlap.
No executable controller, guard, drop-in, or install/rollback command is supplied
in this blocked revision.

Forward evidence must require at least two completed scheduled discovery cycles,
three actual executed settlement cycles, and two observer cycles after deployment.
Deferrals cannot satisfy executed minimums. Exhaustion, database locks, service
failures, nonzero discovery exit status, and missing required evidence prevent
PASS. Successful retries alone do not fail a run. The existing evidence reader
has not been changed before resolving this prerequisite.

## Read-only evidence needed to resume

An operator with existing root access can collect the missing manager records.
These commands do not start or stop any service and do not change ADMIN state.
Review exports before sharing; do not export environment values or tokens.

```bash
sudo journalctl --no-pager --output=json --since='7 days ago' \
  --until=now --unit=goalvision-lab-combo-settle.service _PID=1 \
  --output-fields=__REALTIME_TIMESTAMP,__MONOTONIC_TIMESTAMP,_BOOT_ID,_PID,UNIT,INVOCATION_ID,OBJECT_SYSTEMD_INVOCATION_ID,MESSAGE

sudo journalctl --no-pager --output=json \
  --since='2026-09-28 12:30:00 UTC' --until='2026-09-28 12:36:00 UTC' \
  --unit=goalvision-lab-v2-discover.service \
  --unit=goalvision-lab-combo-settle.service _PID=1 \
  --output-fields=__REALTIME_TIMESTAMP,__MONOTONIC_TIMESTAMP,_BOOT_ID,_PID,UNIT,INVOCATION_ID,OBJECT_SYSTEMD_INVOCATION_ID,MESSAGE
```

Pair starts with terminal manager records within the same boot/invocation; use
monotonic elapsed time, exclude boundary-truncated runs, report unsuccessful and
incomplete runs separately, and compute the completed-run distribution.
Then review the horizon against observed runtime, timeout/termination bounds,
and useful remaining scheduled settlement opportunities. Current protected ADMIN
disabled-state verification and stagger installation receipt remain required.

## Validation and handoff

This revision contains documentation and sanitized inspection evidence only.
JSON structure/hash and `git diff --check` are checked. No runtime test claims are
made; the 28 requested service-boundary tests remain pending implementation.
No model/history/full ML suites were run.

API calls: 0. Telegram sends: 0. Application/database writes: 0.
Production controls: 0. No installation or push. Original dirty checkout untouched.
The requested `PREMATCH_DISCOVERY_PRIORITY_GUARD_READY_FOR_OPERATOR_PREFLIGHT`
status cannot be asserted until the evidence blocker and implementation are resolved.
