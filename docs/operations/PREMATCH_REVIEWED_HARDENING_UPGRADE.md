# PREMATCH reviewed hardening upgrade — 2026-09-25

**UPGRADE_PACKAGE_READY_FOR_REVIEW. New-pick publication remains disabled.**

Prepared on `codex/prematch-reviewed-hardening-upgrade` in `/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade`.
This is a focused operations upgrade of the already installed V2 system, containing
the accepted probability, publication-boundary and delivery-accounting fixes.
Application files are unchanged from the accepted commit. No new audit, model phase,
threshold change, migration, transport/provider call, manual cycle, deployment,
sudo execution, restart, push or merge was performed.

| State | Outcome of this task |
|---|---|
| Existing V2 installation | Verified already installed; stable old summary was stale |
| New reviewed upgrade package | Prepared and offline validated |
| Operator installation of this upgrade | **NOT PERFORMED** |
| First scheduled no-send tick on the new release | **NOT OBSERVED** |
| New-pick re-enablement | **NOT PERFORMED; remains disabled** |

The old installed release remains `/home/arvis/GoalVisionAI-prematch-release-installer-v2-20260925`, commit
`3d99f7dd5348e1440cb6c41eb9d91106c2a0b815`, application tree `c4e8da2e408fa5fef111efe0a653d5f5b49bbf6a`.
The known old package `/home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925` is unchanged; all 12 original
checksum entries pass. It and the older `prematch-v2-release-e120f1b` are retained
for comparison, not current upgrade instructions. Do not use their `apply` or
pre-V2 `rollback` for this upgrade, or delete drop-ins to make `apply` succeed.

The proposed isolated release is `/home/arvis/GoalVisionAI-prematch-release-reviewed-hardening-a7cb28b-20260925`, full accepted commit
`a7cb28ba5fcd87ada8ed8f4e78a18e0cec6021f2`, application tree `333405e4cf5d4ae0ab61f1341ef1cb5fa4e355ea`.
Its tracked files and directories are read-only and hash-bound. This is an immutable
release artifact by operations policy and filesystem permissions, not a claimed
root-only immutable filesystem flag. Do not modify it; prepare another version for changes.
The new versioned package is `/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925`.

**Installed state and unchanged arguments.** The verified service-specific file is
`/etc/systemd/system/<service>.d/90-reviewed-prematch-v2.conf` for all four services
below. There are no additional effective service/timer drop-ins. The known base-unit
fingerprints match the reviewed installer; no unknown drift or newer operational
fix was found. The installed discovery command has no `--send`, with observation
and labels still enabled. Settlement's existing `--send` and weekly report's
existing `--send` remain separate and unchanged.

Interpreter: `/home/arvis/GoalVisionAI/.venv/bin/python` → `/home/arvis/.local/share/uv/python/cpython-3.13.14-linux-x86_64-gnu/bin/python3.13`,
`Python 3.13.14`, SHA-256 `4419b7eee48ee6189e5237dfd885e4bdca5ac41b57a9e6eef1af761db5e2cbff`.
All four working directories remain `/home/arvis/GoalVisionAI`; service user remains
`arvis`, umask `0077`, `NoNewPrivileges=yes`. Credential path remains
`/home/arvis/GoalVisionAI/.env` (0600 arvis:arvis). Credentials were neither printed,
shell-sourced nor edited; only file fingerprints and metadata are retained.

Discovery's unchanged argument vector is:

```text
/home/arvis/GoalVisionAI/.venv/bin/python -P -m app.lab_v2_shadow controlled-cycle --max-calls 400 --settlement-reserve 100 --adaptive-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --football-context-root /home/arvis/goalvision-operations/football-context-v2 --football-context-registry /home/arvis/goalvision-operations/football-context-v2/reviewed-regulations.sqlite --label-v2-selections
```

Settlement remains `app.lab_combo settle --send --adaptive-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db`.
Observer remains `app.adaptive_lab.prematch observe --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --json`.
Weekly reporting remains `app.adaptive_lab.weekly_cli --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --send`.
All retain the interpreter's `-P -m` invocation. Quota 400, settlement reserve 100,
observation/registry paths, database paths and cadence are unchanged.
The unrelated adaptive-learning and all Official/LIVE configurations remain untouched.
`/etc/goalvision-prematch-release.conf` is fingerprinted but never replaced.

