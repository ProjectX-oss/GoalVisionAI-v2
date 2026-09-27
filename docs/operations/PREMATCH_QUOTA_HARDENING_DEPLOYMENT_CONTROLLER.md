# PREMATCH quota hardening deployment controller

## Reviewed controller v2 — 2026-09-27

**PREMATCH_QUOTA_HARDENING_DEPLOYMENT_READY_FOR_OPERATOR_PREFLIGHT.**
The operator approved exactly `/opt/goalvision-prematch-quota-557d5af2-f24738b05fef`.
The new version-2 contract sets `route_relocation_approved=true` and binds new
controller bytes. The original frozen application package and the old blocked
controller bundle remain unchanged. The old controller archive
`d71856ece190455edcb10b165070f9ce334d1b3a8a03adc7a342fabdc5544722`
and contract `ef0cab20facb7579feb712aea80e6b1a22ad728d21c15de914ae3a5a826e1ddf`
are **SUPERSEDED — MUST NOT INSTALL**.

The new code/route-only preflight passes the host package, configuration, source,
timer, disk, audit, ledger and bounded shadow checks. Fresh ADMIN access is the
only remaining operator gate: `ADMIN_PRIVILEGED_CHECK_REQUIRES_OPERATOR`.
Run the new package's exact `sudo ... check` command before installation. This
session did not attempt sudo. No installation, fence, service control, manual
cycle, API call, Telegram send or production database write was performed.
The operations-only branch is committed locally and is not pushed. The unrelated
primary workspace and all application/prediction code remain untouched.

### Shadow compatibility contract

`SHADOW_COMPATIBILITY_CHECK_V1` checks the exact shadow path, regular non-symlink
file and parents, readability, nonzero page-aligned size, SQLite header and
rollback-journal header mode. Existing WAL/SHM/journal sidecars block safe opening.
It uses `mode=ro`, `query_only`, a read transaction, a 1,000 ms busy timeout,
a three-second progress deadline and a 100,000 SQLite VM-step ceiling.

The pinned `sqlite_master` DDL fingerprint checks all three required tables,
columns, primary/unique constraints, both explicit indexes and four immutability
triggers. `user_version=0` and `application_id=0` are required; newer/unknown schema
or version blocks. This repository has no numbered migration table. Its frozen
constructor DDL was reproduced in a disposable in-memory database and matches
the existing schema fingerprint exactly. The repository source is identical to
both installed lineages, verified by pinned hashes. No shadow migration is needed.

Five representative reads each use an index SEARCH and LIMIT 1: evidence primary
key, cache primary key, cache lookup index, review primary key, and early-candidate
kickoff index. Every query plan is checked before execution; a scan or temporary
sort blocks. Document prefixes are limited to 256 characters. No shadow COUNT,
full integrity, quick check, or full foreign-key scan runs. These checks establish
compatibility and bounded readability, not complete historical data correctness.

`FULL_SHADOW_INTEGRITY = NOT_COMPLETED_DUE_TO_SIZE_AND_BOUND` is informational.
The earlier full/quick scan timeouts are neither pass/fail evidence nor a claim
of corruption. Full physical integrity of the 11 GB shadow database was not established by this bounded deployment preflight.
Audit and ledger retain full integrity and foreign-key checks within their
existing 15-second bound. The shadow check is repeated while fenced.

### Fresh ADMIN gate

Every check rereads `/etc/goalvision-admin-alerts/admin-alerts.json` and opens
`/var/lib/goalvision-admin-alerts/admin.sqlite` read-only. It requires
`sender.enabled == false`, reports delivery attempts, sent outbox and pending
outbox counts, and blocks any fresh read failure. Historical counts are findings;
no zero-pending requirement exists. Pending MISSING_OUTPUT for invocation
`1149428ce2d749cb9a1335fbceb78bd9` and MONITORING_COVERAGE_DEGRADED with ledger
`UNRESOLVED_SCAN_IN_PROGRESS` remain unchanged for ADMIN v1.3. The controller
never enables the sender or edits ADMIN configuration, incidents or outbox.

## Frozen identities and incident evidence

