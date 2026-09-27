# PREMATCH systemd timer stagger hardening

## Readiness and supersession

**PREMATCH_TIMER_STAGGER_HARDENING_READY_FOR_OPERATOR_PREFLIGHT**

Daily adaptive research now uses **04:20 host time**, between settlement at
04:15 and 04:25. All five timers participate in collision checking. Systemd with
installed tzdata proves zero exact collisions for all ten pairs in the current
48-hour window and both 2026 DST transition windows. All 36 operations tests pass.
Production installation and forward validation have not been performed.

**Commit `46e680851fd8c64c5d003c14215de75128537542` and its v2 package are
SUPERSEDED / MUST NOT INSTALL.** The obsolete v2 manifest SHA-256 is
`34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472`;
its archive SHA-256 is
`226b0494d8c08b72210c12500017fa75ee7368dc1c549482a873289e42d6d0bb`.
The original `b286210` release also remains superseded. `SUPERSEDES.json`
records both. The immutable old package/archive bytes are retained for audit;
a `prematch-timer-stagger-v2-20260927.SUPERSEDED_DO_NOT_INSTALL.json` sidecar
marks the local v2 artifacts. Use only the v3 paths and hashes below.

The superseded research schedule has two settlement collisions per evaluated
48-hour window. The regression runs the real systemd evaluator and proves the
controller rejects it before acquiring its deployment lock, creating transaction
state, writing drop-ins or issuing any systemd control call.
This status means ready for the root operator's read-only preflight, including
protected ADMIN state verification.

No production installation, timer re-arm, daemon reload, manual PREMATCH cycle,
worker control, API-Football request, Telegram send, application change, or ADMIN
mutation was performed. The corrected commit has not been pushed.

The supplied production incident counts establish recurring contention and
simultaneous scheduling. They do not identify the historical lock holder. This
change addresses exact scheduled timestamps; worker durations can still overlap.

## Exact schedules

| Timer | Exact original file value | Requested target file value |
|---|---|---|
| `goalvision-lab-v2-discover.timer` | `*-*-* 09..22:00,30:00 Europe/Riga` | unchanged |
| `goalvision-lab-combo-settle.timer` | `*:0/10` | `*-*-* *:05,15,25,35,45,55:00` |
| `goalvision-adaptive-learning-observer.timer` | `*:0/30` | `*-*-* *:08,38:00` |
| `goalvision-lab-weekly-stats.timer` | `Sun *-*-* 22:30:00 Europe/Riga` | `Sun *-*-* 22:48:00 Europe/Riga` |
| `goalvision-adaptive-learning.timer` | `*-*-* 04:15:00` | `*-*-* 04:20:00` |

Systemd normalizes the old settlement and observer expressions to
`*-*-* *:00/10:00` and `*-*-* *:00/30:00`. The host timezone is Europe/Berlin;
zone-less expressions deliberately retain that existing timezone. Discovery and
weekly stats explicitly retain Europe/Riga. No fixed UTC offset is assumed.
Research moves five minutes later because its shared adaptive_lab audit database
would otherwise face a deterministic settlement/research collision every day.

Exactly four files are intended to be added, each under `/etc/systemd/system/`:

- `goalvision-lab-combo-settle.timer.d/95-goalvision-prematch-timer-stagger.conf`
- `goalvision-adaptive-learning-observer.timer.d/95-goalvision-prematch-timer-stagger.conf`
- `goalvision-lab-weekly-stats.timer.d/95-goalvision-prematch-timer-stagger.conf`
- `goalvision-adaptive-learning.timer.d/95-goalvision-prematch-timer-stagger.conf`

Each resets the inherited `OnCalendar=` list and adds one target expression.
No other directive changes. Existing `Persistent`, accuracy, randomization,
service associations, enabled state and inactive/active timer state are preserved.
No discovery drop-in is created. The baseline pins the four-timer allowlist and
all five target calendars; original source hashes/calendars remain rollback pins.

