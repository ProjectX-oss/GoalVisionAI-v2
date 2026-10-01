# ADMIN Auto-Repair + Operator Job Status v1 — 2026-09-30

Status: implemented locally from ADMIN `59f051834a4a69ed4941cc78b767f5db0a126c33`.
Deployment is a separate, explicitly reviewed operator action. Nothing below has
been installed, enabled, or run against production by this implementation task.

## Scope and safety boundary

Only `app/admin_alerts` and the new independent `app/admin_autorepair` runtime
change. Official, LIVE, model/champion activation, prediction/confidence/odds
thresholds, bankrolls, combo policy, provider/Telegram credentials, producer
SQLite schemas, publication logic, production services and schedules are unchanged.
There is no prediction algorithm change requiring a backtest.

The monitor writes only its dedicated ADMIN SQLite and the repair spool. Its
existing incident adapters remain read-only. Repair reservations, activation and
maintenance exclusions are immutable, protected by UPDATE/DELETE triggers.
Operator job state/outbox/attempts are separate from incidents and correlation.
Both senders share five attempted sends per scan and twenty attempts per hour,
with incident work served first. Operator status cannot change active fault count.

The worker never imports a sender, reads the ADMIN token or calls Telegram. It
uses a minimal environment without inherited application credentials. Deployment
creates root-owned **bare local source snapshots**, not links to producer
worktrees. Workers clone the configured source HEAD with `--no-local` over the explicitly
allowed local file transport, check out the recorded commit detached, remove origin
and disable Git hooks/global config/network protocols. This avoids direct local
object-store copying races while still forbidding network protocols.
No source mutation, fetch, pull, push, commit or deployment is implemented.

The provided systemd unit runs as `arvis:goalvision-admin-alerts`, with a read-only
host filesystem and source snapshots, private temporary storage, hidden home
(except read-only `/home/arvis/.codex` and `/home/arvis/.local/bin/codex`), masked
`/etc`, `/run`, and `/var` (only worker config, resolver/passwd/group/certificate
essentials and the writable spool are rebound), no capabilities, and resource
limits. This prevents host/source file writes and access to service-manager
sockets. The launcher symlink's standalone binary target inside `.codex` is
readable; ADMIN credentials/config and production PREMATCH logs/DBs remain hidden.
Resolved resolver files under `/run/systemd/resolve` are exposed individually,
without exposing the service-manager directory or sockets.
**Use the hardened service for real Codex; direct CLI invocation is for
offline fake-Codex rehearsal/inspection.** Do not weaken confinement to fix startup.

Codex is invoked with `exec --approve-for-me`, `--ignore-user-config`,
`--ignore-rules`, `--ephemeral` when supported, disabled web search/apps and shell
sandbox network access. `FIX_ALLOWED` uses `--sandbox workspace-write` and
`DIAGNOSE_ONLY` uses `--sandbox read-only`. No sandbox-bypass fallback exists.
The fixed prompt prohibits production/systemd/credentials/DB mutation, provider
and Telegram calls, policy changes, escalation, dependency installation,
commit/push and subagents. It requires diagnosis first, focused offline tests,
`git diff --check`, documentation, and explicit `NO_CODE_FIX` when appropriate.

`DIAGNOSE_ONLY` invokes Codex with `--sandbox read-only`, also forbids edits in
the prompt, and verifies the complete clone tree (including ignored/untracked
files), index and HEAD afterward. Any observed mutation still fails the job and
no patch is emitted. `FIX_ALLOWED` uses `--sandbox workspace-write` only inside
the disposable clone and also rejects HEAD mutation and failed diff checks.
Patches always require human review; no result can activate or deploy itself.

## Activation, routing and persistence

Tracked sample configuration defaults to:

```json
"autorepair": {
  "enabled": false,
  "spool": "/var/lib/goalvision-admin-autorepair"
}
```

On the first successful enabled scan, snapshot all OPEN/REPEATED/ESCALATED and
PENDING episodes and enqueue none. With `--enable-autorepair`, the installer
automatically creates and verifies this baseline before activating the worker.
A recovered then reopened episode has a new
episode number and can queue once. Disabling/re-enabling does not erase the
baseline or job ledger. It pauses queue/status processing, not history.
Maintenance-filtered events never reach ingestion; already-active episodes
encountered during maintenance receive a permanent episode exclusion.

Each later scan accepts at most one new job, with at most five outstanding
reservations/physical queue or running files. Identity is a stable SHA-256-derived
24-hex digest of incident ID and episode, independent of notification generation.
SQLite commits the reservation before publishing JSON; a later scan repairs an
interrupted handoff without duplicating the job. A cross-user flock fences queue
publication and worker renames. Invalid/missing status never frees a reservation.