Service-specific environment files switch from `/home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925/release.env`
to `/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/release.env`; each contains only its release's
`PYTHONPATH`. Imported paths were verified offline with the installed interpreter,
from the installed working directory, with network syscalls denied:

- `app.adaptive_lab.prematch` → `/home/arvis/GoalVisionAI-prematch-release-reviewed-hardening-a7cb28b-20260925/app/adaptive_lab/prematch.py`
- `app.adaptive_lab.weekly_cli` → `/home/arvis/GoalVisionAI-prematch-release-reviewed-hardening-a7cb28b-20260925/app/adaptive_lab/weekly_cli.py`
- `app.lab_combo.cli` → `/home/arvis/GoalVisionAI-prematch-release-reviewed-hardening-a7cb28b-20260925/app/lab_combo/cli.py`
- `app.lab_v2_shadow.cli` → `/home/arvis/GoalVisionAI-prematch-release-reviewed-hardening-a7cb28b-20260925/app/lab_v2_shadow/cli.py`

The before-import paths and complete command/property inventory are in
`INSTALLED_STATE.json`. At capture `2026-09-25T19:48:52Z`, all four services
were inactive. Timer states/cadence were:

| Timer | State / enabled state | Calendar |
|---|---|---|
| `goalvision-adaptive-learning-observer.timer` | active / enabled | `{ OnCalendar=*-*-* *:00/30:00 ; next_elapse=Fri 2026-09-25 22:00:00 CEST }` |
| `goalvision-lab-combo-settle.timer` | active / enabled | `{ OnCalendar=*-*-* *:00/10:00 ; next_elapse=Fri 2026-09-25 21:50:00 CEST }` |
| `goalvision-lab-v2-discover.timer` | active / enabled | `{ OnCalendar=*-*-* 09..22:00,30:00 Europe/Riga ; next_elapse=Sat 2026-09-26 08:00:00 CEST }` |
| `goalvision-lab-weekly-stats.timer` | active / enabled | `{ OnCalendar=Sun *-*-* 22:30:00 Europe/Riga ; next_elapse=Sun 2026-09-27 21:30:00 CEST }` |

These are observations of the old release. Normal timer activity during preparation
is not an installation or a tick of the proposed release.

**Proposed diff.** Only four service-specific release environment references and
discovery's stdout sink change. Settlement/report execution flags remain in their
unchanged base units. Exact previews are packaged and hashed.

```diff
--- goalvision-lab-v2-discover.service (installed)
+++ goalvision-lab-v2-discover.service (proposed)
@@ -1,5 +1,6 @@
 [Service]
 EnvironmentFile=
-EnvironmentFile=/home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925/release.env
+EnvironmentFile=/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/release.env
 ExecStart=
 ExecStart=/home/arvis/GoalVisionAI/.venv/bin/python -P -m app.lab_v2_shadow controlled-cycle --max-calls 400 --settlement-reserve 100 --adaptive-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --football-context-root /home/arvis/goalvision-operations/football-context-v2 --football-context-registry /home/arvis/goalvision-operations/football-context-v2/reviewed-regulations.sqlite --label-v2-selections
+StandardOutput=append:/var/log/goalvision-prematch/discovery-output.log
--- goalvision-lab-combo-settle.service (installed)
+++ goalvision-lab-combo-settle.service (proposed)
@@ -1,3 +1,3 @@
 [Service]
 EnvironmentFile=
-EnvironmentFile=/home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925/release.env
+EnvironmentFile=/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/release.env
--- goalvision-adaptive-learning-observer.service (installed)
+++ goalvision-adaptive-learning-observer.service (proposed)
@@ -1,3 +1,3 @@
 [Service]
 EnvironmentFile=
-EnvironmentFile=/home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925/release.env
+EnvironmentFile=/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/release.env
--- goalvision-lab-weekly-stats.service (installed)
+++ goalvision-lab-weekly-stats.service (proposed)
@@ -1,3 +1,3 @@
 [Service]
 EnvironmentFile=
-EnvironmentFile=/home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925/release.env
+EnvironmentFile=/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/release.env
```