## Exact calendar proof

`systemd-analyze calendar` evaluates triggers using systemd 255
(255.4-1ubuntu8.17) and installed tzdata 2026c. The proof records zoneinfo hashes,
all original and target UTC triggers, counts, pair intersections, cadence and
research separation. Enumeration must extend beyond the end of each window.
Windows are half-open and exactly 48 elapsed hours. The current window begins
at the current UTC hour; operator preflight regenerates it at execution time.

| Window start (UTC) | Discovery | Settlement | Observer | Weekly | Research | Collisions across ten pairs |
|---|---:|---:|---:|---:|---:|---:|
| 2026-09-27T18:00:00+00:00 (current_48_hours) | 56 | 288 | 96 | 1 | 2 | 0 |
| 2026-03-28T00:00:00+00:00 (spring_dst) | 56 | 288 | 96 | 1 | 2 | 0 |
| 2026-10-24T00:00:00+00:00 (autumn_dst) | 56 | 282 | 94 | 1 | 2 | 0 |

| Timer pair | Current | Spring DST | Autumn DST |
|---|---:|---:|---:|
| Discovery / Settlement | 0 | 0 | 0 |
| Discovery / Observer | 0 | 0 | 0 |
| Discovery / Weekly | 0 | 0 | 0 |
| Discovery / Research | 0 | 0 | 0 |
| Settlement / Observer | 0 | 0 | 0 |
| Settlement / Weekly | 0 | 0 | 0 |
| Settlement / Research | 0 | 0 | 0 |
| Observer / Weekly | 0 | 0 | 0 |
| Observer / Research | 0 | 0 | 0 |
| Weekly / Research | 0 | 0 | 0 |

All six research occurrences have exactly 300 seconds from the previous
settlement and 300 seconds to the next: **04:15 → 04:20 → 04:25** host time.
Research stays daily, and each evaluated trigger moves exactly 300 seconds from
the original. Its elapsed intervals remain 86,400 seconds normally, 82,800 at
spring DST and 90,000 at autumn DST. Discovery triggers remain identical.
Weekly cadence is compared across three consecutive systemd-evaluated events
around every window, including DST, and remains unchanged.

Settlement spacing is normally 600 seconds; observer spacing is 1,800 seconds.
This systemd evaluator skips the repeated local hour in autumn, producing one
4,200-second settlement gap and one 5,400-second observer gap. Original and target
calendars have identical counts and gap sets. Existing DST behavior is preserved.
Weekly stats is 19:48 UTC on September 27 and March 29, and 20:48 UTC on October 25.
The superseded-v2 proof contains two exact 04:15 settlement/research collisions
in each window and `zero_collisions: false`.

Timer accuracy remains 1 minute for the frequent timers and 1 second for weekly
stats; random delay remains zero. Exact timestamp separation does not prove that
long-running workers cannot contend. Persistent catch-up after downtime can also
coincide. These settings and application locking are outside this change.
The installed systemd timer manual documents accuracy and persistent catch-up
behavior (`man systemd.timer`).

## Pinning and read-only preflight

`baseline.json` pins the 12 PREMATCH/ADMIN timer and service units and all 17
fragment/drop-in source hashes, captured at 2026-09-27T18:25:15.954432+00:00.
It also pins the host timezone and `/etc/localtime` content hash. The file hashes
are listed below. Read-only inspection repeated for v3 passed all 12 units, 17 hashes,
loaded calendars and `NeedDaemonReload=no` checks.

Full preflight requires a root operator because the ADMIN configuration and
state directory are protected. Passwordless sudo is unavailable in this session.
**ADMIN sender state has not been verified here.** The preflight would inspect
its configured enabled flag, fence, existing notification epoch, configuration
hash, unit state, and a stable database byte snapshot under the existing read-only
scan-lock handle. SQLite receives only an in-memory copy. WAL/journal sidecars,
unknown sender state or inconsistent enabled/fenced/epoch state fail closed.
No ADMIN token is read and no transport is contacted. This verifies local state,
not Telegram delivery health. The calendar proof now passes; the protected ADMIN
read remains part of the operator preflight.

