# Dixon–Coles research automation — prepared 2026-10-03

The user approved preparing automatic capture/evaluation at normal priority.
This package is **not deployed** by preparation. Operator activation is separate.
No selection, champion, Official, LIVE, ADMIN or existing route changes.

## Installation

Read-only preflight:

```bash
python3 ~/goalvision-operations/dixon-coles-automation.py
```

After reviewing the package, the operator activates its separate timer:

```bash
sudo python3 ~/goalvision-operations/dixon-coles-automation.py --apply
```

Pause without deleting any research evidence:

```bash
sudo python3 ~/goalvision-operations/dixon-coles-automation.py --apply --rollback
```

The wrapper pins updater and metadata hashes. Metadata pins committed application,
the installed SINGLE 1.50 application/environment and all eight existing service
routes/commands. Existing production timers are never paused or repointed.
The normal-user preflight cannot read the root ADMIN disable files; sudo apply
checks those too. The rollback can pause research after a later production release.

## Work schedule and bounds

Separate `goalvision-dixon-coles-research.timer` runs at **:10:30 and :40:30**
Europe/Riga, after the :08/:38 observer. No boot catch-up and no retries.
A late start outside the designated 30-second slot is skipped. Any active,
failed, unknown or missing production discovery/observer/settlement/learning
service also causes a skip. Production work never waits for this job.

The worker uses nice 10, CPUQuota 25% (one-quarter of one CPU), CPU/IO weight 10,
idle I/O, 256 MiB memory and 16 tasks. The cycle deadline is 45 seconds;
systemd terminates the service at 50 seconds. This limits load; it does not
guarantee zero contention. Capacity/time limits may reduce research coverage.

Network isolation: private network namespace, AF_UNIX only, no credentials or
environment file. The filesystem is read-only except the dedicated state
directory and private temporary directory. Existing source SQLite connections
remain query-only; no football provider or Telegram calls exist in the worker.

Capture/evaluation share the already tested research CLI operations. At most
12 current fixture-family candidates per cycle, latest 500 de-vig records and
the existing source byte/time limits apply. No backdated forecasts or historical
bookmaker odds. Gaps, truncation, stale quotes, missing fits and unavailable
comparators remain explicit. A capture-input failure still attempts evaluation
of previously stored forecasts. Deadline/partial writes retain valid append-only
records and the next natural cycle is idempotent.

## State and continuity

- Immutable release: `/opt/goalvision-dixon-coles-<commit>-20261003/application`.
- Persistent database: `/var/lib/goalvision-dixon-coles/research.db`.
- Latest cycle status: `/var/lib/goalvision-dixon-coles/latest.json`.
- Per-cycle stdout/error: journal for the new service only.

First activation uses a SQLite consistent backup of the previously captured
research database from the original research worktree. All **10 existing records**
are pinned (four forecasts, four models, one plan, one pending metrics report).
They cover one genuine fixture, 1641278, and nine paired market comparisons.
Subsequent apply preserves every later record and validates the pinned seed subset.
The source database is not modified or erased. Do not continue manual captures
into the old worktree database after cutover; the persistent database becomes the
single research write destination.

Rollback disables only this timer and stops only its service. The database,
release, latest status and all past forecasts/results remain available.
Preparation or rollback never starts a manual research or production cycle.

## Evaluation and limits

The declared plan remains byte-identical, fingerprint
`ec2b5310518ad7ff5cc5182daa4cc0f86461cc1828a8bb6c0271e4e6e10e6918`.
New captures stop at **2026-10-19 00:00 UTC (03:00 Riga)**; evaluation of already
captured fixtures continues afterward. Reserved/consumed holdouts and the original
calendar windows are unchanged. Model fitting still uses the frozen pre-Oct-2
training boundary and only results known at the original quote capture.

First resolved comparisons become available after their natural result appears
in the existing settlement/canonical source, at the next eligible research slot.
The first genuine captured fixture starts Oct 3 at 21:00 Riga; late-evening review
is conditional on the provider result reaching the existing natural pipeline.
There is no promised fixed settlement time.

Inspect pending/resolved/void fixture counts, market rows, separate kickoff dates,
coverage, paired Brier/log loss and calibration. Complementary markets are
correlated and do not create independent samples. A one-fixture result is only a
pipeline check. A cross-day quality review requires accumulated evidence; the
worker always reports NEEDS_MORE_EVIDENCE and never promotes a model automatically.
The Oct 11–18 validation and Oct 19–26 sealed holdout schedule stays frozen.

Read-only operational checks after operator activation:

```bash
systemctl status goalvision-dixon-coles-research.timer --no-pager
systemctl show goalvision-dixon-coles-research.service -p Result -p ExecMainStatus
cat /var/lib/goalvision-dixon-coles/latest.json
```

Do not use `systemctl start ...service` as a test. Allow its natural timer.
A failure appears in this separate service/status file; ADMIN routes are unchanged.

SINGLE >=1.50 publishes to the existing Lab destination; COMBO legs >=1.30 keep
the separate bot/period, no combined floor. Today-only, Reply results and early
COMBO loss/remaining-leg tracking remain installed. LIVE and ADMIN Codex stay disabled.

## Preparation evidence

Source commit: `e5b02e4b35bb29720b3500d20d874ab8ad368474`.
104 offline tests passed (45 automation/installer checks), systemd verify passed.
All 831 package checksums and pinned-wrapper read-only preflight passed.
No research service/timer is installed; activation and natural-run proof remain pending.
Evidence: `docs/evidence/dixon_coles_automation_20261003/verification.json` and
`docs/evidence/dixon_coles_automation_20261003/package_preflight.json`.