Bundles contain only a fixed schema: incident/episode/generation, allowlisted
service/rule/severity, safe opaque identifiers, typed facts, timestamp, target,
and mode. Non-opaque invocation/object/cycle values become hashes. Only explicit
boolean/numeric facts and fixed enum values survive; unknown keys, exception
messages, provider payloads and arbitrary strings are discarded. JSON reads and
writes are capped at 64 KiB, reject links/non-regular files, and use fsync plus
same-directory atomic replacement. Queue/running/done handoffs are atomic renames.
The worker revalidates the producer schema before invocation.

- Monitor and ADMIN-owned coverage/delivery incidents route to `ADMIN`.
- Application incidents route to `PREMATCH`.
- Internal service, analysis, integrity, persistence, output, observation,
  monitoring and DB-lock/contention faults allow a proposed fix.
- Provider/auth/quota, uncertain/external delivery, missing-start/timer and known
  routing/auth configuration faults are diagnosis-only. Quota DB contention is
  an internal locking issue, distinct from provider quota exhaustion.

A whole-job flock and systemd oneshot scheduling permit one worker/Codex process.
The Codex child inherits the lock so an orphan cannot overlap a later worker.
Process-group TERM/KILL enforces the default 45-minute deadline; systemd adds a
47-minute outer limit and control-group cleanup. Polling updates heartbeats every
30 seconds (configurable only up to 60). Logs are drained but retained up to
16 MiB; the service limits individual files to 256 MiB.

A worker restart marks an abandoned running job `FAILED/WORKER_INTERRUPTED` and
moves it to done without replaying Codex. A completed status surviving before
the done rename is preserved. Failed/interrupted jobs require explicit human
review; there is no automatic same-episode retry.

## Operator messages and later inspection

Status files contain machine enums and bounded measurements only. ADMIN never
reads the Codex log or final prose. It scans at most 100 tracked status files per
scan with a durable round-robin cursor. Sequence/time regression, future heartbeat,
unknown fields, arbitrary outcomes and oversized files are rejected.

- All new operator messages use Latvian status/action text and retain incident,
  target, job ID, machine outcome, failure code, changed-file count and elapsed time.
- STARTED: `Sāk izpēti`, with the diagnosis-only or isolated-fix mode.
- RUNNING: `Turpina izpēti` or `Turpina izpēti un labojuma sagatavošanu` after
  ten minutes, then at most every ten minutes; missed intervals do not spam.
  The current protocol cannot distinguish each individual edit/test phase.
- COMPLETED/PATCH_READY: `Gaida pārbaudi un apstiprinājumu`; explicitly requires
  code/test review and manual deployment approval. It does not claim tests passed,
  that production was repaired, or that approval triggers automatic installation.
- Other completion: diagnosis or no code change, with manual result review needed.
- FAILED/TIMEOUT/STALLED: Latvian warning and required operator action.
- Existing persisted notices, delivery identities and retry budgets are unchanged.
- Heartbeat older than three minutes: one STALLED per continuous stale period.
  Fresh heartbeat permits further lifecycle transitions and a later distinct stall.
- A job finishing between scans still creates STARTED then terminal notices.

Durable attempts precede transport, and receipts are stored before marking SENT.
A receipt-backed notification is never replayed. Telegram offers no idempotency
key: exact-once *remote delivery* cannot be guaranteed around a lost response or
crash. Operator ATTEMPTING/uncertain outcomes are held as UNCERTAIN and **never
retried automatically**; definite rejections have bounded retries. Existing
incident uncertainty/retry semantics are unchanged. Separate operator delivery
errors do not generate incident faults or alter incident states.

Each job retains `incident.json`, `prompt.txt`, `source.json`, `invocation.json`,
`codex.log`, `final-message.txt` when Codex supplies it, `result.json`, the clone,
and `result.patch` for a successful fix/no-change result. Interrupted jobs may
have only a subset; the running/done bundle and status remain the authority.
Outcome is PATCH_READY, NO_CODE_CHANGE, DIAGNOSIS_ONLY, CODEX_FAILED or TIMEOUT.
`PATCH_READY` means a diff passed whitespace checks, not that tests or the
proposed fix are independently certified. Read the final message/log and review
all changes. Nothing wakes this ChatGPT chat; the server worker is the handoff.

Read-only inspection (does not construct a Telegram transport):

