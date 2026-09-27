# ADMIN alerts v1.3.1: idle delivery and existing epoch resume

Status: **ADMIN_ALERTS_V1_3_1_READY_FOR_OPERATOR_PREFLIGHT**.

Base: corrected v1.3, `ee01244efd35c02acf542b9e13d540577ab800ed`.
Branch: `codex/prematch-admin-alerts-v1-3-1`.
This release is prepared locally. No production install, sender enablement, push,
Telegram/API request, or PREMATCH control was performed.

## Defect and delivery semantics

Sender enabled with no deliverable work defaulted missing delivery state to UNKNOWN, which was incorrectly classified as ADMIN_DELIVERY_DEGRADED.

The scan now reports informational `IDLE_NO_DELIVERY_WORK` with
`transport_verified_this_scan=false` when there is no eligible work and no retained
real error. Idle creates no incident or outbox work and supplies no recovery event.
`HEALTHY` remains backed by a validated, persisted delivery receipt.

Eligibility includes incident lifecycle, due time, correlation and the existing
activation episode. Dispatch applies these checks before Telegram validation.
Local token/configuration checks remain active, including during idle scans;
missing tokens still produce a genuine delivery configuration fault. An idle scan
calls neither Telegram `validate()` nor `send()`. Existing transport failures,
uncertain sends, permanent states and retry limits retain their prior behavior.
A deferred delivery with no recorded result reports `DELIVERY_DEFERRED`, without
inventing a successful transport test.

## Audited false incident cleanup

Each monitor scan, including a no-send scan, checks for the exact old default path:

- `ADMIN_DELIVERY_DEGRADED`, monitor/admin identity and `admin-transport` source;
- exact retained old Event document with occurrence/facts code `UNKNOWN`;
- matching original source evidence and one occurrence, first episode/count;
- absent delivery metadata: a retained validation/transport state vetoes cleanup;
- no prior notification, receipt, error, attempt count or attempt row for its outbox;
- only unattempted `PENDING` or already `SUPERSEDED` outbox history.

Unproven or contradictory cases remain actionable for review. Cleanup records
`IDLE_NO_DELIVERY_WORK_NOT_TRANSPORT_FAILURE` in the immutable invalidation audit,
including the original incident and complete original outbox snapshot. It marks
the incident `INVALIDATED`; unattempted pending notifications become `SUPERSEDED`
through the existing notification audit mechanism. Source evidence, occurrences,
timestamps, receipts, attempts and existing audits remain retained.

Future genuine delivery faults use a separate stable identity if the original
identity is an invalidated tombstone. Their normal delivery/recovery lifecycle
therefore remains available. No incident is deleted or falsely recovered.

## Existing activation boundary

The production epoch must remain exactly:

- ID: `ADMIN_NOTIFICATION_EPOCH_V1`;
- policy: `PRE_ENABLEMENT_EPISODES_SUPPRESSED_V1`;
- complete episode/generation snapshot, with `activation_review_required=[]`.

Upgrade preserves every byte of `admin.sqlite`, config and token. Resume opens
only a read-only in-memory copy of the database and writes only sender config.
Neither operation calls `prepare_epoch`, creates epoch rows, rewrites
`epoch_incidents`, or suppresses another backlog. The original enable operation
still refuses activation replay; the new controller explicitly directs operators
to the separate resume operation.

Existing suppressed episodes remain suppressed. New post-epoch incidents and
new recurrences of stable incidents follow corrected v1.3 episode/generation
eligibility. Resume sends no test message. A restored timer can subsequently
perform normal scans and deliver eligible real incidents.

## Package and local evidence

Prepared standalone package:
`/home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-1`.
The archive and manifest hashes are in
[PREMATCH_ADMIN_ALERTS_V1_3_1_PACKAGE.json](PREMATCH_ADMIN_ALERTS_V1_3_1_PACKAGE.json).
The builder pins the corrected v1.3 baseline manifest and verifies every baseline
file. Installation verifies both package manifests and unchanged ADMIN unit hashes.

The complete ADMIN suite passes with a real-network guard:
[tests](PREMATCH_ADMIN_ALERTS_V1_3_1_TESTS.json).
It includes idle scans/reporting, configuration/transport failures, receipt health,
conservative cleanup, attempted/uncertain vetoes, exact confirmation, malformed
activation/configuration rejection, database byte preservation, failure restoration,
ADMIN-only controls, restart, and the corrected v1.3 recurrence regressions.
No historical, model or PREMATCH suite was run.

[Synthetic rehearsal](PREMATCH_ADMIN_ALERTS_V1_3_1_REHEARSAL.json) proves one false
UNKNOWN invalidation, unchanged existing epoch, zero new epoch rows, safe snapshot
resume, unchanged resume database bytes, and zero live mutations/network/PREMATCH
actions. Synthetic sender enablement occurs only in disposable fixture config.