| Drop-in | Installed SHA-256 | Proposed SHA-256 |
|---|---|---|
| `goalvision-lab-v2-discover.service` | `136cdaa8e4f2dc4416f6e50e7168f14c669853678f71f97351fb4ec3cddbc69f` | `cbc2d17ec75e1804e70919126019037da9b3aace1bd3528cc5e39f7bfbd2cb56` |
| `goalvision-lab-combo-settle.service` | `3939a0c4e8dcd82bc56d34ba7c12d21b8b21afb22da359d9e1790419300a42ca` | `3923460fbbf879b3ba2e5a2de6dc675ad3ad7b2f8f5518e028f791a613ca190e` |
| `goalvision-adaptive-learning-observer.service` | `3939a0c4e8dcd82bc56d34ba7c12d21b8b21afb22da359d9e1790419300a42ca` | `3923460fbbf879b3ba2e5a2de6dc675ad3ad7b2f8f5518e028f791a613ca190e` |
| `goalvision-lab-weekly-stats.service` | `3939a0c4e8dcd82bc56d34ba7c12d21b8b21afb22da359d9e1790419300a42ca` | `3923460fbbf879b3ba2e5a2de6dc675ad3ad7b2f8f5518e028f791a613ca190e` |

**Upgrade transaction and recovery.** `upgrade_prematch_reviewed.py` reuses the
byte-identical reviewed `install_prematch_v2.py` primitives for the shared nonblocking
installer lock, exact unit/drop-in checks, literal command rendering, atomic file
replacement and service-start gates. It does not call the old `apply` or rollback.
The explicit upgrade requires all four exact currently installed no-send drop-ins.
Before writing, it validates release commits/trees/cleanliness, every release file,
interpreter/dependency files, credential fingerprint, environment files, base units,
timer units, effective command/environment/sinks and known configuration directories.
Unloaded extra drop-ins, changed quota/paths and concurrent installer operations fail
closed. Any drift requires review; no blind replacement of newer operational fixes.

The operator action records exact prior bytes, proposed bytes, manifest digest and
previously active timers in the fsynced, root-owned recovery journal
`/var/lib/goalvision-prematch-upgrade/transaction.json` (0640 root:arvis, directory 0750).
It pauses only these four timer triggers, creates temporary runtime start conditions
for all four services, reloads the gates, and drains active/transitional services
(up to 30 minutes). No service is stopped or restarted. It revalidates after draining,
writes all four compatible drop-ins behind the gates, verifies them with systemd,
reloads and checks the effective configuration, removes gates and restores only the
previously active timers. Disabled/inactive timers are not enabled. Persistent timers
may naturally deliver a due scheduled tick when resumed; this is not a manual test cycle.

