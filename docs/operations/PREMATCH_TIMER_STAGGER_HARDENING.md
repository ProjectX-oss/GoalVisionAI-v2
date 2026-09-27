# PREMATCH systemd timer stagger hardening

## Readiness and supersession

**PREMATCH_TIMER_STAGGER_HARDENING_READY_FOR_OPERATOR_PREFLIGHT**

Weekly stats now uses the explicitly approved Sunday **22:48 Europe/Riga**.
All other target schedules are unchanged. Systemd calendar evaluation proves
zero exact trigger collisions across all six required timer pairs in each of
three 48-hour windows, including both DST transitions. All 31 operations tests
pass. Production installation and forward validation have not been performed.

**Commit `b286210` and its package are SUPERSEDED — DO NOT INSTALL.** The obsolete
manifest SHA-256 is
`03102aa9c8b06a18d735328846725680c9347a4d1074cfc51cdaa699358938ca`.
The corrected package records this in `SUPERSEDES.json`. Use the new package and
trusted hashes below; the old 22:45 target is retained only in a negative
regression test. This readiness status means ready for the root operator's
read-only preflight, including protected ADMIN state verification.

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
| `goalvision-adaptive-learning.timer` | `*-*-* 04:15:00` | unchanged |

Systemd normalizes the old settlement and observer expressions to
`*-*-* *:00/10:00` and `*-*-* *:00/30:00`. The host timezone is Europe/Berlin;
zone-less expressions deliberately retain that existing timezone. Discovery and
weekly stats explicitly retain Europe/Riga. No fixed UTC offset is assumed.
Research remains at 04:15 host time, which also matches the new settlement :15;
research is outside the requested four-timer collision comparisons.

Exactly three files are intended to be added, each under `/etc/systemd/system/`:

- `goalvision-lab-combo-settle.timer.d/95-goalvision-prematch-timer-stagger.conf`
- `goalvision-adaptive-learning-observer.timer.d/95-goalvision-prematch-timer-stagger.conf`
- `goalvision-lab-weekly-stats.timer.d/95-goalvision-prematch-timer-stagger.conf`

Each resets the inherited `OnCalendar=` list and adds one target expression.
No other directive changes. Existing `Persistent`, accuracy, randomization,
service associations, enabled state and inactive/active timer state are preserved.
No discovery or research drop-in is created.

## Exact calendar proof

`systemd-analyze calendar` evaluates every trigger with installed tzdata.
`evidence/calendar-proof.json` contains the requested schedules and all pairwise
intersections. Windows are half-open, exactly 48 elapsed hours:

| Window start (UTC) | Discovery | Settlement | Observer | Weekly | Research | Exact collisions across all six pairs |
|---|---:|---:|---:|---:|---:|---:|
| 2026-09-26 21:00 | 56 | 288 | 96 | 1 | 2 | 0 |
| 2026-03-28 00:00, spring DST | 56 | 288 | 96 | 1 | 2 | 0 |
| 2026-10-24 00:00, autumn DST | 56 | 282 | 94 | 1 | 2 | 0 |

Discovery/settlement, discovery/observer, settlement/observer,
weekly/discovery, weekly/observer and weekly/settlement intersections are all
empty in every window. Weekly stats evaluates to 19:48 UTC on September 27 and
March 29, and 20:48 UTC on October 25, with Europe/Riga resolved by systemd.
`evidence/calendar-proof.json` is the final accepted proof; the old proposal-only
proof has been removed to avoid two competing release artifacts.

Normal settlement spacing is 600 seconds and observer spacing 1,800 seconds.
The systemd evaluator skips the repeated local hour in autumn, producing one
4,200-second settlement gap and one 5,400-second observer gap. The original
calendars have the same counts and gaps. Tests compare old and new evaluation;
there is no claim of uninterrupted elapsed-time cadence across DST when the
original local calendars do not provide it. Research's exact evaluated timestamps
and discovery's expression are unchanged.

