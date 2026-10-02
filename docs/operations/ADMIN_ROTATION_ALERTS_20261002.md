# ADMIN rotation-gap reminder correction — 2026-10-02

Engineering: PASS. Operator deployment: VERIFIED. Natural monitor exit-0: PASS.
Post-deployment receipt-count stability: not independently read back.

## Operator report and diagnosis

The operator forwarded incident `c7df1386cf441d629cbc83b9`, dated
2026-10-01 20:12:09 Europe/Riga, with occurrence count 1, and reports frequent
repeated notifications. The identity exactly reproduces the installed V1
signature for service monitor, rule MONITORING_COVERAGE_DEGRADED, object
stdout-rotation. Its sources are ROTATED_INODE_LOST, FILE_TRUNCATED or
FILE_REWRITTEN. It predates the de-vig deployment.

Installed monitor base:
`/opt/goalvision-admin-alerts-releases/admin-monitor-compat-a28f2a6-20261002`.
Source worktree starts from `a3aa0866ccb0b2e22d9e43ebbf55893ea0f9106f`;
all installed admin_alerts Python files match before editing.

The existing enqueue policy reminds about OPEN historical rotation incidents
every 1,800 seconds even without a new occurrence. Generic stdout readability
does not resolve the distinct stdout-rotation incident, correctly retaining a
historical evidence gap. But the reminders make that old gap look like fresh
PREMATCH failures. Additionally, the old occurrence key is only the reason,
so another physical gap with the same reason cannot increment that episode.

The protected live ADMIN database is not readable by arvis; sudo -n requires a
password. No permissions or roles were changed. Before deployment, the exact retained subreason,
live state and receipt count had NOT been inspected. The supplied identity,
timestamp and count plus controlled reproduction establish the code defect;
the package includes a bounded read-only diagnostic for the exact incident.

## Correction

Four monitor modules change: model.py, sources.py, store.py and delivery.py.

- Keep the first rotation-gap notification and its existing bounded delivery
  retries. Once acknowledged, do not enqueue timer-only reminders without newer
  observed evidence.
- Apply the same eligibility check before transport to old queued/uncertain
  reminders. Preserve attempted/acknowledged/receipted rows; audit supersession
  only of never-attempted pending rows.
- Give distinct physical rotation/truncate/rewrite gaps deterministic occurrence
  identities using the persisted cursor serial and source identity. Replaying
  the same cursor/evidence remains idempotent.
- A new physical gap advances notification generation. Old uncertain bodies do
  not become the notification for the new gap. Existing cooldown/rate limits and
  transport failure guards still apply.
- Explain the retained historical-output gap and show an allowlisted reason code
  in new notification text.
- Do not mark the incident recovered, delete evidence, reset activation or clear
  global monitoring degradation. A historical gap can remain visible in the
  report after its duplicate reminders stop.
- Genuine ongoing READ_UNAVAILABLE, health/journal errors, unknown reasons and
  all unrelated incident reminders remain unchanged.

No PREMATCH, selection, odds, settlement, model, champion, Official or LIVE code
changes. SINGLE 1.30, COMBO no floor, today-only and early settlement stay active.
ADMIN Codex remains disabled.

## Verification

292 tests and 79 subtests PASS in 22.95 seconds, with socket/DNS disabled.
This covers the complete ADMIN-alert suite and relevant upgrade, false-delivery
retirement and disabled-worker regressions. Eighteen focused rotation tests are
included; do not add overlapping counts.

Controlled synthetic replay of the same incident over initial, +30m, +60m and
+24h scans: installed code sent four fake messages; corrected code sent one.
Both retained OPEN, count 1 and the original timestamps. No real message was sent.

Coverage includes first uncertain-send retry, actual new gaps, identical-content
repeated truncations, replay determinism, normal .1 rotation draining, legacy
pending/uncertain/permanent/exhausted reminders, attempt/receipt/epoch retention,
continued real-fault reminders, unknown-reason handling, secret-free text, exact
incident read-only diagnostic, monitor-only apply/rollback and disabled-Codex
guards. Changed modules compile. No production tests or manual scan ran.

## Operator package

Build from committed sources with:
`python3 operations/admin-autorepair/build_rotation_alerts.py`.

Pinned entry point: `/home/arvis/goalvision-operations/admin-rotation-fix.py`.

Read-only:
`python3 ~/goalvision-operations/admin-rotation-fix.py`.

Root-only exact incident inspection (no scan/send):
`sudo python3 ~/goalvision-operations/admin-rotation-fix.py --diagnostic`.

