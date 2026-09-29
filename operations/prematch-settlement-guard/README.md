# Settlement runtime guard v1 — interrupted-install recovery

Operator preparation package. Approved horizon: **180 seconds**.
See `docs/operations/PREMATCH_DISCOVERY_PRIORITY_SETTLEMENT_GUARD.md` in the
source checkout for the trusted package hashes and complete operator commands.

The wrapper uses only the standard library and read-only local systemd queries.
The two observation rounds check discovery state and the actual numeric
`NextElapseUSecRealtime` D-Bus property. Active discovery defers immediately;
unknown/failed/inconsistent state defers closed; <=180 seconds defers as imminent.
No sleep, retry, application import, API request, Telegram send or database access
occurs on deferral. One sanitized JSON record goes to existing journal stderr.

Successful authorization records `SETTLEMENT_EXECUTED`, then uses `os.execv` with
the exact pinned application argv and inherited environment. An exec error returns
126; evidence requires successful manager completion before counting execution.
There is no atomic interlock with discovery: discovery may change after the final
observation, and settlement can exceed the approved horizon. No timeout is changed.


## Recovery from the verified interrupted installation

This package adds `recovery-preflight` (read-only) and `recover-installing`
(explicit receipt finalization). Use the **new** externally verified SHA256SUMS
hash for every action; do not pass the predecessor digest as the new package hash.
Exact commands and trusted hashes are in the source checkout's
`docs/operations/PREMATCH_SETTLEMENT_GUARD_RECOVERY.md`.

The only recoverable predecessor manifest is
`c50abe7fc9f7f44a3c05d12fbc81fb41cf53be847d17a09b5f316f0ac85bcfb5`,
with phase exactly `installing`, the original pinned application argv, and no
existing completion/recovery fields. Recovery requires these exact installed hashes:

- Drop-in: `c78ae7eb2347d049d2b9c763d4f77316b91a566de1eaa9f642c6754db6e36d51`.
- Runtime: `4ab82ae534403e2a3d8f7e1b589220b555b8f3cfac63bb7c878337eea53ea5ff`.

Recovery checks the unchanged predecessor baseline, the complete production
inspection with no partial-install exemptions, root ownership/modes, loaded
wrapper executable and argv, `NeedDaemonReload=no`, settlement `inactive/dead`,
all five timers `active/waiting`, ADMIN sender disabled, and the exact installed
stagger-v4 receipt. It checks the loaded state again after inspection and refuses
if the receipt changed. Every finalization reruns preflight under the existing
exclusive transaction lock. The read-only preflight creates no lock or files.

Only `After`, `Before`, `Requires`, `Wants`, `OnFailure`, and `OnSuccess` use
`set(actual.split()) == set(expected.split())`: token order, whitespace, and
repeated identical members are immaterial. Added, missing, changed, or substring
members fail. Missing properties fail even when the pinned set is empty.
All other comparisons retain their exact previous semantics.

Finalization atomically writes the receipt and uses the existing lock; it performs
no daemon-reload, worker/timer control, API request, Telegram send, or business DB
access. No runtime or drop-in is rewritten. `manifest` and `original_argv` remain
unchanged. `recovery` records the new package manifest, method schema, UTC time,
complete original receipt text, and its SHA256. `installed_at` is the recovery
time, so normal evidence cannot claim unverified cycles before finalization.
Normal status displays the original manifest and recovery provenance.

Keep this recovery package for `status`, `evidence`, and future `rollback` using
its new manifest hash. Those actions validate the explicit predecessor linkage.
Rollback retains provenance, restores the exact original application argv through
the existing pinned unit/drop-ins, and remains retryable after reload failure.
Re-running recovery after completion fails; use `status`. Reinstalling a recovered
transaction is refused to preserve its history. An old package cannot understand
the new provenance and still has the ordering bug.

State reads are observations, not an interlock with naturally scheduled workers.
Recovery changes only metadata, so a later natural activation is not controlled.
A state-check refusal requires another operator preflight during normal idle time.
Existing `evidence/validation.json` describes the original package rehearsal;
`evidence/recovery-validation.json` records this recovery package's offline tests.

## Operator actions

Every action requires `--manifest-sha256` with the independently reviewed digest.
Use `/usr/bin/python3 -I -B control.py ACTION --manifest-sha256 DIGEST` after
external hash verification. Supported actions:

- `check`: read-only exact baseline, environment hashes, installed stagger v4,
  ADMIN sender disabled, and settlement idle/window checks.
- `install`: root-only owned guard file and settlement ExecStart drop-in,
  receipt and daemon-reload. Requires >60 seconds until actual next settlement.
- `status`: read-only pins, phase, guard ownership, content and recovery linkage checks.
- `rollback`: verify owned artifacts, remove only owned routing, daemon-reload,
  verify original argv, then remove the unused guard file. Refuses active settlement.
- `evidence`: read-only post-install bounded journal/output report. Defaults to
  receipt installation time; optional `--since` cannot precede installation.

No action starts, stops, kills, restarts, enables, disables or rearms a service or
timer. Only install/rollback may daemon-reload. A partial transaction stays visible;
use this package's explicit recovery for the known predecessor incident, or the
matching package's rollback for other partial transactions after review. Never delete the receipt
or hand-edit a tampered artifact to bypass refusal. No automatic rollback runs.

Production routing is limited to:
`/etc/systemd/system/goalvision-lab-combo-settle.service.d/99-goalvision-settlement-guard.conf`.
Runtime file: `/opt/goalvision-settlement-guard-v1/runtime_guard.py` (root, 0444).
Receipt: `/var/lib/goalvision-prematch-settlement-guard/transaction.json`.
The service retains its user, environment, working directory, output routes,
sandbox, timeout and exact application argv. Timers remain stagger v4.

Forward PASS needs at least 2 completed scheduled discovery, 3 successfully
executed scheduled settlement, and 2 completed scheduled observer cycles.
ACTIVE/IMMINENT are informational and do not count as settlement execution.
STATE_UNAVAILABLE, exhaustion, database locks, service failures, failed discovery,
missing/invalid/duplicate guard records, or missing required evidence prevent PASS.
Calendar alignment alone does not establish timer causation: operator review of
normal scheduling and absence of manual activations is still required.

`vendor/` contains byte-identical copies of the reviewed stagger evidence/calendar
helpers. The installed stagger package and source files are not modified.
`guard_evidence.py` adds guarded invocation accounting without application imports.
`evidence/read-only-inspection.json` is the preserved earlier blocked inspection;
`approved-runtime-evidence.json` supersedes its missing runtime statistics.
`schedule_proof.py` regenerates the full per-tick current/DST horizon proof using
the host systemd and tzdata. No application or model backtest is relevant to this
service-boundary change; the historical overlap is projected offline.