Check/status/proof/evidence do not create transaction files or change configuration.
All actions verify the package manifest. Check rejects source hashes, extra
loaded/unloaded drop-ins, missing units, changed calendars, timezone drift,
`NeedDaemonReload` drift and unsafe timer dependency propagation. Loaded unit
checks cover the 12 pinned units; concurrent systemd configuration work must not
be performed during the operator transaction.

## Install, rollback and interrupted operation

The following describes future operator execution after a successful preflight.
It was not executed while preparing this package:

1. Acquire an exclusive package operation lock under
   `/var/lib/goalvision-prematch-timer-stagger`; no ADMIN lock/state is written.
2. Verify package, baseline, calendars, ADMIN state and timer state. Reject a
   persistent catch-up risk or a trigger boundary before changing configuration.
3. Record a durable transaction before adding any drop-in. Write each exact
   drop-in through a same-directory temporary file, fsync and atomic rename.
4. Recheck persistent re-arm safety, reload the manager because the timer
   configuration changed, and restart only the previously active changed timers.
   Inactive timers remain inactive; enable/disable is never called.
5. Verify loaded schedules, states, hashes and each changed timer's actual
   `NextElapseUSecRealtime` against systemd calendar evaluation. If a normal
   worker is running, wait for its timer to arm, without stopping the worker.
   Record installation completion and unchanged ADMIN configuration/epoch state.

`Persistent=true` and the existing catch-up guard are retained. **Operator
installation constraint:** under normal punctual operation, daily research can
pass the target guard only after its old 04:15 tick and before 04:20 host time.
Weekly stats can pass only after its old Sunday 22:30 tick and before 22:48 Riga.
These windows do not intersect. Thus the current all-at-once installer will
refuse normal installation with `PERSISTENT_CATCHUP_RISK_RETRY_AFTER_NORMAL_RUN`.
Simply retrying the documented command at another time does not resolve this
constraint. The scheduling/collision correction is ready for operator preflight;
production deployment needs a separately reviewed catch-up-safe procedure before
installation can proceed. No guard was relaxed, timestamp file edited or worker
launched to make installation pass. The operations tests exercise transaction
mechanics with `safe_rearm` mocked and separately test catch-up refusal; they do
not establish that these four live timers can be safely re-armed together.

Catchable installation failures attempt restoration. Rollback verifies exact
ownership, removes only the four exact package drop-ins, reloads for those
configuration changes, re-arms only originally active timers and verifies the
original calendars. It leaves the original fragments, foreign files, application,
databases and evidence untouched. The controller has no service stop/restart/kill
operation. Active workers may finish normally during either operation.

Recovery intent is fsynced before removal; a crash after unlink and before reload
is recoverable. On SIGKILL, power loss or reboot no Python process can perform
immediate recovery. The next `rollback` (or `install` detecting an incomplete
transaction) restores the original scheduling and returns; a separate fresh
check/install is then required. Until recovery, a partial set of staggered timers
may remain. No boot recovery service is added, because this is a timer-only
package. Re-arm/rollback waits are bounded to 15 minutes, in two-second polls.
If systemd remains unavailable, source/ownership drift appears, or no safe re-arm
window arrives, the transaction remains pending for operator recovery; success
is never reported. Do not delete its transaction metadata.

## Operations tests

36 operations tests passed. No model, history or full application suite ran.
Fixtures use temporary unit/state directories and a fake systemd control boundary.
Real `systemd-analyze` handles calendar evaluation only. Transaction tests isolate
the collision gate to exercise mechanics. Separate acceptance tests evaluate the
final schedules and all ten pairwise intersections, while a negative regression
proves that the superseded 22:45 weekly target is still rejected. A second real
calendar regression proves the 04:15 research collision and refusal before writes.