On handled failure, exact prior compatible service bytes are restored and verified
while gated, then prior active timers resume. If restoration itself fails, gates and
the journal remain for explicit `recover`; do not delete either. The recovery command
also handles a recorded interrupted partial switch, accepting only recorded old/new
bytes and known gates, never unknown drift. After reviewing/fixing the administrative
failure, the one-line compatible recovery command is:

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python -E -B /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/manifest.json recover --sha256 10afc86a3da97dd24ee961010433dd455b53e644469060049def20bfa906a7b7
```

After a completed upgrade, the same command returns all four services to the prior
installed V2 release, always without new-pick `--send`. Any further disabled observation
or label controls stay disabled. During interrupted transactions it restores the
journal's exact previous configuration. It never rolls back a database or removes
claims, receipts, snapshots, results or predictions. Protected logs and rotation
configuration are retained on recovery so evidence is not discarded. If the host
cannot reload or restore timers, recovery must finish before normal scheduling resumes.
The prior release must remain available for recovery.

After upgrade the same pinned command accepts `disable-new-picks` (idempotent) or
`disable-data-labels` (disables observation and labels, preserves no-send). It has
no re-enable action. These controls validate the upgraded output configuration and
preserve any previously disabled capability. Do not invoke old-package controls
against the new drop-ins.

**Protected output.** Current discovery stdout is `null`; stderr is `journal`.
The proposal uses direct `StandardOutput=append:/var/log/goalvision-prematch/discovery-output.log`,
without changing ExecStart or adding a pipe/wrapper. Process exit status is preserved.
The installer creates a root:arvis directory 0750 and root:arvis file 0640; systemd opens
the service output descriptor. The operator `arvis` can read retained facts but cannot
replace or truncate the root-owned file through its path. No extra debug logging,
raw headers, API payload dump, credentials or telemetry service is introduced.
Accepted exception handling retains typed facts and omits exception text; the existing
Lab transport redaction regression also passed.

`/etc/logrotate.d/goalvision-prematch-reviewed` uses the existing active/enabled
`logrotate.timer`: daily, `maxsize 8M`, 14 rotations, `maxage 14`, compression with one
cycle of delay, and create 0640 root:arvis. It renames files; no `copytruncate`, size
clipping or line truncation. An in-flight 30-minute maximum run may finish writing its
renamed `.1` file before compression the following day. **8 MiB is a rotation-time
threshold, not a hard byte cap between daily checks**; record size is deliberately
not capped because prediction IDs, acknowledgements, receipt/cycle persistence status
and reconciliation flags must remain complete. Inspect both the current file and `.1`
after rotation. Retention is bounded by 14 rotations; maxage is evaluated on rotation.
Archive any real unresolved incident through separately reviewed operations before its
retention expires. Existing logrotate configuration/timer/binary are fingerprinted.

The log does not exist on the host yet; no production size/ownership claim is made.
Offline tests verified creation modes with fake ownership calls, complete accepted
persistence-failure facts, exit status 7 passthrough, an over-8-MiB record without
truncation, and actual rotation of a disposable file with full prior contents retained.
Exact production logrotate configuration parsed; its root `su` check was rejected as
expected under the unprivileged reviewer. A disposable rotation substituted only its
path and owner. Privileged log setup is still an operator installation check.
**Exit code 0 alone never proves successful publication.** Inspect delivery status,
`publication_cycle_persistence.persisted`, per-delivery acknowledgement,
`receipt_persisted`, and `reconciliation_required`; an acknowledgement with no durable
receipt remains unresolved, never a confirmed publication or an automatic retry.

**Read-only history and compatibility.** `HISTORY_CHECK.json` was captured at
`2026-09-25T19:50:22.920487+00:00` with `mode=ro`, `query_only`, one read transaction per
database, a 15-second progress deadline per database, and at most 200 detail rows.
It is not a simultaneous cross-database snapshot. No database was copied, migrated,
rewritten, repaired or reconciled. The reusable `prematch_upgrade_history.py` performs
only these bounded reads; it does not instantiate writable publication repositories.

- 118 delivery claims and 118 receipts; zero unreceipted claims, unknown markers or
  economic claims lacking receipts. No unreceipted PREMATCH weekly claim/unknown marker.
- 53 confirmed single publications and 8 confirmed combos; pending settlements are
  three singles (messages 129, 130, 131) and one combo (message 132). Full immutable
  prediction IDs are retained in the history report. Safe scheduled settlement continues.
- No acknowledged-but-unpersisted facts were found within the latest 200 retained
  publication cycles. Old records lack the new analysis/delivery fields; null means
  unavailable, not success. The old stdout sink discarded output, so absence of a
  receipt/output cannot prove a send never happened. No missing receipt was counted
  as confirmation.
- Observation stores passed SQLite `quick_check`: 519 readiness events, 483 retained
  sources, 488 source receipts, four snapshots; all files 0600 arvis:arvis. This is a
  storage/compatibility check, not a new full semantic/model audit.
- Registry verification using the accepted read-only registry implementation passed
  for four records. PREMATCH observer store has 333 runs at this capture.

The existing protected first-failure log
`/home/arvis/goalvision-operations/prematch-v2-first-failed-cycle.log` was also read
within a 1 MiB bound: 69,103 bytes, mode 0600, SHA-256
`535310141f1066f096039057c15b487326e4c2960fab63c6b9bed63eeef6e17e`.
It contains zero occurrences of `acknowledgement_received`, `receipt_persisted`,
`reconciliation_required` or `LAB_PUBLICATION_CYCLE_PERSISTENCE_FAILED`. No raw log,
exception text or headers were exported. Those missing markers are a limitation,
not proof of non-delivery.

No real unresolved delivery was identified within these bounds. If subsequent reads
or retained output reveal one, make it an explicit **future new-pick re-enable blocker**
requiring separate reviewed resolution. Never auto-resend, reconcile, rewrite or drop
history; it does not justify stopping safe settlement or observation.

**Validation and binding.** Final focused network-blocked run: **243 passed (6.38s)**,
covering the new upgrade tests plus existing installer, probability/publication/delivery,
settlement, labelled cohort/report and schedule regressions. Commands and full results
are in `TEST_RESULTS.json`; no broad historical/ML audit suite was repeated. All
installer service-manager commands were fake, databases disposable, and application
network syscalls denied by the existing seccomp launcher. Staged systemd syntax
verification passed without daemon reload. The packaged read-only `check` returned
`previous`, `new_picks=false`, `observe=true`, `labels=true`, `journal_pending=false`.

| Artifact | SHA-256 |
|---|---|
| Manifest (operator pin) | `10afc86a3da97dd24ee961010433dd455b53e644469060049def20bfa906a7b7` |
| Upgrade installer | `77e5e72adcda077418cbd5009400e6a7f23f39f64b8331864f182fc187686d52` |
| Unchanged reviewed V2 helper | `97535e9c0c1888cc4b9f2c0a9656111ee87499dfc0c34d1ef842543efa6603d5` |
| Proposed environment | `5f38b6b663929320907fc18926a971b2c397c45e1e141fa245d3e99e5556484d` |
| Complete release-file map | `6db71dbee367a962be07d5fb145e863328678ac68d4bee06023014833933f320` |
| Interpreter/dependency-file map | `8c8d666bfeee97bdd67b3aced4152035a5abbc23b5466463957bf9c82b8c4ce5` |
| Test results | `918d8985d02ca4968c461cf80dc2a7ffbde1b5fc1f8508a2d9d79892a20095a2` |

The manifest binds installers, environment, proposed/before drop-ins, release files,
interpreter/dependency contents, tests and bounded history evidence. `SHA256SUMS`
covers the package files, including this report. The committed
`PREMATCH_REVIEWED_UPGRADE_PACKAGE_REVIEW.json` binds that checksum index and every
package file. Package and release paths are intentional absolute operator pins.

**Operator installation after review — one line:**

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python -E -B /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/manifest.json upgrade --sha256 10afc86a3da97dd24ee961010433dd455b53e644469060049def20bfa906a7b7
```