| Input | Identity |
|---|---|
| Application source | `557d5af2c05d78404b5e86368e72ec5671dcf737` |
| Frozen manifest SHA256 | `f24738b05fef5f71f3ebcaead3c791233d94fcc38cee21e96a59f2f23493fff2` |
| Frozen archive SHA256 | `024972a084a68966c535f73fd9c4307b075b917e9d1277f88103b5e3f9d3e517` |
| Current operational lineage | `23e57e9c48f321b8ee5f67bd536fbb2b264f6cb0` |
| Current daily research lineage, verified locally | `363f567a5b9d74e4b8da152a5139d0726c64bea6` |
| Installed ADMIN lineage | v1.2, `d811177fdd11e25b087f036584d33c0e0328906b` (unchanged) |

The operator supplied privileged evidence for invocation
`1149428ce2d749cb9a1335fbceb78bd9`: 72 exact journal entries,
`sqlite3.OperationalError`, `database is locked`, main process status `1/FAILURE`,
and result `exit-code`. This closes the earlier lifecycle evidence gap.
**LOCK_HOLDER_NOT_PROVEN** remains explicit and is not a deployment gate.

The historical MISSING_OUTPUT and recurring MONITORING_COVERAGE_DEGRADED / ledger /
UNRESOLVED_SCAN_IN_PROGRESS incidents are outside this deployment. Scanner pagination
and lifecycle work belongs to ADMIN v1.3. The controller neither correlates nor
invalidates, deletes, acknowledges or sends those incidents. The separately packaged
ADMIN mapping patch is verified as frozen package content and never applied.

## Files and handoff

- `operations/quota-deployment/controller.py`: standard-library CLI, no application imports.
- `host-contract.json`: fixed before routes, reviewed source hashes, configuration hashes,
  loaded command/static properties, timer states/schedules and database schema fingerprints.
- `controller-checksums.json`: controller and contract checksums. The contract also pins
  the controller bytes, so the operator's contract SHA binds both code and expectations.
- `test_controller.py`: fake systemd and disposable filesystem/SQLite tests.
- `host-rehearsal.json`: read-only host findings and accepted operator evidence.
- `OPERATIONS_COMMANDS.md`: exact one-line check/install/status/rollback/recovery commands.
- `build_bundle.py`: deterministic local review bundler; no production mutation.

Standalone review bundle:
`/home/arvis/goalvision-operations/prematch-quota-deployment-controller-package-v2-r1-20260927`.
The v2 operations manifest includes the exact prefix derivation and base64 resulting
bytes/hashes for all five routes and both environment files. It includes the
controller, fixed contract, tests/evidence, full frozen package and
original frozen archive. `operations-manifest.json` pins every payload;
`SHA256SUMS` additionally covers that manifest. The tar.gz hash is supplied in the
handoff. The bundle needs Python's standard library, local systemd/git and operator
read privileges. It does not import from this repository or install dependencies.
The operator must verify the archive hash from the handoff before extraction, then
run `sha256sum --check --quiet SHA256SUMS` inside the extracted bundle.

## Exactly five routes

| Service | Before | Proposed immutable payload |
|---|---|---|
| goalvision-lab-v2-discover.service | 23e57e9 | application |
| goalvision-lab-combo-settle.service | 23e57e9 | application |
| goalvision-adaptive-learning-observer.service | 23e57e9 | application |
| goalvision-lab-weekly-stats.service | 23e57e9 | application |
| goalvision-adaptive-learning.service | 363f567 | research |

Both complete trees are staged under the fixed `/opt` release directory in separate
`application` and `research` subdirectories. Research retains its distinct lineage
with the frozen five-file persistence overlay. Existing releases are never edited.
A pre-existing destination must exactly match payload, ownership and read-only modes.
An interrupted unused staging directory can remain as evidence; it is never selected
as a route or reused as a writable production code tree.

Frozen environment files are copied with only the exact frozen package prefix
replaced by the approved immutable release prefix. Every other byte is preserved. New files are `release.env` and `research.env` inside the immutable release.
Systemd's five commands, working directory and environment properties remain pinned.
The existing runtime `.env` is checked by hash without printing its values. This keeps
publication/new picks, context observation, selection labels, Telegram destinations,
API references, max-calls=400, settlement-reserve=100 and all other settings unchanged.
The existing virtualenv and working directory stay pinned; Python `-P` and the
relocated PYTHONPATH select only sealed `/opt` application/research code.
Root owns staged files/directories; their modes are 0444/0555; `/opt` parents must be
root-owned and not writable by other users. No virtualenv or dependency is modified.

## Preflight and read-only commands

