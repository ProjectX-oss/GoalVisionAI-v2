# PREMATCH timer stagger package v2

PREMATCH_TIMER_STAGGER_HARDENING_READY_FOR_OPERATOR_PREFLIGHT

The approved weekly calendar is Sunday 22:48 Europe/Riga. Discovery, settlement,
observer and daily research retain their previously specified targets. All six
required timer pairs have zero identical triggers in the representative 48-hour
window and both DST transition windows, using systemd calendar evaluation.

Commit b286210 and its package are SUPERSEDED_DO_NOT_INSTALL. SUPERSEDES.json
identifies the old manifest digest. Use only this corrected v2 package.

No production installation has been performed. Root operator preflight remains
required, including protected ADMIN sender-state inspection. See
`docs/operations/PREMATCH_TIMER_STAGGER_HARDENING.md` in the source worktree for
commands, hashes, recovery behavior, test results, and evidence limitations.

Run every controller action with the trusted SHA256SUMS digest from that handoff.
Verify the digest and all manifest entries externally before executing Python.
Only the three supplied timer drop-ins may be installed. Original units remain
untouched. Root is required for changes and protected ADMIN/journal inspection.