```sh
sudo -u arvis -g goalvision-admin-alerts /usr/bin/python3 -I /opt/goalvision-admin-autorepair/run.py --list
sudo -u arvis -g goalvision-admin-alerts /usr/bin/python3 -I /opt/goalvision-admin-autorepair/run.py --job JOB_ID
```

The ADMIN database also retains `repair_jobs`, `repair_exclusions`,
`repair_activation`, `operator_jobs`, `operator_outbox`, and `operator_attempts`.
Do not reset uncertain attempts or delete incident/job history to force retries.

## Offline gate and fake-Codex rehearsal

Run from the reviewed worktree. These commands use only disposable synthetic
repositories/SQLite and a generated fake executable, never the configured real
Codex executable. Fixture commits occur only inside temporary synthetic repos.

```sh
/home/arvis/GoalVisionAI/.venv/bin/python operations/admin-autorepair/test_offline.py \
  --adjacent --output /tmp/admin-autorepair-tests.json
/home/arvis/GoalVisionAI/.venv/bin/python operations/admin-autorepair/rehearse.py \
  --output /tmp/admin-autorepair-review-rehearsal
/usr/bin/systemd-analyze verify \
  operations/admin-autorepair/goalvision-admin-autorepair.service \
  operations/admin-autorepair/goalvision-admin-autorepair.timer
git diff --check
```

The rehearsal output directory must not exist. Expect PATCH_READY, unchanged
source hash, STARTED/COMPLETED outbox entries, and zero real Codex/provider/
Telegram calls. Review `rehearsal.json` and `spool/jobs/<job_id>/result.patch`.

## Exact installer procedure — NOT executed in this task

Prerequisites: existing dedicated ADMIN account/group and configured ADMIN
installation; reviewed clean local Git source repositories for the accepted
ADMIN/application HEADs; installed Codex CLI supporting the required flags;
existing arvis Codex authentication. No authentication is copied. The installer
does not create or modify provider or Telegram credentials. The source snapshots
capture committed HEAD; uncommitted implementation changes are **not** worker
source. Source acceptance/commit is a separate authorized workflow.

1. Review this change and all prepared units/installer. Repeat the offline gate.
2. In a separately authorized root session, replace the two source paths below
   with the reviewed committed repositories; run the preview first:

```sh
/usr/bin/python3 operations/admin-autorepair/install_v1.py \
  --source "$PWD" --release autorepair-v1-20260930 \
  --admin-source /absolute/reviewed/admin-source \
  --prematch-source /absolute/reviewed/prematch-source
```

3. Exact installation/activation command, only after explicit deployment review:

```sh
/usr/bin/python3 operations/admin-autorepair/install_v1.py --apply \
  --source "$PWD" --release autorepair-v1-20260930 \
  --admin-source /absolute/reviewed/admin-source \
  --prematch-source /absolute/reviewed/prematch-source \
  --enable-autorepair
```

Omit `--enable-autorepair` for a disabled installation. Default preview performs
no writes or service calls. `--apply` requires root; no automatic sudo escalation.
The installer refuses an existing v1 transaction/destination rather than silently
overwriting a prior install. Failures during pre-transaction release/snapshot
preparation remove only the versioned paths created by that attempt. Failures after
the transaction is written leave explicit rollback/review state; do not rerun by
deleting the transaction.

The installer:

- Stages `/opt/goalvision-admin-alerts-releases/<release>` and
  `/opt/goalvision-admin-autorepair-releases/<release>` with source-file SHA-256
  manifests; creates `/opt/goalvision-admin-autorepair` as a release symlink.
- Creates root-owned bare snapshots in
  `/opt/goalvision-admin-autorepair-sources/<release>/{ADMIN,PREMATCH}.git`.
  Nonlocal cloning supplies a shell-quoted `--upload-pack` command that passes
  the exact resolved common Git directory as `safe.directory` to the child Git
  process when root snapshots an arvis-owned repository. Parent command-line
  `-c` and Git config environment alone do not cover the sanitized child. No
  global Git configuration or wildcard ownership exception is used. The
  regression test first reproduces the child rejection using real Git with a
  forced foreign owner, then verifies exact linked-worktree HEAD, quoted paths
  and untracked-file exclusion.
- Creates `/var/lib/goalvision-admin-autorepair` and queue/running/status/jobs/done,
  owner arvis, group goalvision-admin-alerts, mode **2770**. Atomic spool files
  and shared locks are explicitly 0660 even under ADMIN's 0077 umask.
- Backs up existing ADMIN config/timer-active state in root-only
  `/opt/goalvision-admin-autorepair-install-v1.json`.