`check` performs no mkdir, journal write, lock creation, reload or service invocation.
It verifies the manifest pin, exact payload file set, file hashes, symlink rejection,
archive hash when present, static unit/drop-in/environment/runtime configuration,
loaded ExecStart/EnvironmentFiles/DropInPaths, source identities and source hashes.
All applicable pinned systemd drop-in directories are compared, including inherited
prefix/type directories. Runtime bytecode files in existing releases are excluded
from the source comparison; staged releases admit no extra files.

It checks host-wide loaded service/timer NeedDaemonReload, five timer states/schedules,
ADMIN sender and delivery counts, bounded shadow compatibility, audit/ledger integrity, and disk
headroom for staged code and recovery evidence. No expected value is learned or
refreshed by a command. A mismatch returns BLOCKED with a fixed diagnostic.

SQLite uses `mode=ro`, `query_only`, a read transaction, one-second busy timeout and
bounded query progress. WAL/shared-memory/journal sidecars and non-DELETE journal
headers require review, avoiding read-triggered recovery or sidecar creation. The
controller never opens a live SQLite file for writing, imports migrations, copies,
backs up, restores, replaces or deletes a database. Missing or changed schemas block.
Audit and ledger full integrity checks run before fencing. After drain, only schema/readability checks
are repeated alongside all route/source/configuration checks, to keep the fenced
interval short. The already completed integrity result is identified explicitly.

`status` triggers no work. It exposes routes/preflight results, timers, service results
and invocation/start/exit timestamps, latest discovery health/provider calls/published
count, ledger delivery counts/latest receipt or claim, ADMIN state and database checks.
Contention codes are counted only in the last 2,000 visible discovery journal entries;
missing coverage is not interpreted as zero contention. Timer trigger timestamps and
health timestamps are supplied for scheduled-cycle correlation. The existing evidence
does not persist an exact timer-to-health join, so the controller does not invent one
or claim full production validation automatically.

## Fence, drain and transaction

Future explicitly confirmed install/rollback commands first run read-only preflight.
They secure a root-owned copy of the controller, contract and frozen package for
recovery, then launch only a transient **controller** service through `systemd-run`.
The production five services are never manually started. The controller service has
an `ExecStopPost` recovery command using the same pinned code and confirmation.

The worker:

1. Takes `/run/lock/goalvision-prematch-v2-installer.lock` with nonblocking flock.
   This is the existing installer coordination lock, shared across releases and
   actions. The inode is never unlinked. All checks are repeated under this lock.
2. Stages, hashes, fsyncs and seals both releases before beginning interruption.
3. Durably journals the origin/target state and exact origin route bytes (base64),
   plus before hashes, under `/var/lib/goalvision-quota-deployment/transaction.json`.
4. Creates the durable `blocked` marker and exactly five temporary drop-ins:
   `/etc/systemd/system/SERVICE.d/91-quota-deployment-fence.conf` containing:

   ```ini
   [Unit]
   ConditionPathExists=!/var/lib/goalvision-quota-deployment/blocked
   ```

5. Reloads systemd to activate this fence. Existing running oneshots are unaffected;
   new starts fail the condition while the marker exists. Timer schedules and
   active/enabled states stay unchanged. A timer tick skipped during fencing is not
   replayed manually; the next ordinary scheduled tick is used.
6. Waits for all five to become inactive/failed, with zero MainPID/ControlPID and
   no pending Job. Each systemctl command has at most five seconds; drain calls use
   the remaining budget. Both drain checks share one 60-second deadline. Timeout
   restores the unfenced original state before any route replacement. No worker
   receives SIGTERM/SIGKILL, stop, restart, disable or mask commands.
7. Revalidates all expectations while fenced, then atomically replaces exactly five
   route files using fsynced temporary files and same-directory rename. It performs
   one bounded reload for the complete route change, verifies loaded routes and
   unchanged timers, and checks ADMIN again.
8. Durably records COMMITTED. Only after the homogeneous loaded state is proven is
   the marker removed. The now-true conditions cannot block subsequent starts. Gate
   files are removed and a final reload drops their configuration. Three reloads
   occur on a clean transaction: fence activation, route activation, fence cleanup.

The success return is **INSTALLED_WAITING_FOR_SCHEDULED_EVIDENCE**. No new cycle is
started. Hardening is not called production-validated until a normal later scheduled
cycle supplies evidence reviewed by the operator.

