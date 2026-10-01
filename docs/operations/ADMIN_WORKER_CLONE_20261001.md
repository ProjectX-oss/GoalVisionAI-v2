# ADMIN worker reviewed-source clone fix — 2026-10-01

Status: root cause reproduced, code and offline validation PASS.
Production follow-up BLOCKED pending separate operator deployment.
Natural end-to-end Codex execution still NEEDS_MORE_EVIDENCE.

## Runtime findings

The operator-deployed admin-io-startup-0a3e42a release restores stdout readability
and lets the worker pass initial job-directory creation. Natural monitor scans
finish with exit 0 and both ADMIN timers remain active.

Three subsequent legitimate worker jobs fail in 0.020–0.024 seconds with
WORKER_ERROR, sequence 3 and source commit
fc4a740f4abfa5aaadc5effb105dcaf3381310f0.
Each directory contains incident.json, prompt.txt and result.json, with no clone
or Codex invocation artifact. The jobs concern PREMATCH INTEGRITY_FAILURE /
SELECTION_ORIGIN_OR_APPROVAL_INVALID. Their underlying PREMATCH incidents are
separate from this worker infrastructure fix; their recency/resolution is not
inferred from the queue creation time.

The exact deployed clone command, run as the ordinary worker user into a
disposable directory, returns exit 128 and Git's dubious-ownership rejection.
The reviewed bare source is root-owned (0755); Git is 2.43.0. The source HEAD read
succeeds, but command-line safe.directory does not reach the upload-pack child.
This explains the observed failure point without changing source ownership or
assuming that Codex ever started.

## Change

The worker uses --no-local with the local file transport and an explicitly
shell-quoted upload-pack command. The child trusts only the exact configured,
resolved source path. Hooks and filesystem monitors stay disabled, other
protocols remain forbidden, and submodules are not recursed.

The clone is independent: no object hardlinks or alternates, no origin remote
before Codex, and checkout pinned to the captured reviewed commit. Source
repositories, global Git config and service sandbox settings remain untouched.

A fixed, bounded failure.json records phase, error category and numeric return
code/errno. It excludes exception text, stderr, command arguments and credentials.
The established public worker status schema stays unchanged.

## Verification

- 333 ADMIN/Auto-Repair tests and 79 subtests PASS in 39.98 seconds.
- Real reviewed-source reproduction: old clone exit 128, corrected clone exit 0,
  correct HEAD, no alternates. No Codex job or provider request was made.
- Regression covers child ownership trust, shell quoting, independent objects,
  source immutability, diagnosis-only lifecycle and sanitized phase evidence.
- Worker-only installer tests cover apply/idempotency/rollback, reload failure,
  protected-route drift, busy-worker refusal, inactive timers and helper hash drift.
- Local Codex --help succeeds and advertises all flags required by the worker.
  This proves CLI compatibility only; it does not prove a complete Codex task.

Evidence: docs/evidence/admin_worker_clone_20261001/verification.json.

## Prepared operator package

Package: /home/arvis/goalvision-operations/admin-worker-clone-20261001
Entry point: /home/arvis/goalvision-operations/admin-clone-fix.py

Read-only validation:

    python3 ~/goalvision-operations/admin-clone-fix.py

After operator approval:

    sudo python3 ~/goalvision-operations/admin-clone-fix.py --apply

Rollback after approval:

    sudo python3 ~/goalvision-operations/admin-clone-fix.py --apply --rollback

Only the worker release/route changes. The package reuses the tested ADMIN route
transaction, pauses only the worker timer, waits at most 60 seconds for an active
job, and never kills or starts a job. Monitor and PREMATCH routes are compared
before and after. A failure restores the previous worker route and timer state.
The old io-startup drop-in remains intact beneath a new dedicated clone-fix
drop-in, so rollback restores the already-fixed 0770 worker release.

No automatic deployment, job retries, manual discovery/research cycles, provider
calls, Telegram tests, prediction policy changes, Official changes, LIVE enablement
or champion promotion. After deployment, verify a new legitimate natural worker
job; preserve the earlier failed-job history.

## Changed files

- app/admin_autorepair/worker.py
- tests/admin_autorepair/test_worker.py
- operations/admin-autorepair/update_io_startup.py (shared transaction hooks)
- operations/admin-autorepair/update_worker_clone.py
- tests/admin_autorepair/test_worker_clone_upgrade.py
- ADMIN_IO_STARTUP_20261001.md, this report, both evidence records and TASKS.md.

Git commit: the commit containing this report on fix/admin-worker-startup-20261001;
the immutable operator package records its full source commit.