This command is provided for the operator and was **not executed**. It requires
operator review and root access for service-specific configuration/log ownership.
Do not manually invoke discovery, publication or settlement to demonstrate success.

**Read-only post-install checks** (also available before installation):

```bash
/home/arvis/GoalVisionAI/.venv/bin/python -E -B /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/manifest.json check --sha256 10afc86a3da97dd24ee961010433dd455b53e644469060049def20bfa906a7b7
```

After operator installation expect `release_state=upgraded`, `new_picks=false`,
`observe=true`, `labels=true`, no pending journal. The check verifies exact imported
release bytes and effective executable/environment/arguments; it does not invoke a cycle.
Inspect the four services with `systemctl show ... -p ExecStart -p EnvironmentFiles
-p WorkingDirectory -p DropInPaths -p StandardOutput -p StandardError -p ActiveState`
and their timers with `systemctl list-timers --all`. Do not request a full environment dump.
Use `stat -c '%a %U %G %s %n' /var/log/goalvision-prematch/discovery-output.log`
and `systemctl show logrotate.timer -p ActiveState -p LastTriggerUSec` to check output
ownership, size and rotation scheduling. Read full JSON records locally without
clipping required IDs/acknowledgements. Keep any incident evidence protected.

For a fresh bounded history view, with network denied:

```bash
PYTHONPATH=/home/arvis/GoalVisionAI-prematch-release-reviewed-hardening-a7cb28b-20260925 PYTHONDONTWRITEBYTECODE=1 /home/arvis/GoalVisionAI/.venv/bin/python /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/offline_test_runner.py /home/arvis/GoalVisionAI/.venv/bin/python -P /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/prematch_upgrade_history.py
```

Then observe only the next normally scheduled no-send tick. Verify its timestamp is
after installation, actual accepted release/configuration, `publication_requested=false`,
`publication_enabled=false`, zero attempts/Telegram sends, no transport construction,
analysis/observation outcome and complete output persistence facts. Report that tick
separately from installation. Do not infer it from a service exit code or old-release tick.

**Later re-enable prerequisites.** Separate explicit authorization/review is required
for new-pick publication. First complete operator installation and verify the first
scheduled no-send tick, protected output/rotation, compatible settlement/reporting,
registry/observation availability and unchanged quota/cadence. Refresh the bounded
claim/receipt/history check and resolve any real unknown or acknowledged-unpersisted
delivery in a separate review. Legacy previews need fresh accepted normalization and
final publication decisions; do not relabel or rewrite them. Do not enable a new
model, change thresholds, or use old installer `apply` as an enablement shortcut.

There are no preparation blockers. Operator installation, the new release's first
scheduled no-send tick and later publication authorization remain outstanding,
independent states. Old stdout loss is an evidence limitation, not a confirmation
of delivery/non-delivery and not a reason to stop safe observation or settlement.