Timer accuracy remains 1 minute for the frequent timers and 1 second for weekly
stats; random delay remains zero. Exact timestamp separation does not prove that
long-running workers cannot contend. Persistent catch-up after downtime can also
coincide. These settings and application locking are outside this change.
See the upstream [systemd timer documentation](https://github.com/systemd/systemd/blob/main/man/systemd.timer.xml)
for calendar accuracy and persistent catch-up behavior.

## Pinning and read-only preflight

`baseline.json` pins the 12 PREMATCH/ADMIN timer and service units and all 17
fragment/drop-in source hashes, captured at 2026-09-27T18:25:15.954432+00:00.
It also pins the host timezone and `/etc/localtime` content hash. The file hashes
are listed below. Live read-only inspection passed all 12 units, 17 hashes,
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

`Persistent=true` is retained. An operator should use a naturally safe window,
for example Sunday shortly after 22:30 Europe/Riga, once that normal weekly tick
has occurred and before 22:35. This is a suggestion, not a bypass: current
`LastTriggerUSec` and target calendars decide safety. If preflight reports
`PERSISTENT_CATCHUP_RISK_RETRY_AFTER_NORMAL_RUN`, wait for the normal scheduled
run and check again. Do not start the service or edit its timestamp file.

Catchable installation failures attempt restoration. Rollback verifies exact
ownership, removes only the three exact package drop-ins, reloads for those
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

31 operations tests passed. No model, history or full application suite ran.
Fixtures use temporary unit/state directories and a fake systemd control boundary.
Real `systemd-analyze` handles calendar evaluation only. Transaction tests isolate
the collision gate to exercise mechanics. Separate acceptance tests evaluate the
final schedules and all six pairwise intersections, while a negative regression
proves that the superseded 22:45 weekly target is still rejected.

| Requested coverage | Verification |
|---|---|
| Exact targets, cadence, no collisions | Exact final payloads; 48-hour/DST evaluation; all six pairs pass at approved 22:48; superseded 22:45 is rejected |
| Discovery/research unchanged | Original hashes, exact expressions/evaluated research timestamps |
| Only intended timer changes | Exactly three owned drop-ins; all original unit hashes preserved |
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
python3 -B -m unittest discover -s tests/operations -p test_prematch_timer_stagger.py -v
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

### Versioned package

- Package archive: `/home/arvis/goalvision-operations/prematch-timer-stagger-v2-20260927.tar.gz`
- Package SHA-256: `226b0494d8c08b72210c12500017fa75ee7368dc1c549482a873289e42d6d0bb`
- Extracted package: `/home/arvis/goalvision-operations/prematch-timer-stagger-v2-20260927`
- Manifest (`SHA256SUMS`) SHA-256: `34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472`

The archive contains only the standalone operations package. Its frozen extracted
copy is used by the commands below. The source tests and this handoff remain in
the committed worktree. The archive uses fixed metadata and gzip mtime for
reproducible packaging. Both the extracted package and archive are read-only.
Archive members, frozen package files and committed source package bytes were
compared and match exactly. The frozen package CLI reproduced the accepted
calendar/DST proof. Its read-only check reached the protected ADMIN configuration
and refused access without root, as expected; full operator preflight is pending.

| Package file | SHA-256 |
|---|---|
| `README.md` | `b5cbc2a2e31e7cff3134e6ff86bd88b066a1b4fa7c575a90adc7a1ee5b26292a` |
| `SUPERSEDES.json` | `a1465dddaba260d726e6afb4718ea0c9f641be5905b41a18788e4a5e69272fb7` |
| `baseline.json` | `1eb8e37a510a5cf525e37e5c15ea85164e0c8b91a244e8ea2fb8ca03a739e4a1` |
| `calendar_proof.py` | `1c5ed11137d60f35b5e4b2169c9fb27064529734a840204fe383be48a7dac1d8` |
| `control.py` | `805edab5621104dacf6b0339a182679579ce11aeed99979c05f80da1f7231866` |
| `drop-ins/goalvision-adaptive-learning-observer.timer.conf` | `0ddbd492381bd624ab9cc2fd08cc1e7839e6e20bc2c86f80cc3f1736ec0f2f58` |
| `drop-ins/goalvision-lab-combo-settle.timer.conf` | `29eb3bdcab1115c4457a897633cd487ca55207a09a620aa8a530b624342a48c0` |
| `drop-ins/goalvision-lab-weekly-stats.timer.conf` | `6b64433a79d412ae4f6dfca9d3e791fbbbba1ade4e68e75a2248a5ae17549092` |
| `evidence/calendar-proof.json` | `1c9a03b7857788fd0b551dba21da83b5a036a35ef49bde39a0bb2ec03d6788b1` |
| `evidence/operations-tests.txt` | `fef9a188ef87d9d539e2243480567548c59b7e63999d25eb40be02eeb36079dc` |
| `evidence/read-only-host-inspection.json` | `1fecfdf3c2d03b1ebd9aaaf731cd5d2b7a2b5e0a2af0d3a041ac89b9465591f8` |
| `forward_evidence.py` | `9a84af3e3fa80f2aa6033561b36d51a93261655d5379eb801e002e68a9d797c5` |

### Exact one-line commands

Check:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v2-20260927 && echo "34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py check --manifest-sha256 34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472'
```

Install:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v2-20260927 && echo "34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py install --manifest-sha256 34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472'
```

Status:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v2-20260927 && echo "34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py status --manifest-sha256 34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472'
```

Rollback:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v2-20260927 && echo "34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py rollback --manifest-sha256 34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472'
```

Evidence:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v2-20260927 && echo "34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py evidence --manifest-sha256 34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472'
```

Proof:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v2-20260927 && echo "34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py proof --manifest-sha256 34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472'
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
