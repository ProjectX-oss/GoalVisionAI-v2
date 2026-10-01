# ADMIN incidents 5551793 / 421c897 — read-only triage, 2026-10-01

Status: NEEDS_MORE_EVIDENCE for monitor source; worker startup fix prepared, not deployed.

The scheduled PREMATCH cycle at 19:30 Riga completed at 19:36:46 with exit 0.
Three SINGLE and three COMBO receipts were independently verified. These facts
do not establish full ADMIN monitoring coverage.

Readable status for job 48cab99a1c6591528428427c is FAILED / CODEX_FAILED /
WORKER_INTERRUPTED, source_commit UNKNOWN, sequence 1 and elapsed 0. Its status
was created at 19:05:01 Riga. The expected job directory does not exist.
The worker recovery path synthesizes this status when a running-spool entry
has no valid status, so zero duration is not a measured Codex execution.

Deployed execute() still calls mkdir(mode=02770) before initial status/try.
The live unit has RestrictSUIDSGID=yes. Prepared commit 994bdf8 changes this
to 0770 and has 104 passing worker/protocol tests. Evidence strongly matches
that pre-execution failure path; the original syscall error was not exported.

The monitor incident DB is not readable by the current OS identity. No access
controls were changed or bypassed. The prepared operator probe opens only the
ADMIN SQLite DB with mode=ro/query_only, selects the two exact incidents and
exports bounded machine facts plus source_access and the exact worker status.
It does not instantiate the monitor, run Codex, launch services or send messages.

Operator command:

    bash /home/arvis/goalvision-operations/admin-check.sh

The script requests sudo only for the protected read and saves a private
operator-owned JSON. Return its ADMIN_DIAGNOSTIC_SAVED path for inspection.

Synthetic verification: exact incident selection, missing-ID handling,
credential/free-text omission and unchanged source DB hash PASS; shell syntax
PASS. No production probe was executed by the assistant. No deploy occurred.
