# PREMATCH timer stagger package v3

PREMATCH_TIMER_STAGGER_HARDENING_READY_FOR_OPERATOR_PREFLIGHT

Daily adaptive research moves from 04:15 to 04:20 in the host timezone,
Europe/Berlin. Settlement runs at 04:15 and 04:25 around it. Discovery stays
unchanged; settlement, observer and weekly stats retain the approved targets.
All ten pairs across all five timers have zero exact collisions in the current
48-hour window and both DST windows, evaluated by systemd with installed tzdata.
Cadences are preserved, including weekly cadence and existing DST behavior.

Commit 46e680851fd8c64c5d003c14215de75128537542 and the v2 package are
SUPERSEDED / MUST NOT INSTALL. SUPERSEDES.json identifies their hashes and also
retains the earlier v1 supersession. The superseded 04:15 research schedule is
proven to collide daily and is rejected before any deployment writes.

Only FOUR supplied timer drop-ins may be installed: settlement, observer, weekly
stats and daily research. Discovery has no drop-in. Original units remain
untouched. This is a scheduling-only package with no application changes.

No installation or production service control has been performed. Root operator
preflight remains required, including protected ADMIN sender-state inspection.
See docs/operations/PREMATCH_TIMER_STAGGER_HARDENING.md in the source worktree
for exact check/install/status/rollback/evidence commands, hashes and limitations.
Verify the trusted SHA256SUMS digest and every manifest entry externally before
executing Python; pass that digest to every controller action.

Evidence includes every evaluated UTC trigger, all ten pair intersections,
04:15 / 04:20 / 04:25 research separation, original-versus-target cadence,
systemd and tzdata versions, zoneinfo hashes, and superseded-v2 collision proof.
Operator proof/check/install regenerate the current window at execution time,
starting at the current UTC hour and ending 48 elapsed hours later.
Exact trigger separation does not guarantee that worker runtimes cannot overlap.

Operator constraint: with the existing persistent catch-up guard, the normal
safe windows for daily research and weekly stats do not intersect. The current
all-at-once install command therefore refuses normal installation. A separately
reviewed catch-up-safe deployment procedure is required; this release is ready
for operator preflight only. See the handoff before using the install command.
