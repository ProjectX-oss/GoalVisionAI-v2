# PREMATCH Lab: same-day discovery and publication — 2026-10-01

Status: root cause, 525 offline regressions, operator deployment and the first
two post-deployment natural cycles PASS. Date scope and receipts are verified;
this is not a prediction-quality or broader AI/ML deployment approval.

## Root cause and observations

The user reported on 1 October that newly published picks were for 2–3 October.
The screenshots show Al Ain – Ajman (2 October, 16:15 Riga) and Switzerland –
Slovenia (3 October, 21:45 Riga).

The deployed CLI defaults to a three-day UTC discovery horizon. The runner
also restores upcoming global and tracked fixtures from earlier cycles without
a calendar-day filter. The publication clock checks 09:00–23:00 Riga hours but
does not require the fixture date to match the publication date. The SINGLE
rank prioritizes probability across the full pool, so a future fixture can win
a limited publication slot.

The exact deployed clock gate accepts both screenshot cases. The fixed gate
rejects each with FIXTURE_NOT_TODAY_RIGA.

The read-only 20:30 Riga cycle contains 1,339 persisted market candidates:
186 for 1 October, 956 for 2 October, and 197 for 3 October. The earlier 19:30
cycle even contains 11 candidates for 4 October despite requesting 1–3 October,
consistent with the independent restoration path. These are candidate-market
counts, not match counts or betting recommendations. We do not claim that
every same-day READY candidate would pass final publication/duplicate checks.

## New behavior

The active Lab discovery route opts into TODAY_RIGA through
GOALVISION_LAB_TODAY_ONLY=1. The CLI also exposes --today-only for explicit
offline/manual use. It overrides the broader research horizon for fixture
discovery and queries today's date with Europe/Riga timezone.

Both newly received fixtures and restored global/tracked fixtures are filtered
to that same Riga date before odds, model/context enrichment and final-review
budget allocation. UTC odds dates are derived from the scoped upcoming fixtures.
The research runner retains its explicit broader-horizon capability.

New SINGLE and every COMBO leg must match the Riga publication date. The
shared Lab gate is used in preparation and before/after the atomic publication
claim, so retained future previews cannot bypass the restriction. Existing
nighttime/cutoff gates, quote freshness, model checks, independence, correlation
and other publication rules continue to apply. No combo is forced when today's
eligible pool is too small.

Already published future picks and their receipts, statistics and settlements
remain intact. Settlement notifications bypass the new-pick date restriction,
including after midnight and on later dates.

Audits and bounded stdout expose discovery_day_scope with the Riga date,
TODAY_RIGA mode, included fixture count and excluded fixture count.

## Validation

525 tests PASS in 41.94 seconds. Coverage includes:

- Riga date equality across winter/summer offsets and both 2026 DST transitions;
- rejection of previous-day, next-day and two-days-ahead fixture dates;
- high-probability future picks cannot displace same-day candidates;
- no future leg can fill an insufficient same-day combo pool;
- provider and persistent restored-fixture filtering before further requests;
- old future previews rejected without a claim/send;
- date recheck after claim with zero transport calls after a date change;
- later-day settlement remains publishable;
- CLI flag/environment propagation and bounded diagnostic projection;
- adjacent discovery, publication, delivery, combination and settlement regressions;
- hash-pinned upgrade, replay, rollback, busy-cycle refusal, inactive timers,
  tamper and staged-symlink refusal.

All integration sends use synthetic transports. No manual provider calls,
real Telegram test messages, forced discovery cycles or production changes.

Structured evidence: docs/evidence/prematch_today_scope_20261001/verification.json.

## Operator package

Package: /home/arvis/goalvision-operations/prematch-today-20261001
Short entry point: /home/arvis/goalvision-operations/today-fix.py

Read-only verification:

    python3 ~/goalvision-operations/today-fix.py

Operator-approved installation:

    sudo python3 ~/goalvision-operations/today-fix.py --apply

Operator-approved rollback:

    sudo python3 ~/goalvision-operations/today-fix.py --apply --rollback

The package layers four reviewed modules onto the exact currently deployed
context-scope-1a18dc0 release. It preserves the prior CPU fix, accuracy-combo
enablement and the complete remaining Python tree. Only the discovery
EnvironmentFile route changes via a dedicated later-sorting drop-in.

Only the discovery timer is paused for installation. An active cycle must end
naturally within 60 seconds; otherwise installation refuses and restores the
timer. There is no kill or manual service start. Monitor, AutoRepair, settlement,
observer, research and weekly-statistics routes are checked unchanged.
Any transaction failure restores the prior discovery route and timer state.
Rollback removes only this package's drop-in and restores the previous release.