## Crash recovery and rollback

`ExecStopPost` runs independently after controller success/failure, including a killed
controller process. RuntimeMaxSec bounds only this controller service; it does not
stop a production worker. Recovery re-acquires the shared deployment lock and reads
the durable journal. The normal worker also attempts recovery on caught failures.

- PREPARED/FENCED: no route replacement was authorized. Verify the origin state and
  remove the fence without waiting another 60 seconds on an already timed-out worker.
- CHANGING: establish/verify the fence, drain, restore exact origin bytes, reload,
  verify homogeneous routes/timers, commit the recovered decision, then unfence.
- COMMITTED: finish cleanup on the target state. Never restore origin after the
  marker could already have allowed a scheduled target worker to start.
- DONE: recovery is a no-op. Install and rollback replays in the wrong route state
  are rejected before fencing.

The research route's absent-before state is explicit. Removal is permitted only for
exact proposed **operations-package** bytes. A changed/foreign file is retained and
recovery fails closed. Four prior route files are restored byte-for-byte. Restoring
those files also restores the previous environment references; original environment
files were never modified. Any subsequent capability/configuration change blocks
rollback rather than silently toggling publication.

If route restoration/reload/verification cannot be proven, the persistent marker and
five gate files remain, and the controller prints the journal phase, origin/target,
marker and surviving gate files. It does not allow mixed route execution. Recovery
does not restore any audit/ledger/shadow DB, quota claim, publication, settlement or
statistic; new evidence survives both successful and failed rollback.

The gate files and marker deliberately survive reboot. The transient supervisor does
not survive reboot. After a host/power failure during the transaction, the exact
`rollback --recover` command in OPERATIONS_COMMANDS.md resumes the recorded decision.
This is an explicit fail-closed recovery state; never delete the marker by hand or
manually start a job to test it. A single controller-process failure is handled by
ExecStopPost; failure of recovery or host reboot requires the operator.

Systemd semantics were checked against the installed systemd.service(5) and
systemd.unit(5) manuals. See the upstream descriptions of
[ExecStopPost](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
and [unit conditions](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html).
No real fence/reload rehearsal was authorized or performed; fake systemd tests model
these transitions. An isolated real-systemd integration rehearsal remains useful
before approving production operation.

## Validation and host rehearsal

**59 controller test methods passed**, including all previous parameterized fault
boundaries and new relocation, sealing/reuse, shadow and ADMIN cases. Tests use
fake systemd and disposable databases. The prior frozen package evidence records
64 directly relevant quota/database/package regressions; those application tests
were not rerun for this operations-only change. No giant historical/model suite or ADMIN suite was rerun. No prediction
logic changed, so the frozen package's prior algorithm/backtest evidence remains
applicable; this work tests only operations and directly relevant regressions.

Controller coverage includes read-only checks/status; manifest/payload/extra-file/
symlink tamper; route, ADMIN sender/readback, loaded-reload, drop-in, capability,
timer and schema drift; disk space; active drain and exact 60-second timeout;
all five fence and route failure boundaries; independently resumed crash recovery;
all five rollback failure boundaries; exact rollback/research absence; reload failure
at activation and cleanup; loaded mismatch; immutable releases; byte/inode/mtime DB
preservation; installed replay and rollback replay; lock contention; unresolved mixed
state fencing; post-commit crash handling; and controller-code/contract identity binding.

The final read-only host CHECK completed in 1.3747 seconds, reaching only the
ADMIN privilege gate. `host-rehearsal.json` records its fresh findings and shadow
elapsed time. The rehearsal command boundary permits only systemctl show/list-units
and git rev-parse. The evidence records:

- Frozen package and all 1,695 payload files match; available archive matches its pin.
- Five routes, five timer states/schedules, capability settings and 1,679 current
  application/research source-file hashes match their reviewed baselines.
- Host-wide loaded service/timer NeedDaemonReload check passes.
- Audit and ledger schema, full integrity and foreign-key checks pass.
- Shadow compatibility passes in milliseconds without a full-file scan; full physical integrity remains unestablished.
- Fresh ADMIN local readback requires the operator; protected config/DB remain unchanged.
- Production configuration and source bytes still match after the rehearsal.
- API calls 0; Telegram sends 0; production DB writes 0; production service-control
  operations 0; deployments 0; Official/LIVE/ADMIN changes 0.