Reproduce locally from the checkout:

```bash
PYTHONPATH=. python3 operations/admin-alerts/test_v1_3_offline.py --output docs/operations/PREMATCH_ADMIN_ALERTS_V1_3_1_TESTS.json
python3 operations/admin-alerts/build_upgrade_v1_3_1.py --output /path/to/new-package --v1-3-package /path/to/corrected-v1-3-package
python3 -I /path/to/new-package/rehearse_v1_3_1.py --synthetic
```

## Operator preflight and upgrade commands

These commands are prepared for later operator execution. Codex has not run them
against production. Run from the reviewed, extracted package directory. Privileged
access is needed only for the operator's live files and ADMIN controls.

Before upgrade, read-only checks and host snapshot rehearsal:

```bash
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-1
sudo python3 -I control_v1_3_1.py check
sudo python3 -I rehearse_v1_3_1.py --installed v1.3
```

The rehearsal takes the existing ADMIN scan lock, reads the database bytes,
rejects SQLite sidecars/unsupported formats, and evaluates cleanup/resume in a
disposable copy. It controls no units and changes no live files. Token checks are
local; bot/destination network validation is not claimed. A busy scan lock causes
a safe refusal; retry the read-only command after the scan finishes.

Expected preflight: disabled sender, unfenced monitor, exact existing epoch and
complete snapshots. Before cleanup, resume readiness is false while the false
UNKNOWN incident remains actionable. The snapshot rehearsal should show
`would_invalidate_idle_unknown=1`, `epoch_preserved=true`,
`resume_ready_after_cleanup=true`, and all action/network counters zero.
If retained evidence differs, review the refusal instead of forcing invalidation.

Operator upgrade and read-only status:

```bash
sudo python3 -I control_v1_3_1.py upgrade
sudo python3 -I control_v1_3_1.py status
```

Upgrade requires sender=false. It fences and stops only the ADMIN timer/service,
verifies the baseline again under the scan lock, atomically exchanges the code
directories, then restores the timer only if it was previously active. Sender
remains false. No database migration, cleanup or network operation runs inside
upgrade. The next normal monitor scan may apply the audited cleanup.
If the timer was inactive, the operator can explicitly run the installed no-send
monitor as its existing service user:

```bash
sudo -u goalvision-admin-alerts python3 -I /opt/goalvision-admin-alerts/run.py --config /etc/goalvision-admin-alerts/admin-alerts.json --no-send
```

That monitor command writes ADMIN scan state and applies cleanup; the preflight,
status and rehearsal commands remain read-only against live state.

## Prepare and explicitly confirm resume

```bash
sudo python3 -I control_v1_3_1.py prepare-resume
sudo python3 -I rehearse_v1_3_1.py --installed v1.3.1
sudo python3 -I control_v1_3_1.py resume-sender --confirm RESUME_PRIVATE_ADMIN_EXISTING_EPOCH
sudo python3 -I control_v1_3_1.py status
```

`prepare-resume` checks the installed v1.3.1 manifest, sender=false, exactly the
existing epoch/policy, complete snapshot, no activation review, monitor unfenced,
local bot identity/private destination configuration, a readable protected token
matching the configured bot ID, exact `operator_confirmed_start=true`, and no
actionable UNKNOWN delivery incident. It reports the epoch, sender, actionable
post-epoch incidents, attempted/superseded notifications, and `resume_ready`.
Exit status is nonzero if preparation is not ready. No Telegram identity test or
private-chat test is made; existing operator validation is reused.

`resume-sender` requires the exact confirmation above. It repeats readiness checks,
fences/stops ADMIN, rechecks a read-only snapshot under the scan lock, atomically
sets sender=true with config readback verification, and restores the previously
active ADMIN timer. Config replacement/fsync, verification or timer failures restore
sender=false and leave ADMIN fenced. A failed restore of config itself is also
contained by the persistent fence; it requires operator review.

## Disable and rollback

```bash
sudo python3 -I control_v1_3_1.py disable-sender
sudo python3 -I control_v1_3_1.py rollback
```

Disable does not require token readiness; it sets sender=false under ADMIN fencing.
Rollback verifies and restores the saved corrected v1.3 code, preserves all ADMIN
database/audit/configuration history, sets sender=false, leaves `DISABLED` present,
and leaves the ADMIN timer stopped. Old code cannot safely reuse the invalidated
delivery identity, so rollback deliberately stays fenced. Do not remove that fence
or replay activation to bypass review.

Backup: `/opt/goalvision-admin-alerts-v1-3-1-v1-3-rollback`.
Transaction record: `/opt/goalvision-admin-alerts-v1-3-1-transaction.json`.
All control calls structurally allow only `goalvision-admin-alerts.service` and
`goalvision-admin-alerts.timer`; no daemon reload or PREMATCH control is allowed.