| Requested coverage | Verification |
|---|---|
| Exact targets, cadence, no collisions | Exact final payloads; 48-hour/DST evaluation; all ten pairs pass; superseded 22:45 weekly and 04:15 research are rejected |
| Discovery unchanged; research shifted five minutes | Original hashes, identical discovery triggers, daily research at 04:20 and 300-second settlement gaps |
| Only intended timer changes | Exactly four owned drop-ins; all original unit hashes preserved |
| No worker stop/restart/kill | Structural mutation allowlist and negative boundary tests |
| Only timer re-arm | Recorded fake commands; inactive timers never restarted |
| Exact rollback | Original loaded calendars and unchanged source hashes |
| Reload only around configuration changes | Install/remove command sequence; idempotent rollback performs no reload |
| Tamper/drift rejection | Manifest/payload changes, symlinks, foreign drop-ins, source hash and reload drift |
| Interrupted install | After each atomic drop-in and after unlink/before reload; next command restores |
| No API/Telegram/database writes | Network-guarded fixtures; live SQLite never opened by SQLite; only memory snapshot |
| No ADMIN mutation | Synthetic ADMIN files' bytes and mtimes unchanged |
| Forward evidence | Minimum cycles, transient retries, exhausted/lock/exit failures, incomplete journals and service-specific output contracts |

Re-run from the worktree:

```bash
python3 -B -m unittest discover -s tests/operations -v
```

## Trusted package hashes and commands

The trusted SHA256SUMS digest and exact one-line commands are appended below.
Keep the reviewed package under controlled ownership while running it. Each
command validates the trusted manifest digest and every file before executing
Python, which repeats the manifest and inventory checks. This prevents a changed
manifest from blessing changed package content. Hashes provide integrity against
the reviewed digest; they are not a signature from a separate authority.

The install command is supplied for later operator use after preflight.
No command below was used to install or roll back production.

## Forward validation after a future successful install

Run the `evidence` command below after normal scheduled cycles. It defaults to
the durable successful installation timestamp; it does not launch any worker.
Allow at least two discovery, three settlement and two observer completions.
An overnight installation may need to wait until discovery's next daytime window.
Re-run the same read-only command if it reports `WAIT_OR_INCOMPLETE_EVIDENCE`.
The bounded report supports up to seven elapsed days since installation.

The report includes per-service and per-invocation counts for
`QUOTA_DB_CONTENTION_RETRY`, `QUOTA_DB_CONTENTION_EXHAUSTED`, `SERVICE_FAILURE`,
`DATABASE_LOCK`, and `MISSING_OUTPUT`, invocation IDs, calendar timestamps,
actual systemd service-start timestamps, completion timestamps and exit status.
These are journal/file evidence counts, not historical ADMIN incident counts.
No monitor scan is invoked and no ADMIN cursor is advanced.

- Success requires the minimum completed, calendar-aligned invocations;
  exhausted contention and database locks must be zero and every exit status zero.
  Missing starts, required output, invocation identity or completion prevent PASS.
- Transient retries alone are reported and do not fail successful invocations.
- Actual service activations come from systemd's `Starting` journal record.
  They are matched to expected ticks within the existing 60-second accuracy
  window plus five seconds. Alignment does not independently prove which client
  requested a start. No manual cycle is authorized during validation.
- Discovery's append-only compact stdout file has no invocation ID: its expected
  schema is associated by the run's time window and labelled accordingly.
  Rotated uncompressed files are read; compressed/oversized/unavailable evidence
  fails closed for operator review. No file is changed.
- Settlement has `StandardOutput=null`; expected final stdout is unobservable.
  Its `MISSING_OUTPUT` field counts only explicit/missing-start evidence and is
  labelled `NOT_ASSESSABLE_STDOUT_NULL`. The report does not invent missing output
  for this route. Exit/lock evidence remains required.
