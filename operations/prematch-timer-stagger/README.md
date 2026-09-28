# PREMATCH forward evidence rotation fix — v4 evidence r1

PREMATCH_FORWARD_EVIDENCE_ROTATION_FIX_READY_FOR_REVIEW

Timer stagger v4 (`b32ede450e19ecac771cde5e9a1d03a6668e3746`) is already
installed, as reported by the operator on 2026-09-28. This revision changes the
operations evidence reader only. Use the `evidence` action with the existing
successful installation timestamp; do not install or re-arm timers again.

Discovery evidence reads the current uncompressed log first and determines its
earliest valid `goalvision-lab-v2-operator-cycle-v1` timestamp. If that timestamp
is at or before `--since`, older numbered rotations are outside the requested
window. Otherwise it reads `.1`, `.2`, etc., stopping as soon as coverage reaches
`--since`. Missing or ambiguous required rotation numbers fail closed. Required
`.gz` rotations still refuse with `DISCOVERY_ROTATION_REQUIRES_OPERATOR_REVIEW`;
no gzip decompression is attempted. Older rotations are listed by filename only.

Selected files share a 64 MiB read budget and a 100,000-line budget. Missing,
unreadable, empty, symlinked or non-regular required files cannot supply coverage.
Malformed/non-cycle lines never count as evidence; malformed cycle timestamps
refuse. Timestamp ranges select files; existing journal matching still requires
scheduled starts and cycle outputs, so a temporal gap cannot become a PASS.
The report lists `discovery_output_files_read`,
`discovery_output_files_ignored_outside_window`, and per-file timestamp ranges.

The new frozen review package is
`prematch-timer-stagger-v4-evidence-r1-20260928`. Its manifest covers this reader,
README and updated operations test evidence. The original installed v4 archive
and frozen directory are retained unchanged. See the current section of
`docs/operations/PREMATCH_TIMER_STAGGER_HARDENING.md` for hashes and the read-only
evidence command. No production evidence run was performed for this revision.

## Historical v4 installation handoff (2026-09-27)

The remaining installation notes describe the original v4 release. Installation
has since succeeded; these are retained for audit and are not instructions to
repeat installation for this evidence fix.

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