Separate operator apply:
`sudo python3 ~/goalvision-operations/admin-rotation-fix.py --apply`.

The transaction pins the full installed monitor manifest and four overlays,
pauses only the monitor timer, lets an active monitor finish naturally, protects
the worker/PREMATCH/weekly routes, and verifies Codex remains disabled. It does
not force a scan, send, worker job or PREMATCH cycle. Incident correction happens
only in subsequent natural monitor scans. No raw credentials or message bodies
are exposed by the diagnostic. It prints the exact reason/state/times and
aggregate outbox acknowledgement counts.

Rollback, only if separately needed:
`sudo python3 ~/goalvision-operations/admin-rotation-fix.py --apply --rollback`.

Rollback restores the exact previous monitor route; historical state remains
retained. It also restores the previous reminder behavior.

Evidence: `docs/evidence/admin_rotation_20261002/verification.json` and JUnit.
Operator readback/package pins are recorded after package preparation.


## Prepared package readback (before operator deployment)

- Implementation commit: `6a377873fc573831f526b110af73afc81520d984`.
- Package: `/home/arvis/goalvision-operations/admin-rotation-alerts-6a37787-20261002`.
- Read-only package validation PASS; all seven SHA256SUMS entries PASS.
- Existing ADMIN release still a28f2a6; candidate release not installed.
- Current de-vig PREMATCH preflight PASS with current_mode=ENABLED.
- ADMIN Codex service PID 0, inactive; worker timer disabled/inactive.
- Runtime deployment, real sends, manual scans, incident invalidation and source
  permission changes: none.
- Exact live incident subreason/receipt readback remains root-only. Operator apply
  prints the sanitized diagnostic; standalone --diagnostic is also available.

Pins and readbacks: `docs/evidence/admin_rotation_20261002/operator_package.json`.


## Operator deployment and independent readback

The operator applied the prepared package and supplied
`ADMIN_ROTATION_ALERTS_DEPLOYED` and `ADMIN_CODEX_STILL_DISABLED`. The new
monitor override was written at 2026-10-02 21:28:25 Europe/Riga.

The operator's root-only read-only diagnostic confirms exact incident
`c7df1386cf441d629cbc83b9`: stdout `ROTATED_INODE_LOST`, OPEN, occurrence count 1,
episode 1 and generation 1. First/last evidence is 2026-10-01 20:12:09 Riga;
49 SENT rows are acknowledged. Last send was 2026-10-02 21:11:47 Riga.
Thus the forwarded repetitions belong to one retained historical gap. These
counts are the operator-supplied deployment snapshot, not a later independent
query of the protected SQLite database.

Independent readback at 21:57:56 Riga:

- Installed release:
  `/opt/goalvision-admin-alerts-releases/admin-rotation-alerts-6a37787-20261002`.
- All 19 Python file hashes and manifest.json match the pinned base plus four
  reviewed overlays; no symlinks. Configured monitor route matches this release.
- Enabled/active monitor timer naturally triggered at 21:57:38 Riga; monitor
  completed at 21:57:39 with Result=success and ExecMainStatus=0.
- All six protected configured routes match package preparation, including the
  four PREMATCH services, weekly stats and disabled ADMIN worker.
- ADMIN worker remains inactive with PID 0; worker timer disabled/inactive.
- All 810 installed PREMATCH Python files match the de-vig manifest. Research,
  SINGLE 1.30, accuracy COMBO, today-only and early COMBO loss flags remain 1.
  No selection, champion or settlement code changed in this deployment.

The old de-vig deployment preflight now fails closed with
`PREPARED_CONFIGURATION_DRIFT`: its pinned ADMIN command, working directory and
monitor drop-in list precede this authorized monitor deployment. A full
configuration comparison confirms that this ADMIN route is the sole difference;
PREMATCH and all other protected command/route properties match. This is an
outdated operator-package configuration pin, not a de-vig runtime failure.
The pinned package was not edited or bypassed. Any future reuse of its apply or
rollback requires a fresh review against the current ADMIN route.

The old incident deliberately remains OPEN. The fix suppresses acknowledged
reminders without new evidence; it does not reconstruct missing historical logs
or assert monitoring coverage recovered. Natural service success does not by
itself prove the delivery count stayed at 49; a later protected diagnostic or
operator observation would establish that. No manual scan, production cycle,
provider request, test send, incident edit, permission change or agent deployment
was performed for this readback.

Evidence: `docs/evidence/admin_rotation_20261002/deployment_readback.json`.