- Observer must emit its structured PREMATCH final document with exact journal
  invocation attribution. Arbitrary stderr does not satisfy the output contract.

Production success is **not yet measured**: this package has not been installed.

### Versioned package v3

- Extracted package: `/home/arvis/goalvision-operations/prematch-timer-stagger-v3-20260927`
- Archive: `/home/arvis/goalvision-operations/prematch-timer-stagger-v3-20260927.tar.gz`
- Archive SHA-256: `ade13cb7dc820fc22105188cae042960f0954f1f0b1723a980d3ae9584d301de`
- Manifest (`SHA256SUMS`) SHA-256: `0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d`

The archive contains only the standalone operations package. Source, archive and
frozen package bytes match exactly. Archive metadata and gzip mtime are fixed;
rebuilding the same payload produces identical bytes. The archive and extracted
package are read-only. Full protected ADMIN preflight and production forward
validation remain pending. The persistent catch-up constraint above must be
resolved before installation; these commands do not bypass it.

| Package file | SHA-256 |
|---|---|
| `README.md` | `460f2a0265bb5f7180b3e3b4c78d93f3b08942e1654aa091c509df769aaf7b67` |
| `SUPERSEDES.json` | `f867b200594432fa3ccd1b02f692395c0af479aff9f5df0d74a309698e000927` |
| `baseline.json` | `1efd2bf259f7bf29e8fee009fc313de2846014420eb1413c6511f7955660cd6c` |
| `calendar_proof.py` | `8fe1f27ca3487ef98a9e15a2ecb50cc5e17fdb9362e29d8aa87f23a11526a1b0` |
| `control.py` | `7b518744dfe6212ff1f76dbb5568747afab7e0eafa377eef2e2889d62ed40a58` |
| `drop-ins/goalvision-adaptive-learning-observer.timer.conf` | `0ddbd492381bd624ab9cc2fd08cc1e7839e6e20bc2c86f80cc3f1736ec0f2f58` |
| `drop-ins/goalvision-adaptive-learning.timer.conf` | `24fb39120d5455b817b40698702ecaf9439e63b9bddcbfd89f3830c2a01e5eb1` |
| `drop-ins/goalvision-lab-combo-settle.timer.conf` | `29eb3bdcab1115c4457a897633cd487ca55207a09a620aa8a530b624342a48c0` |
| `drop-ins/goalvision-lab-weekly-stats.timer.conf` | `6b64433a79d412ae4f6dfca9d3e791fbbbba1ade4e68e75a2248a5ae17549092` |
| `evidence/calendar-proof.json` | `0f3f427afbf01ccfc01f493602a0f120fb8f7377b25f22830f2e911e79598609` |
| `evidence/operations-tests.txt` | `c25c1a6abfd4f04b98a0cf81471d4b870f6d17ee8fcec8a22695f3a270923a02` |
| `evidence/read-only-host-inspection.json` | `df02959302780181d07c2171d32e0f4fe334a4604bb351054d62c5c6b0efcbd8` |
| `evidence/superseded-v2-collision-proof.json` | `83b01c317c1a2ece435a3d9cde106325410d6aa39d27c135ef4bf1102aaaa26b` |
| `forward_evidence.py` | `9a84af3e3fa80f2aa6033561b36d51a93261655d5379eb801e002e68a9d797c5` |

### Exact operator commands

Archive verification:

```bash
cd /home/arvis/goalvision-operations && echo "ade13cb7dc820fc22105188cae042960f0954f1f0b1723a980d3ae9584d301de  prematch-timer-stagger-v3-20260927.tar.gz" | /usr/bin/sha256sum --check --strict -
```

Check:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v3-20260927 && echo "0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py check --manifest-sha256 0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d'
```

Install (future operator use; see catch-up constraint):

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v3-20260927 && echo "0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py install --manifest-sha256 0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d'
```

