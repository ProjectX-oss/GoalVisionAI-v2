# PREMATCH timer stagger package — blocked draft

The exact requested Sunday 22:45 weekly calendar collides with settlement at :45.
`check` and a new `install` reject this package with `TARGET_CALENDAR_COLLISION`.
No production installation has been performed. Do not bypass the collision check.

The proposed Sunday 22:48 alternative has a separate passing proof, but is not
selected. An explicit scheduling decision and a newly hashed package are required.
See `docs/operations/PREMATCH_TIMER_STAGGER_HARDENING.md` in the source worktree for
commands, hashes, recovery behavior, test results, and evidence limitations.

Run every controller action with the trusted SHA256SUMS digest from that handoff.
Verify the digest and all manifest entries externally before executing Python.
Only the three supplied timer drop-ins may be installed. Original units remain
untouched. Root is required for changes and protected ADMIN/journal inspection.
