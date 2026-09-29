# Settlement runtime guard v1

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

## Operator actions

Every action requires `--manifest-sha256` with the independently reviewed digest.
Use `/usr/bin/python3 -I -B control.py ACTION --manifest-sha256 DIGEST` after
external hash verification. Supported actions:

- `check`: read-only exact baseline, environment hashes, installed stagger v4,
  ADMIN sender disabled, and settlement idle/window checks.
- `install`: root-only owned guard file and settlement ExecStart drop-in,
  receipt and daemon-reload. Requires >60 seconds until actual next settlement.
- `status`: read-only pins, phase, guard ownership and content checks.
- `rollback`: verify owned artifacts, remove only owned routing, daemon-reload,
  verify original argv, then remove the unused guard file. Refuses active settlement.
- `evidence`: read-only post-install bounded journal/output report. Defaults to
  receipt installation time; optional `--since` cannot precede installation.

No action starts, stops, kills, restarts, enables, disables or rearms a service or
timer. Only install/rollback may daemon-reload. A partial transaction stays visible;
use the same package's rollback after reviewing status. Never delete the receipt
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
