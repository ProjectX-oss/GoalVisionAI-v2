# PREMATCH forward evidence rotation fix — 2026-09-28

**PREMATCH_FORWARD_EVIDENCE_ROTATION_FIX_READY_FOR_REVIEW**

## Current handoff

Production timer stagger v4 is successfully installed, per the operator's
2026-09-28 report, from commit
`b32ede450e19ecac771cde5e9a1d03a6668e3746`. The remaining
`DISCOVERY_ROTATION_REQUIRES_OPERATOR_REVIEW` refusal was caused by selecting
irrelevant old compressed logs. This revision changes only the operations
validator, tests and documentation/package evidence.

The operator supplied these coverage bounds (not independently re-read here):

| Discovery file | Earliest / latest supplied UTC timestamp |
|---|---|
| `/var/log/goalvision-prematch/discovery-output.log` | first `2026-09-28T06:00:02.475971+00:00`; last `2026-09-28T18:30:08.329293+00:00` |
| `/var/log/goalvision-prematch/discovery-output.log.1` | last `2026-09-27T19:30:01.474996+00:00` |
| `/var/log/goalvision-prematch/discovery-output.log.2.gz` | last `2026-09-26T19:00:19.868180+00:00` |

The reported successful install time falls within the current file's coverage.
The validator uses the exact requested `--since` or durable `installed_at`, with
no rounding: earliest current timestamp <= start makes that file sufficient.

### Selection and failure behavior

1. Validate and read current `discovery-output.log`; calculate the minimum valid
   timestamp for `goalvision-lab-v2-operator-cycle-v1`, independent of line order.
2. Once the earliest timestamp is at or before the requested start, stop. List
   older numeric rotations as outside the evidence window without opening,
   decompressing or charging their size against the read budget.
3. Otherwise read `.1`, `.2`, etc., in numeric newest-to-oldest order until
   coverage reaches the start. Missing or duplicate required rotation numbers
   fail closed with `DISCOVERY_ROTATION_GAP_OR_AMBIGUOUS`.
4. A required `.gz` still refuses with
   `DISCOVERY_ROTATION_REQUIRES_OPERATOR_REVIEW`. There is no gzip reader.
5. Selected files share the existing 64 MiB limit, enforced during reads too,
   plus a 100,000-line limit. Missing, unreadable, empty, symlinked and non-regular
   required files fail closed. Malformed/unrelated lines never count as evidence;
   malformed timestamps in matching cycle documents now explicitly refuse.
6. Existing journal checks still require scheduled starts, invocation IDs,
   completions and expected cycle output. Timestamp bounds alone cannot supply
   missing output across a temporal gap. Service evidence rules are unchanged.

Reports include `discovery_output_files_read` (selection order),
`discovery_output_files_ignored_outside_window`,
`discovery_output_file_ranges` (earliest/latest valid timestamps and bytes/lines
read), and `discovery_output_coverage_since`.

### Validation

`python3 -B -m unittest discover -s tests/operations -v`: **61 tests passed**.
Only operations tests ran. The 14 new tests cover current-file sufficiency,
equality at `--since`, earliest valid schema timestamp, old gzip/oversized files
never opened, consecutive and numeric rotation order, required gzip refusal,
missing/duplicate rotations, temporal gaps, malformed/unavailable/oversized
required evidence, shared byte/record bounds, and complete report integration.
The integration fixture blocks network/API/Telegram access and file mutations,
allows only a mocked journal read and service inspection, and verifies fixture
bytes and mtimes are unchanged. Calendar tests use read-only systemd-analyze;
transaction tests use fake hosts and temporary directories.

No production logs were accessed or modified for this fix. No production
validation, timer/systemd mutation, worker execution, application change,
network/API/Telegram call, installation or push was performed. Algorithm
backtesting does not apply to this operations reader correction.

### Review package and read-only evidence command

- New frozen package: `/home/arvis/goalvision-operations/prematch-timer-stagger-v4-evidence-r1-20260928`
- Archive: `/home/arvis/goalvision-operations/prematch-timer-stagger-v4-evidence-r1-20260928.tar.gz`
- Archive SHA-256: `67dd346ccaa3b873ba0c57ce7bdef6532c221163bb896b77d66c4e2266477504`
- Manifest SHA-256: `1e1fa8ba34de63a2436da5d5a875231e388cfdc921430197dae596d514e6fffd`
- Reader SHA-256: `7d2645db0c51986f461fe417133a2dd0e9a160bf9322f0db4c877669d048e8c3`