Status:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v3-20260927 && echo "0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py status --manifest-sha256 0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d'
```

Rollback:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v3-20260927 && echo "0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py rollback --manifest-sha256 0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d'
```

Evidence:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v3-20260927 && echo "0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py evidence --manifest-sha256 0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d'
```

Proof:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v3-20260927 && echo "0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py proof --manifest-sha256 0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d'
```


### Pinned live unit and drop-in hashes

| Original source file | SHA-256 |
|---|---|
| `/etc/systemd/system/goalvision-adaptive-learning-observer.service` | `a628c35482ebab376b82f348feffa6b2e8f542ca522c9fa57704525dd83a2393` |
| `/etc/systemd/system/goalvision-adaptive-learning-observer.service.d/90-reviewed-prematch-v2.conf` | `8ecdfedd8ee5839e2ff1adf2ca2d6943bfea59f5e456c75d989b336661b331a1` |
| `/etc/systemd/system/goalvision-adaptive-learning-observer.timer` | `72daf0281538ab3570b3081dac7493c0252092fa86140860c1114a035398c09a` |
| `/etc/systemd/system/goalvision-adaptive-learning.service` | `a2e9081eb083665f17b32c8a3ff7a05c8f1073e2f1501de6f87ad00e755c2aed` |
| `/etc/systemd/system/goalvision-adaptive-learning.service.d/90-quota-lock-hardening.conf` | `76332b75a5738a55ba4aa8f13dfb13063237a683e70262ccede2dcb73fae266e` |
| `/etc/systemd/system/goalvision-adaptive-learning.timer` | `190c203ea7b19776829fb97ee76fec62e0f9cf328a46760b34685d057fac456e` |
| `/etc/systemd/system/goalvision-admin-alerts.service` | `b7fb2228b47506f853d5df4499270d82f8cf956b060b7558c0fd7ab3b5150a21` |
| `/etc/systemd/system/goalvision-admin-alerts.timer` | `22a76b96bae2598f9ef2c05f39093e048ddee91068ea856ec77c7be6dff29d8d` |
| `/etc/systemd/system/goalvision-lab-combo-settle.service` | `bb0c1d71cd510b83a4d87230a246b82e83886c882fdcbd086e0ab9b64c5a363e` |
| `/etc/systemd/system/goalvision-lab-combo-settle.service.d/90-reviewed-prematch-v2.conf` | `8ecdfedd8ee5839e2ff1adf2ca2d6943bfea59f5e456c75d989b336661b331a1` |
| `/etc/systemd/system/goalvision-lab-combo-settle.timer` | `cb07e8fa9591abfdae04d10143d7edf7f74fb71d62867ebf5c3acee72427a620` |
| `/etc/systemd/system/goalvision-lab-v2-discover.service` | `6eb6693d878bf0bdf75149250615f7bb409b4437b7ac8f19691285174d48e2d3` |
| `/etc/systemd/system/goalvision-lab-v2-discover.service.d/90-reviewed-prematch-v2.conf` | `a2be440a9ef6518bf43b630c822fa0f61959e884d55d03072bc05f61302b25df` |
| `/etc/systemd/system/goalvision-lab-v2-discover.timer` | `ba40f22f5157720ded06527849ec4cfefd737756905386fb815d0bccb8f5055c` |
| `/etc/systemd/system/goalvision-lab-weekly-stats.service` | `ee64b9126e15128800ca6b5e9372e23cd1faf74edc959a04ed742341b3c32225` |
| `/etc/systemd/system/goalvision-lab-weekly-stats.service.d/90-reviewed-prematch-v2.conf` | `8ecdfedd8ee5839e2ff1adf2ca2d6943bfea59f5e456c75d989b336661b331a1` |
| `/etc/systemd/system/goalvision-lab-weekly-stats.timer` | `f0e27207d0b367cf275d762f7e7624013dba568df95f5762905010e0d5bd4aca` |
