# ADMIN stdout rotation and worker startup — 2026-10-01

Status: PASS in tests; deployment and natural monitoring/worker execution pending.

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

The worker still requests mkdir(02770) before initial status and exception
handling, under RestrictSUIDSGID=yes. The prepared 0770 change (994bdf8) keeps the
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

A successful deployed readback and next natural ADMIN scan must confirm stdout
coverage recovery. Actual Auto-Repair execution remains unproven until a new
legitimate job occurs. The package does not retry old recovered incidents or
turn a historical generic failure into an unsupported root-cause claim.

Changed files: app/admin_alerts/sources.py; tests/admin_alerts/test_monitor.py;
operations/admin-autorepair/update_io_startup.py;
tests/admin_autorepair/test_io_startup_upgrade.py; this runbook, evidence and
TASKS.md. The package includes the existing 994bdf8 worker startup change.
