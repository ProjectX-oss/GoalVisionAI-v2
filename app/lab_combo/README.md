# GoalVision Lab experimental selection

`LAB_EXPERIMENTAL_SELECTION_V1` is an isolated Lab-only publication policy. It
does not change or bypass any Official, model-activation, calibration or
production publication gate. Its numerical signal is deterministic and
explicitly uncalibrated.

The discovery command performs cheap fixture/odds filtering before bounded
Current Match Intelligence enrichment. It publishes at most three ranked
singles and three disjoint three-leg combinations when all evidence gates pass.
Missing confirmed lineups remain eligible for a later near-kickoff recheck and
do not prevent early quality scoring, but they prevent final publication.

LAB does not impose a hard minimum decimal-odds floor on singles, combo legs or
combined combo odds. Decimal prices must still be current, fresh, finite and
greater than 1, and low odds do not bypass value, evidence, agreement, lineup,
final-review, independence, correlation, exposure or duplicate-publication
checks. The experimental upper safety limits remain fail-closed safeguards.

Every supported Lab market is currently treated as lineup-sensitive. Evidence
may be retained as `EARLY_CANDIDATE`, but publication requires a forced final
review beginning 60 minutes before kickoff. That review refreshes fixture
status, odds, lineups and injuries; attempts recent-lineup continuity evidence;
and requires a complete, non-conflicting confirmed XI before assigning
`READY_TO_PUBLISH`. Missing unpublished lineups remain
`FINAL_REVIEW_REQUIRED` until a later cycle rather than becoming a permanent
rejection.

Published prices, provider timestamps, retrieval timestamps, reasoning,
provenance and fingerprints are immutable in `var/lab_combo/ledger.db`.
Singles and combos have separate settlement records and statistics. Settlement
only queries published, unresolved fixtures after the normal terminal-result
window; delivery claims make both prediction and result messages exactly-once.
Public Telegram messages use concise Latvian labels, Latvia local kickoff time
and rounded display values. Full-precision factors, missingness, freshness,
lineup state, experimental signal and provenance remain in the immutable audit
record. Optional result images may be placed at
`app/lab_combo/assets/results/{win,loss,void}.png`; absent files automatically
fall back to text and no image path or binary is stored in the database.

The discovery process has a hard 40-call ceiling. At 30-minute cadence its
maximum is 1,920 calls/day. Settlement is capped at 21 calls per 10-minute
cycle, or 3,024 calls/day. The combined conservative ceiling is 4,944 calls/day,
below the 7,500-call Pro allowance; normal cache reuse is substantially lower.

The units remain inert until the operator installs and enables them. Rotate any
Lab bot credential that has appeared in transport logs before running this
command:

```bash
sudo systemctl stop goalvision-lab-combo-discover.timer goalvision-lab-combo-settle.timer && sudo install -m 0644 app/lab_combo/systemd/goalvision-lab-combo-{discover,settle}.{service,timer} /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now goalvision-lab-combo-discover.timer goalvision-lab-combo-settle.timer
```

Both timers are persistent. Both services share the same non-blocking ledger
lock, preventing overlapping discovery and settlement processes after restart.
