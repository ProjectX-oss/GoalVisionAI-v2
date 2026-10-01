# ADMIN stdout rotation and worker startup — 2026-10-01

Status: deployment, stdout readback and natural monitor execution PASS.
The source-clone follow-up is now deployed; full Auto-Repair execution still
NEEDS_MORE_EVIDENCE until a new legitimate job occurs.

## Findings

The operator's bounded diagnostic reports both submitted incidents RECOVERED:
5551793c5b77956d7db042f5 (health coverage) and 421c8977ff14a1c4c99ebc27
(discovery TIMER_INACTIVE). The first incident now retains healthy evidence,
so its original unhealthy reason is not available and is not invented here.

The latest source_access independently reports stdout READ_UNAVAILABLE.
The ADMIN account has directory --x and current/.1 file r-- ACLs. On inode
change, the old tail reader called parent.iterdir(), which requires directory
read permission. The installed logrotate policy uses compress/delaycompress;
only .1 is the supported uncompressed predecessor. Discovery output-window
verification already uses that exact file pair.

The reader now looks up .1 directly. It drains the saved inode before switching
to the replacement, retains byte/line limits and explicit lost-inode evidence,
and keeps real unreadable files degraded. ACLs and account groups are unchanged.

The former worker requested mkdir(02770) before initial status and exception
handling, under RestrictSUIDSGID=yes. The now-deployed 0770 change (994bdf8) keeps the
sandbox intact. The missing job directory and synthetic zero-duration recovery
status strongly match a pre-status failure; the original syscall trace remains
unavailable. WORKER_INTERRUPTED is not proof that Codex itself executed.

## Verification

- 313 ADMIN/Auto-Repair tests + 79 subtests PASS, 28.25 s.
- 11 separate installer tests PASS, 0.15 s: dual-route apply, replay, rollback,
  partial mutation failure, readback failure, hash drift, symlink refusal,
  active-job no-kill refusal and preservation of inactive timers.
- Source read tests deny directory enumeration and still drain .1/current;
  a missing predecessor reports a gap, and an unreadable archive fails closed.
- Existing worker regression simulates special-bit denial and completes a
  synthetic clone/job lifecycle; no real Codex task was started during this work.

Structured evidence: docs/evidence/admin_io_startup_20261001/verification.json.

## Operator package

Prepared package: /home/arvis/goalvision-operations/admin-io-startup-20261001.
Short entry point: /home/arvis/goalvision-operations/admin-fix.py.
Read-only verification:

    python3 ~/goalvision-operations/admin-fix.py

Only after explicit operator approval:

    sudo python3 ~/goalvision-operations/admin-fix.py --apply

Rollback after approval:

    sudo python3 ~/goalvision-operations/admin-fix.py --apply --rollback

The package creates separate immutable monitor and worker releases, changing
only app/admin_alerts/sources.py in the monitor and app/admin_autorepair/worker.py
in the worker. It routes the two ADMIN services with dedicated drop-ins.
Both ADMIN timers are paused briefly; active services must finish within 60 s
or installation refuses and restores timers. Active jobs are never killed.
Before resuming prior scheduling, a pure read-adapter probe runs as the actual
ADMIN account and must prove stdout readability. It does not run a monitor
scan, mutate incident state or send anything. Failures restore both routes.

PREMATCH routes are compared before/after and never controlled. Existing
incidents, spool jobs, delivery receipts, credentials, source repositories,
ACLs and sandbox restrictions are not altered. Failed jobs are not requeued.
After resume, already-authorized timers operate normally. Rollback changes
routes only; it never rolls back databases or deletes historical evidence.

## Remaining evidence

The operator applied both releases at admin-io-startup-0a3e42a-20261001.
Full Python-tree hashes, manifests, dedicated drop-ins and effective routes PASS.
Both timers are active; repeated natural monitor invocations finish with exit 0.
The supplied pure readback reports read_available=true, 17 records, 37,111 bytes.
ROTATED_INODE_LOST preserves a real historical log gap; it does not mean the
current log remains unreadable. Current protected incident/source-access state
has not been independently re-exported, so complete incident recovery is not claimed.

Natural worker jobs now create job artifacts and record the reviewed source HEAD.
Three observed jobs terminate with WORKER_ERROR, sequence 3, before any clone or
Codex invocation artifact. Their exact old clone command reproduces Git's
dubious-ownership rejection against the root-owned reviewed snapshot.
This separate blocker is addressed by the operator-deployed worker-only follow-up:
docs/operations/ADMIN_WORKER_CLONE_20261001.md.

Deployment evidence: docs/evidence/admin_io_startup_20261001/deployment.json.
No failed jobs were retried, no manual service cycles or test messages were sent,
and PREMATCH routes remain unchanged.

Changed files: app/admin_alerts/sources.py; tests/admin_alerts/test_monitor.py;
operations/admin-autorepair/update_io_startup.py;
tests/admin_autorepair/test_io_startup_upgrade.py; this runbook, evidence and
TASKS.md. The package includes the existing 994bdf8 worker startup change.
