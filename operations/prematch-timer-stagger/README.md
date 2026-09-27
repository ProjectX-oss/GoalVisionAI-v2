# PREMATCH timer stagger package v4

PREMATCH_TIMER_STAGGER_HARDENING_READY_FOR_OPERATOR_PREFLIGHT

Final schedules:

- Discovery: `*-*-* 09..22:00,30:00 Europe/Riga` (untouched).
- Settlement: `*-*-* *:05,15,25,35,45,55:00`.
- Observer: `*-*-* *:08,38:00`.
- Weekly stats: `Sun *-*-* 22:28:00 Europe/Riga`.
- Daily research: `*-*-* 04:12:00`.

Zone-less schedules use the pinned Europe/Berlin host timezone. Exactly four
OnCalendar-only drop-ins are allowed. Application code, Persistent, accuracy,
randomization, associations and enabled/inactive state remain unchanged.

Systemd/installed-tzdata proof covers all ten pairs in current 48-hour, spring
DST and autumn DST windows with zero exact collisions. Research moves three
minutes earlier than production; weekly moves two minutes earlier. Cadences,
including existing DST behavior, remain unchanged.

Persistent compatibility is proved from pinned original calendars. Typical common
windows are HH:00:10–HH:04:50 and HH:30:10–HH:34:50, conditional on observed normal
old triggers. Installation requires more than 60 seconds remaining, checks real
LastTriggerUSec for every active changed timer, and refuses outside a common
window before creating its lock/state. A forecast never substitutes for a run.
Check/status/proof expose common_safe_now and next_common_safe_window. Install
runs one foreground transaction, with rechecks, atomic file replacements and
rollback recovery. There is no staged/background installer or timestamp editing.

Both previous candidates and packages are SUPERSEDED / MUST NOT INSTALL:
46e680851fd8c64c5d003c14215de75128537542 (v2) and
a8bfc1fd30b2da3112284e436d11eec050d804e8 (v3). See SUPERSEDES.json for hashes.
Regressions reject old 04:15 research collisions and both 04:20 deployment cases.

No installation or production controls have been performed. Full protected ADMIN
preflight and normal post-install service evidence remain operator tasks.
See docs/operations/PREMATCH_TIMER_STAGGER_HARDENING.md in the source worktree
for the handoff, exact check/install/status/rollback/evidence commands, hashes,
and bounded recovery limitations. Verify the trusted SHA256SUMS digest and all
entries externally before executing Python; pass that digest to every action.

Evidence includes complete UTC calendars, all ten pair intersections, nearest
neighbors, original-versus-target cadence, common Persistent windows, systemd/
tzdata metadata, negative proofs and operations tests. Exact scheduled separation
does not guarantee non-overlapping worker runtimes or eliminate outage catch-up.