- Briefly stops only the ADMIN timer and drains its current scan, preserving
  receipt persistence. It does not stop/kill an active monitor send or PREMATCH.
- Writes `/etc/goalvision-admin-autorepair.json` (no Telegram fields), the two
  worker units, and the ADMIN service `40-autorepair.conf` override pointing at
  the versioned ADMIN release and allowing shared-spool writes.
- Preserves sender identity/configuration and ADMIN activation history; changes
  only the autorepair config section, then reloads systemd.
- With `--enable-autorepair`, keeps the ADMIN timer stopped and worker timer
  disabled/service stopped. Runs exactly one `--no-send` ADMIN scan via `runuser`
  as `goalvision-admin-alerts`, using the new versioned release, the normal
  `/etc/goalvision-admin-alerts/admin-alerts.json` config and
  `/var/lib/goalvision-admin-alerts` state directory. Requires exit 0 and completed
  no-send evidence. Read-only SQLite checks require `repair_activation`, exclusions
  for all current active/pending episodes, no new repair-job rows, and no repair
  jobs belonging to the activation baseline. Both `queue/` and `running/` must
  be empty before and after the scan, including partial/non-JSON files.
- Only after all baseline checks pass, enables/starts the worker timer and
  restores the previously active ADMIN timer. A scan/check/activation failure
  disables the worker timer, stops its service, leaves ADMIN stopped, and retains
  the transaction for explicit rollback/review. It never clears the baseline,
  queue or SQLite history to force activation. Disabled installation skips the
  baseline scan and worker activation.

4. Inspect service startup/permissions and the installer-verified baseline report.
   No manual baseline scan is needed before worker activation. If installation
   failed, use the rollback below before restoring scheduled monitoring; do not
   enable the worker manually around a failed gate. Do not inject faults into PREMATCH. Let a
   genuine new episode trigger the first real job; review it before any proposal
   is accepted. If Codex auth refresh, sandbox/namespaces, DNS, or required CLI
   flags are incompatible with confinement, leave the worker disabled and review
   the setup; do not bypass sandboxing or copy credentials.

## Rollback and stop controls

A separately authorized root operator may stop only this worker:

```sh
systemctl disable --now goalvision-admin-autorepair.timer
systemctl stop goalvision-admin-autorepair.service
```

This leaves ADMIN queueing enabled and bounded; disable autorepair or use the
installer rollback to stop both queue processing and worker activation. A spool
`DISABLED` marker prevents unit starts but deliberately does not alter ADMIN's
incident alerting or queue ledger. No PREMATCH pause is needed.

Full installer rollback, including a partially applied v1 transaction:

```sh
/usr/bin/python3 operations/admin-autorepair/install_v1.py --apply --rollback
```

Rollback stops the worker, briefly drains the ADMIN timer, restores the original
ADMIN config, removes only this install's ADMIN override/worker units/config/link,
reloads systemd and restores the previous ADMIN timer activity. Original ADMIN
release files remain untouched. All SQLite/job history, source snapshots and
versioned releases remain on disk; never roll the ADMIN DB backward or delete
repair receipts. Review interrupted jobs by ID after rollback.

## Remaining limitations

- No actual Codex/model or hardened service execution was authorized/tested;
  offline success and unit syntax validation are not a host-runtime certification.
- OpenAI connectivity/authentication is necessary for a real job. The outer
  service permits network for Codex; it is not an OpenAI-only domain firewall.
  Shell network is disabled by the Codex sandbox, while prompts prohibit provider/
  Telegram use and escalation. Auto-approval/model adherence is not a substitute
  for the outer filesystem/service isolation or a future dedicated egress proxy.
- Read-only Codex home can make an expired authentication refresh fail closed.
  Required CLI flags fail closed if unsupported; only ephemeral is optional.
- Source snapshots need a separately reviewed refresh after source acceptance;
  the worker never fetches, updates or writes them.
- Job artifacts/ledger history are retained indefinitely. Monitor disk use and
  apply a separately reviewed archival policy; no automatic deletion is included.
- Correlated rules can each have a job: deduplication is per incident episode,
  not per correlated service execution. Capacity/rate limits bound the effect.
- Invalid spool inputs fail closed; repair them manually after inspection. Status
  inspection shows up to 100 jobs; use `--job` for an older exact ID.

## Implementation inventory and completed validation

Changed existing files:

- `TASKS.md`
- `app/admin_alerts/cli.py`
- `app/admin_alerts/store.py`
- `app/admin_alerts/delivery.py`
- `operations/admin-alerts/admin-alerts.json`

