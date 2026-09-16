# Lab V2 final-review readiness audit — 2026-09-16

## Scope and safety

This audit traces `EARLY_CANDIDATE` through `FINAL_REVIEW_REQUIRED`,
`READY_TO_PUBLISH`, and the Lab-only publication handoff. Operational SQLite
files were opened read-only for evidence queries. Tests use pytest temporary
directories and disposable SQLite files. No provider call, Telegram transport,
systemd action, Official path, historical bookmaker odds, or operational
database write is part of this audit.

Initial operational database SHA-256 values:

- `var/lab_v2/shadow.db`:
  `898744f97c68ea97395b8bae405067938e1449ed3a464dd6befe8c94b5a3ff87`
- `var/lab_combo/analysis.db`:
  `62c4f8c70b05312124a95292e936b5041ec5c15240f1828e8f342aba080da6b3`
- `var/lab_combo/ledger.db`:
  `0b49e7bd69e42f84ff711fe7ab10d9557687e182829ce670d8680d30eae3faee`

The already-enabled systemd timers remained untouched, as required. While the
audit was in progress, the pre-existing V2 timer ran at 18:30 Europe/Berlin and
the separate Lab ledger job continued its ten-minute run records. Consequently
the final hashes of `shadow.db` and `ledger.db` differ from the initial hashes;
the systemd journal attributes the 18:30 V2 write to PID 353154 and the normal
`controlled-cycle --send` unit. It recorded zero READY candidates and zero
Telegram sends. No audit/test command wrote either operational database.
`analysis.db` remained byte-identical.

## Findings

`APPROVED` is the ensemble decision and does not mean publication-ready. The
separate readiness gate requires the final-review window, exact refreshed
fixture state, exact fresh current odds, supported optional evidence required
for that market, and Tier C quality constraints. The publication adapter then
accepts only `APPROVED` plus `READY_TO_PUBLISH` and applies the existing
Lab-ledger exactly-once boundary.

Two implementation defects were present:

1. The readiness gate used league capability alone, so a league advertising
   lineups or injuries made that evidence mandatory for every market. This
   recreated the V1 every-market lineup dependency. Existing project policy is
   market-specific: 1X2 is lineup-sensitive; totals and BTTS are not.
2. Optional enrichment could consume the call budget before final review. At
   16:00 UTC the cycle used 99 of 100 calls and Atromitos–PAOK received no
   exact fixture or odds refresh. Repeated highest-edge ordering could also
   prefer later kickoffs over fixtures nearer to expiry.

The final-review timestamp existed in evidence but was not itself validated by
the readiness function. This was an auditability/freshness gap rather than the
observed blocker for the two refreshed examples.

## Real examples

- Waldhof Mannheim–Rot-Weiß Essen, `DRAW`: Tier B metadata advertises lineups
  and not injuries. Fixture and odds refreshes passed. The sole effective
  blocker was `lineup_status=NOT_YET_PUBLISHED` for a lineup-sensitive 1X2
  market.
- Omonia Nicosia–Celta Vigo, `HOME_WIN`: Tier A metadata advertises both
  endpoints. Fixture, odds, and injuries refreshes passed. The sole effective
  blocker was `lineup_status=NOT_YET_PUBLISHED` for a lineup-sensitive 1X2
  market.
- Atromitos–PAOK, `DRAW`: Tier C metadata advertises lineups but not injuries.
  It was not final-reviewed because the remaining call budget was insufficient:
  fixture refresh and odds refresh were false, lineup was not requested, and
  `reviewed_at_utc` was null. Its Tier C ensemble quality had otherwise passed.

Across 2026-09-16 evidence through the 16:00 UTC cycle there were 632 approved
`EARLY_CANDIDATE` observations, 15 approved `FINAL_REVIEW_REQUIRED`
observations, and zero READY observations. The same logical fixtures were
recomputed in later cycles when still eligible; however, there was no durable
queue or reserved budget guaranteeing completion before kickoff.

## Corrected policy

`LAB_V2_FINAL_REVIEW_READINESS_V2` explicitly makes `HOME_WIN`, `DRAW`, and
`AWAY_WIN` lineup-sensitive. Confirmed lineups are required only when supported
for those markets; refreshed injuries are likewise required only when
supported. Totals and BTTS may proceed without optional lineup/injury evidence.
Every market retains exact fixture, current-odds, timestamp, ensemble edge,
agreement, signal-quality, and Tier C gates.

The runner now reserves up to four final-review calls for each of at most five
near-kickoff fixtures before optional prediction enrichment, orders the
shortlist by stage and kickoff before edge, validates a five-minute final-review
timestamp, and persists explicit `readiness_reasons`. Candidates are rebuilt on
the next cycle, while claimed/sent/indeterminate Lab publication keys remain
deduplicated by the existing ledger.

The first naturally scheduled cycle that observed the working-tree change used
83/100 calls with a 20-call final-review reserve, compared with 99/100 in the
preceding cycle. It reconsidered Atromitos–PAOK, completed fixture/odds/lineup
review, and retained it as not READY because the refreshed selection remained
lineup-sensitive and also failed the unchanged Tier C readiness-quality gate.
This operational observation is not counted as a controlled test or deployment.

## Verification

- `tests/test_lab_v2_shadow.py`: 33 passed.
- Adjacent Lab selection/no-minimum-odds/Official gate tests: 57 passed plus 4
  subtests.
- Broader suite excluding the unrelated collection blocker: 1,630 passed and
  563 subtests passed; one unrelated staging-model rehearsal assertion failed
  (`CALIBRATION_REVIEW_MISSING` versus expected
  `CALIBRATION_EVIDENCE_STALE`).
- Unfiltered collection is independently blocked by an unrelated existing
  import of missing `app.lab_combo.cli._analysis_input`.