## Operator deployment verification

The operator deployed f5d79683dda72067fc5fae5a02f2db4cf38497d0 on 1 October at
20:53:19 Europe/Riga (drop-in modification time). Verification at 20:54 Riga
passed the full Python-tree hashes, exact release environment, drop-in bytes
and effective discovery EnvironmentFiles route.

Active release: /opt/goalvision-prematch-today-scope-f5d7968-20261001.
Both GOALVISION_LAB_TODAY_ONLY=1 and GOALVISION_LAB_ACCURACY_COMBOS=1 are present.
All protected service routes match the pre-deployment snapshot.

The discovery timer is active/waiting. Its next scheduled run is 21:00 Riga
(the server displays this as 20:00 CEST). The last completed cycle was the
20:30 Riga run, before deployment; its exit 0 is not evidence for the new scope.
The first natural TODAY_RIGA cycle and any new publication receipt dates
remain NEEDS_MORE_EVIDENCE. No cycle was forced and no test message was sent.

Deployment evidence: docs/evidence/prematch_today_scope_20261001/deployment.json.

## Natural runtime verification — 21:00 and 21:30 Riga

Both scheduled cycles completed after the operator deployment. Each requested
only 2026-10-01 in Europe/Riga, retained 135 same-day fixtures and excluded 1,630
out-of-date fixtures before analysis. Each evaluated 157 candidate markets from
15 current-odds fixtures. These counts are not numbers of published bets.

| Scheduled cycle, Riga | Publication completed, Riga | SINGLE | COMBO | Provider calls | Status |
| --- | --- | ---: | ---: | ---: | --- |
| 21:00 | 21:02:02 | 3 | 2 | 63 | COMPLETED |
| 21:30 | 21:32:50 | 3 | 0 | 64 | COMPLETED |

Read-only ledger verification checked all eight persisted receipts (Telegram
message IDs 324–331) against the publication-cycle evidence and their immutable
prediction documents. All sixteen document fingerprints match. All six SINGLE
kickoffs and all six COMBO leg entries are on 1 October in Riga and were in the
future at their respective send times. There are zero receipt mismatches,
cross-date legs or post-kickoff sends in this cohort.

The 21:00 cycle prepared two triples from seven eligible fixtures. The 21:30
cycle reports INSUFFICIENT_ELIGIBLE_COMBO_FIXTURES with one eligible fixture
remaining and ten COMBO_FIXTURE_ALREADY_CLAIMED rejections. No additional combo
was forced. SINGLE/COMBO overlap exists in the intended approved-single combo
policy; these 12 kickoff entries are not 12 independent fixtures or learning
observations.

Systemd confirms the 21:30 service exited successfully at 21:32:51 Riga, with
ExecMainStatus=0. The timer remains active/waiting for 22:00 Riga. Server CEST
wall-clock values are one hour behind Riga on this date.

The deployed legacy 1.30 odds floor still blocks ten candidate markets per
cycle. Its already-prepared removal and the unified performance, readiness and
calibration work are not included in this date-scope deployment. Date/delivery
PASS does not establish model quality, calibration or profitability.

No manual provider calls, manual cycles, source-ledger changes, test messages
or new deployments were performed for this verification. No code changed;
the existing 525-test result remains the release regression evidence. Natural
midnight rollover remains unobserved in this sample; its boundary paths and
both DST transitions have offline coverage.

Evidence: docs/evidence/prematch_today_scope_20261001/natural_cycles.json.

## Changed files and limitations

New behavior:
app/lab_combo/publication_window.py;
app/lab_v2_shadow/runner.py;
app/lab_v2_shadow/cli.py;
app/lab_v2_shadow/operator_output.py.

Tests/package:
tests/test_lab_today_scope.py;
tests/test_prematch_today_scope_upgrade.py;
operations/today-scope/update.py;
this report, verification evidence and TASKS.md.

The isolated branch starts at c490866 and carries the already-deployed
app/prematch_football_context/capture/repository.py and snapshot/service.py
byte-for-byte for baseline parity. These two modules are not overlaid or
changed by this deployment.

No Official, LIVE, champion, historical bookmaker odds, bankroll or result-history
change. No other pending AI/ML batch changes are included. Existing selection
thresholds are outside this date-scope fix.

The first two natural post-deployment cycles now pass the date/receipt check
below. A no-pick result remains valid when no same-day candidate passes the gates.

Git commit: the commit containing this report on fix/prematch-today-20261001;
the immutable operator package records its full source commit.