Added files:

- `app/admin_alerts/autorepair.py`, `app/admin_alerts/operator_jobs.py`
- `app/admin_autorepair/__init__.py`, `protocol.py`, `worker.py`
- `operations/admin-autorepair/goalvision-admin-autorepair.service`,
  `goalvision-admin-autorepair.timer`, `worker.json`, `run.py`, `install_v1.py`,
  `rehearse.py`, `test_offline.py`
- `tests/admin_autorepair/conftest.py`, `test_queue.py`, `test_worker.py`,
  `test_operator.py`, `test_repair_integration.py`
- This runbook.

Final guarded gate (2026-10-01): **367 passed, 79 subtests passed** across the full
ADMIN and repair suites plus adjacent shadow/quota packages:

- `tests/admin_alerts`: **206 passed**.
- `tests/admin_autorepair`: **69 passed**.
- `tests/test_lab_v2_shadow.py`: **63 passed**.
- `tests/adaptive_lab/test_quota_cli.py`: **29 passed**.

The focused installer/unit gate separately passed **20 tests**, including immediate
worker activation after baseline verification, active/pending episode exclusions,
nonzero/timeout/incomplete scans, missing baseline/exclusions, unexpected queued or
running files, hidden SQLite reservations, activation-history conflicts, failed
worker enablement and rollback. These 20 are included in the 69 repair tests above.
Real-network attempts, real Codex jobs, provider calls and Telegram calls: **zero**.
Static `systemd-analyze verify`, `git diff --check`, and whitespace checks on all
18 untracked implementation files passed. Gate evidence is retained locally in
`/tmp/admin-autorepair-final-20261001.{json,xml}`; fake rehearsal evidence is in
`/tmp/admin-autorepair-final-rehearsal-20261001/rehearsal.json`.
The fake rehearsal produced PATCH_READY with an identical source hash and one
STARTED plus one COMPLETED notification. HEAD remains the original
`59f051834a4a69ed4941cc78b767f5db0a126c33`; no worktree commit/push, installation,
service control, production state change or real credentials access occurred.


## Latvian operator status update — 2026-10-01

The narrow updater `operations/admin-autorepair/update_status_language.py` is
packaged as `update.py` with `operator_jobs.py` and pinned `metadata.json`.
It only accepts the installed R4 ADMIN module/route hashes, verifies the complete
base Python manifest, creates a separate ADMIN release, and changes only the
notification formatter. It drains ADMIN while its timer is paused, verifies the
new route, and restores the timer's prior activity. A switching failure restores
the previous route; failed staging releases are retained for review.

Run the packaged updater without arguments for a read-only plan. Root
`python3 update.py --apply` installs; `--apply --rollback` restores the saved
R4 ADMIN drop-in. Neither command starts a manual ADMIN scan or sends a test
message. Normal scheduled ADMIN delivery resumes according to its existing policy.
Existing notification bodies and receipts are not rewritten or replayed.
PREMATCH, worker configuration/source snapshots, activation baseline and spool
remain on R4. The narrow release records its new source commit in
`status-update.json`; worker source refresh remains a separate operation.


## Reviewed false delivery retirement — 2026-10-01

Incident `bd52a22acbc330714271ae9a` retained nine old aggregate delivery errors.
Read-only inspection of all nine immutable PREMATCH cycle-health records proved
27 `REJECTED_BEFORE_TRANSPORT / SELECTION_ORIGIN_OR_APPROVAL_INVALID` outcomes
and zero send attempts. R4 corrected new-event classification but did not retire
the stored incident; the old incident therefore continued 30-minute reminders.

The reviewed cleanup installs a narrow Store recurrence guard, then pauses/drains
only ADMIN, takes its scan lock and SQLite backup, and rechecks the exact incident
count/episode/generation, every retained source event and all nine source records.
Only proven false classification is set to INVALIDATED with immutable original
incident/outbox snapshots and source hashes. Sent, attempted and uncertain notices
and receipts remain unchanged. Only unattempted pending reminders are superseded.
There is no recovery notification or claimed Telegram delivery success.

The guard preserves exact old evidence replays as tombstones; different genuine
faults (including delayed evidence) and real recovery use a fresh stable identity.
Do not roll back this guard after retirement: older Store versions would suppress
that identity permanently. Failure before retirement can use normal route recovery.
The wrapper `apply_delivery_cleanup.py`, packaged as `apply.py`, is repeatable
after partial deployment. Use `sudo python3 apply.py --apply`; default is proof-only.
It never sends a message, changes Lab timers, or writes producer databases.