The source package, frozen files and archive payload were compared byte-for-byte.
The archive reproduced identically with fixed metadata and gzip mtime. The
original installed v4 directory/archive remain unchanged. Controller, calendar
proof, baseline, Persistent guards and all four drop-in payloads retain their
original bytes. `SUPERSEDES.json` retains the historical v4 timer supersession
record; evidence r1 does not replace the installed timer configuration.

After review, the operator can use the new package's read-only evidence action:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v4-evidence-r1-20260928 && echo "1e1fa8ba34de63a2436da5d5a875231e388cfdc921430197dae596d514e6fffd  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py evidence --manifest-sha256 1e1fa8ba34de63a2436da5d5a875231e388cfdc921430197dae596d514e6fffd'
```

It defaults to the existing durable successful installation timestamp. An
explicit `--since` must preserve the intended post-install interval. No timer
installation is needed. The older install/rollback commands below are archived
historical instructions and must not be rerun for this validator fix.

---

## Archived v4 handoff (2026-09-27; superseded operational status)

The rest of this document preserves the pre-install v4 review and original
artifact hashes. Its statements about installation being pending describe that
historical review, not the current production state.

# PREMATCH systemd timer stagger hardening — v4

## Status and supersession

**PREMATCH_TIMER_STAGGER_HARDENING_READY_FOR_OPERATOR_PREFLIGHT**

All 47 operations tests pass. The final schedules have zero exact collisions
across all ten timer pairs in each required window and recurring common
Persistent-safe deployment windows from the pinned production calendars.

Both previous candidates and packages are **SUPERSEDED / MUST NOT INSTALL**:

- `46e680851fd8c64c5d003c14215de75128537542` / `prematch-timer-stagger-v2-20260927`: 04:15 research collides with settlement.
  Manifest `34faa9f26e8176b54213209e0a705e2096f821d18b45365b5a06c56460cc2472`; archive `226b0494d8c08b72210c12500017fa75ee7368dc1c549482a873289e42d6d0bb`.
- `a8bfc1fd30b2da3112284e436d11eec050d804e8` / `prematch-timer-stagger-v3-20260927`: 04:20 research and Sunday 22:48 weekly have no common Persistent-safe deployment window.
  Manifest `0b323c31b53cffebff688a1fb370fe8d07deb210031f5949aecc71ddecd9166d`; archive `ade13cb7dc820fc22105188cae042960f0954f1f0b1723a980d3ae9584d301de`.

`SUPERSEDES.json` records both and retains the earlier v1 supersession. Old
archive/package bytes are retained for audit; matching external
`.SUPERSEDED_DO_NOT_INSTALL.json` sidecars mark them. Use only v4 commands below.

No installation, push, production timer/service control, manual worker run,
Telegram/API-Football call, ADMIN mutation, application database change, quota
policy change or model/publication change was performed. Application code is
unchanged. Full protected ADMIN preflight and production forward evidence remain
pending; readiness here means ready for operator preflight.

## Final schedules and exact allowed changes

| Timer | Original production calendar (systemd normalized) | Final calendar |
|---|---|---|
| `goalvision-lab-v2-discover.timer` | `*-*-* 09..22:00,30:00 Europe/Riga` | `*-*-* 09..22:00,30:00 Europe/Riga` |
| `goalvision-lab-combo-settle.timer` | `*-*-* *:00/10:00` | `*-*-* *:05,15,25,35,45,55:00` |
| `goalvision-adaptive-learning-observer.timer` | `*-*-* *:00/30:00` | `*-*-* *:08,38:00` |
| `goalvision-lab-weekly-stats.timer` | `Sun *-*-* 22:30:00 Europe/Riga` | `Sun *-*-* 22:28:00 Europe/Riga` |
| `goalvision-adaptive-learning.timer` | `*-*-* 04:15:00` | `*-*-* 04:12:00` |

Host timezone is pinned to Europe/Berlin. Zone-less calendars retain that timezone;
discovery and weekly stats explicitly use Europe/Riga. No fixed UTC offset is
assumed. Research moves three minutes earlier than production, and weekly stats
two minutes earlier. All cadences are preserved.

Exactly four paths may be added under `/etc/systemd/system/`:

- `goalvision-lab-combo-settle.timer.d/95-goalvision-prematch-timer-stagger.conf`
- `goalvision-adaptive-learning-observer.timer.d/95-goalvision-prematch-timer-stagger.conf`
- `goalvision-lab-weekly-stats.timer.d/95-goalvision-prematch-timer-stagger.conf`
- `goalvision-adaptive-learning.timer.d/95-goalvision-prematch-timer-stagger.conf`

Every payload resets `OnCalendar=` and supplies one final expression. Discovery
has no drop-in. Original units, service associations, `Persistent=true`, accuracy,
randomization and enabled/active/inactive state are preserved. The controller
pins all five target calendars and the exact four-timer allowlist in baseline.json.

## Runtime collision and cadence evidence

`systemd-analyze calendar`, systemd 255 (255.4-1ubuntu8.17), installed tzdata 2026c.
`evidence/calendar-proof.json` records evaluator/version/zoneinfo hashes, complete
original and target UTC triggers, counts, all intersections, cadence and neighbors.
Enumeration must reach beyond the end of each window. Windows are half-open and
48 elapsed hours; the current one begins at the current UTC hour and regenerates
at each proof/preflight.

| Window start UTC | Discovery | Settlement | Observer | Weekly | Research | Exact collisions |
|---|---:|---:|---:|---:|---:|---:|
| 2026-09-27T19:00:00+00:00 (current_48_hours) | 56 | 288 | 96 | 1 | 2 | 0 |
| 2026-03-28T00:00:00+00:00 (spring_dst) | 56 | 288 | 96 | 1 | 2 | 0 |
| 2026-10-24T00:00:00+00:00 (autumn_dst) | 56 | 282 | 94 | 1 | 2 | 0 |

| Pair | Current | Spring DST | Autumn DST |
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

Discovery evaluated ticks are unchanged. Daily research ticks are exactly 180
seconds earlier, retaining daily intervals of 86,400 seconds normally, 82,800
across spring DST and 90,000 across autumn DST. Weekly cadence is compared over
three consecutive ticks per window and remains unchanged. Settlement normally
has 600-second gaps; observer has 1,800-second gaps. The installed evaluator skips
the repeated local hour in autumn: original and target share one 4,200-second
settlement gap and one 5,400-second observer gap. Counts and gap sets match.

### Nearest-neighbor separation

| Subject | Peer | Previous peer | Gap before | Next peer | Gap after |
|---|---|---|---:|---|---:|
| Research 04:12 host time | Settlement | 04:05 | 7 min | 04:15 | 3 min |
| Research 04:12 host time | Observer | 04:08 | 4 min | 04:38 | 26 min |
| Weekly Sunday 22:28 Riga | Settlement | 22:25 Riga | 3 min | 22:35 Riga | 7 min |
| Weekly Sunday 22:28 Riga | Discovery | 22:00 Riga | 28 min | 22:30 Riga | 2 min |
| Weekly Sunday 22:28 Riga | Observer | 22:08 Riga | 20 min | 22:38 Riga | 10 min |

All margins are evaluated in every collision window, with peer timestamps
converted to the subject's timezone. Berlin is one hour behind Riga in these
windows. This does not reinterpret the zone-less timer as a Riga calendar.
Timer accuracy remains 1 minute (1 second for weekly), with zero randomized delay.
Exact schedule separation does not guarantee that worker runtimes cannot overlap;
outage catch-up can also coincide. Application locking is outside this change.

## Common Persistent-safe deployment proof

`persistent_proof.py` reads original schedules and Persistent flags from the
pinned production baseline and rejects drift. It obtains original/target ticks
from systemd, including nine days of history to cover the previous weekly tick.
The algorithm partitions time at every original/target trigger and its ±10-second
boundary, then intersects safety across all four changed timers:

`latest original tick >= latest target tick`

Both old and target boundaries are excluded. The resulting intervals are exact
for these evaluated calendars. Every UTC day in the eight-day current horizon
and both DST windows must offer a usable interval longer than the 60-second
installation reserve. Future windows assume normal original ticks; this is a
forecast, never a claim that those runs occurred.

| Evaluation horizon | Usable common windows | Recurring on every UTC day |
|---|---:|---|
| current_eight_days: 2026-09-27T00:00:00+00:00 through 2026-10-05T00:00:00+00:00 | 384 | yes |
| spring_dst: 2026-03-28T00:00:00+00:00 through 2026-03-30T00:00:00+00:00 | 96 | yes |
| autumn_dst: 2026-10-24T00:00:00+00:00 through 2026-10-26T00:00:00+00:00 | 94 | yes |

Typical intervals are **HH:00:10–HH:04:50** and **HH:30:10–HH:34:50**. Endpoints
are exclusive at the right. Admission additionally requires more than 60 seconds
remaining: start before **HH:03:50** or **HH:33:50** respectively. Actual timer
accuracy, delayed/missed triggers and runtime state can make an otherwise forecast
window unavailable; the controller always rechecks.

`evidence/persistent-common-window-proof.json` includes every usable interval,
per-day counts, exact baseline/target schedules, boundary/reserve rules, pinned
baseline digest, evaluator and tzdata metadata. Negative proofs establish:

- 04:15 research collides daily with settlement (superseded v2).
- 04:20 research with final 22:28 weekly has no common window.
- 04:20 research with superseded 22:48 weekly also has no common window (v3).

### Controller output and refusal

Check/status/proof expose:

- `common_safe_now`: requires a forecast interval, sufficient time remaining and
  real observed `LastTriggerUSec >= latest target tick` for every active changed
  timer. Missing, stale, future or unknown evidence fails closed. Inactive timers
  remain inactive and are never re-armed.
- `next_common_safe_window`: UTC start/end and latest install start, explicitly
  conditional on observed last triggers. It may describe the current forecast
  interval when only observed evidence is missing. It is null for incompatibility.

A successful read-only check may report `common_safe_now: false`. That does not
authorize immediate installation. INSTALL independently re-evaluates the window
and refuses with `OUTSIDE_COMMON_SAFE_WINDOW` or `NO_COMMON_PERSISTENT_WINDOW`,
including these output fields, before creating deployment lock/state. It does
not wait until the next window and creates no background installer. Time is
recaptured after calendar evaluation so evaluation latency cannot authorize a
stale window. Timing is checked again before transaction writes, before reload,
and before each changed active timer is re-armed.

## One foreground install transaction and rollback

The operator runs one install command after preflight. It uses an exclusive lock,
verifies package/source/calendars/timezone/ADMIN state, and records durable intent.
All four exact drop-ins are written through atomic replacement and fsync before
one daemon-reload. Only originally active changed timers are re-armed; discovery,
services and ADMIN are never controlled. Each changed timer's next elapse is
checked against systemd calendar evaluation. No timestamp file is edited, no
Persistent flag changed and no missed-run receipt synthesized.

This is one foreground transaction with failure recovery, not a staged deployment.
Atomic replacement applies to each file; systemd does not provide an all-files,
all-timers atomic primitive. Catchable failures attempt rollback. A crash can
leave a partial transaction, which the next rollback (or install detecting the
incomplete transaction) restores before a separate new install is allowed.
No unattended recovery service is added.

Rollback verifies exact ownership, removes only these four drop-ins, reloads,
re-arms originally active timers and verifies original schedules/hashes/states.
It retains the Persistent catch-up guard using observed evidence. Immediate
rollback within the admitted window is covered by a synthetic test with the real
guards. Later rollback is not guaranteed safe at arbitrary times: after target
runs replace old LastTrigger evidence, the reverse schedules may have no common
safe window. Rollback refuses promptly if a guard fails and retains its durable
transaction for operator review. It never edits timer stamps or starts workers
to force rollback. Do not delete pending transaction metadata.

If next-elapse verification waits for a normally running worker, its existing
bound is 15 minutes with two-second checks; it never stops that worker. There is
no multi-hour wait for install or rollback eligibility. Production validation is
not claimed by transaction tests.

## Read-only host inspection and protected preflight

The v4 inspection matched all 12 pinned PREMATCH/ADMIN units, all 17 source-file
hashes, loaded original calendars and `NeedDaemonReload=no`. The original capture
is retained as the rollback baseline. Updated read-only evidence includes actual
last-trigger observations and the common-window decision. It does not modify any
unit, service, database or ADMIN state.

Full preflight requires root access to protected ADMIN configuration/state. ADMIN
sender state has not been verified here. The existing check reads the configured
flag/fence/epoch and a stable byte snapshot under the existing read-only scan lock;
SQLite receives only an in-memory copy. WAL/journal sidecars, unknown or inconsistent
state fail closed. No token/transport is used. Concurrent systemd configuration
work is prohibited during an operator transaction.

## Operations tests

47 operations tests pass. Only `tests/operations` ran; there is no application,
model or historical test run. Filesystem mutations use temporary fixture paths;
systemd controls use a fake host. Real systemd calendar evaluation supplies all
calendar and common-window proofs. A synthetic safe install/rollback uses the real
common-window and Persistent guards with declared synthetic original ticks.
Missing/stale/future last-trigger tests prevent forecasts from becoming receipts.

Coverage includes all ten pairs, three windows, cadence and neighbor margins;
04:15 collision refusal; both incompatible 04:20 proposals; recurring final
windows; no-mutation outside-window refusal; successful inside-window transaction;
exactly four drop-ins; service-control denial; inactive timer preservation;
rollback/recovery after every drop-in/reload/re-arm failure; drift/tamper/symlink
rejection; unchanged ADMIN fixture bytes/mtimes; and forward evidence contracts.
Network access is forbidden in transaction fixtures. Controller SQLite opens only
an in-memory snapshot, never an application or live ADMIN database.

```bash
python3 -B -m unittest discover -s tests/operations -v
```

## Forward evidence after a future successful install

The evidence command defaults to the durable successful installation time and
reads normal scheduled execution only. Allow at least two discovery, three
settlement and two observer completions. It never launches a worker. This runtime
evidence scope remains those three frequent services; all five timers participate
in calendar collision proof.

The report records invocation IDs, Starting/completion timestamps, scheduled
alignment, exit status and counts for QUOTA_DB_CONTENTION_RETRY,
QUOTA_DB_CONTENTION_EXHAUSTED, SERVICE_FAILURE, DATABASE_LOCK and MISSING_OUTPUT.
Transient retries alone do not fail an otherwise successful invocation. Missing,
truncated, rotated/compressed or unavailable evidence fails closed for review.
Starting records show actual service activations; calendar alignment alone does
not prove which client requested the start. Discovery file output is associated
by time window without an invocation ID. Settlement stdout is null and reported
NOT_ASSESSABLE_STDOUT_NULL. Observer requires its structured PREMATCH document
with exact journal invocation attribution. No production success is yet measured.

## Package, hashes and exact commands

Verify archive/manifest/file hashes against this trusted handoff before Python
execution. Every controller action repeats manifest and inventory checks. Keep
package ownership controlled during execution. Hashes provide integrity against
the reviewed digest, not an independent signature. Commands below are supplied
for later operator use; no install or rollback command has been executed here.

### Versioned package v4

- Extracted package: `/home/arvis/goalvision-operations/prematch-timer-stagger-v4-20260927`
- Archive: `/home/arvis/goalvision-operations/prematch-timer-stagger-v4-20260927.tar.gz`
- Archive SHA-256: `dcc9d4f6ddfc7eb512f8785b4600fba6ef9987cfda2e512236a7fcc3d7e2d91e`
- Manifest (`SHA256SUMS`) SHA-256: `61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598`

The archive contains only the standalone operations package. Source, archive and
frozen package bytes match exactly. Archive metadata and gzip mtime are fixed;
rebuilding the same payload produces identical bytes. The archive and extracted
package are read-only. Full protected ADMIN preflight and production forward
validation remain pending. Install requires a freshly verified common safe
window and observed last triggers; these commands do not bypass either guard.

| Package file | SHA-256 |
|---|---|
| `README.md` | `cd45704b8bf58d783e634c3c1c549defc13e769fd9b67b8fd92d4ee62d3f94c2` |
| `SUPERSEDES.json` | `4371b09aaae37ec162510b618a6e547b8d43064748ad235684bb7370f3d15270` |
| `baseline.json` | `c1483eeeebf91c4ba5699965d0348334ba3f692f787bd6efe35497c5d082285a` |
| `calendar_proof.py` | `0e308ff5c2a4c423bd94248d0bf50f0bf29399c8327c8dd4e90e906254cb80d6` |
| `control.py` | `836126dc552367647edbd94c6541a62d83b65dc4e166a57f06fa86a04e534f95` |
| `drop-ins/goalvision-adaptive-learning-observer.timer.conf` | `0ddbd492381bd624ab9cc2fd08cc1e7839e6e20bc2c86f80cc3f1736ec0f2f58` |
| `drop-ins/goalvision-adaptive-learning.timer.conf` | `784754a925ba8e7635cdb8640991842bf02ad6dad667be3cd4fdb4ee5cfda29b` |
| `drop-ins/goalvision-lab-combo-settle.timer.conf` | `29eb3bdcab1115c4457a897633cd487ca55207a09a620aa8a530b624342a48c0` |
| `drop-ins/goalvision-lab-weekly-stats.timer.conf` | `86630652ddf7dad6317e6992ec2f60d5184d300cd4f01f46f0ea34e2b8c4ce51` |
| `evidence/calendar-proof.json` | `cf5fb00ceb4ddba289f4b8cc0c2a7a7422d2cd496aefeaac1dab73e4aea14527` |
| `evidence/operations-tests.txt` | `0275904e3727168d992d2b0444b290d38811f9927bd8284a4cfdcf1343bfaa05` |
| `evidence/persistent-common-window-proof.json` | `784d98d24e143d2737385707f42a3b92f444abcca2cf179f667274a8f4342eae` |
| `evidence/read-only-host-inspection.json` | `65b1b825695dad917d6739367e104fad5e0e99de5ea381f6189657e9c6471c79` |
| `evidence/superseded-0420-persistent-proof.json` | `8f7b938fa0f19e0d3887a89bdfea698748830c25311df09b4439e4dee117d494` |
| `evidence/superseded-v2-collision-proof.json` | `fe27fe0ed7fc7ffe056a6e3c59c0bfe5437fa34486b1c8ffe285f41391ba6d82` |
| `evidence/superseded-v3-persistent-proof.json` | `600eab3cd8fddc282002f7816822aacfea6b3c5ea06f7d4b9fdb34d10c46787a` |
| `forward_evidence.py` | `9a84af3e3fa80f2aa6033561b36d51a93261655d5379eb801e002e68a9d797c5` |
| `persistent_proof.py` | `1a360c2b8ce95555bb4e6eb549ea1d4a030f6ae06377135119ac4e6baf0eb5bf` |

### Exact operator commands

Archive verification:

```bash
cd /home/arvis/goalvision-operations && echo "dcc9d4f6ddfc7eb512f8785b4600fba6ef9987cfda2e512236a7fcc3d7e2d91e  prematch-timer-stagger-v4-20260927.tar.gz" | /usr/bin/sha256sum --check --strict -
```

Check:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v4-20260927 && echo "61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py check --manifest-sha256 61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598'
```

Install (future operator use; requires common_safe_now):

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v4-20260927 && echo "61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py install --manifest-sha256 61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598'
```

Status:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v4-20260927 && echo "61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py status --manifest-sha256 61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598'
```

Rollback:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v4-20260927 && echo "61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py rollback --manifest-sha256 61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598'
```

Evidence:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v4-20260927 && echo "61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py evidence --manifest-sha256 61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598'
```

Proof:

```bash
sudo /bin/sh -c 'cd /home/arvis/goalvision-operations/prematch-timer-stagger-v4-20260927 && echo "61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598  SHA256SUMS" | /usr/bin/sha256sum --check --strict - && /usr/bin/sha256sum --check --strict SHA256SUMS && exec /usr/bin/python3 -I -B control.py proof --manifest-sha256 61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598'
```


## Pinned original source hashes

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
