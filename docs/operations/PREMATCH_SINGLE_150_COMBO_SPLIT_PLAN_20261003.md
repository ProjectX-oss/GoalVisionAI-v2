# PREMATCH SINGLE 1.50 test and separate COMBO Telegram stream

Status: FUTURE WORK RECORDED; no implementation or deployment in this change.
Request: Arvis, 2026-10-03 12:51 Europe/Riga.
Source baseline: 1564193; deployed runtime remains e355b51.

## Requested direction and present boundary

The user wants to raise the PREMATCH signal minimum to 1.50 later for a test,
and proposes moving COMBO bets to the COMBO Telegram bot so they do not mix
with SINGLE matches, with a new statistics period.

Interpret the 1.50 request as the next PREMATCH Lab SINGLE policy. The current
COMBO per-leg 1.30 requirement remains unless the user explicitly extends 1.50
to COMBO legs. There is no additional combined-odds minimum.

Current installed behavior remains SINGLE >=1.30 and COMBO legs >=1.30 in the
existing Lab destination. The first post-R2 natural discovery/observer evidence
remains a prior pending task; recording this plan does not complete it.

The future COMBO destination and publishing bot identity must be established
before an operator package is finalized. A bot name alone does not determine
the channel/group receiving predictions. Do not invent a chat ID or transfer
credentials into documentation. No Telegram calls or sends were made here.

## Implementation sequence

1. Finish the pending natural-cycle verification of the installed 1.30 floor.
2. Prepare a versioned SINGLE >=1.50 policy in an isolated worktree. Compare
   exact captured Decimal values before ranking and before a new delivery
   claim, with inclusive 1.50 and no display-rounding exception. Keep the
   independently filtered COMBO >=1.30 candidate pool, quality/correlation,
   probability and freshness rules. Preserve replay of prior policies.
3. Introduce explicit product-specific Telegram destinations and bot selection
   at the publication boundary. Freeze the destination and non-secret bot
   identity with the claim/receipt; validate acknowledgements against it.
   Route new COMBO predictions and their results to the COMBO destination;
   SINGLE predictions and their results stay in the PREMATCH destination.
   Configuration errors must not silently send COMBO to the SINGLE channel.
4. Add a prospective, immutable COMBO statistics period at cutover, counted
   from confirmed new publications assigned to that period. Show published,
   pending, WON/LOST/VOID/partial-void, settled, hit rate, flat-unit P/L and ROI.
   Preserve existing accounting definitions and disclose unresolved outcomes.
   Keep COMBO and SINGLE accounting separate; do not invent a cash bankroll
   or change stake amounts without a separate concrete decision.
5. Keep old predictions, losses, receipts, claims and statistics intact.
   Settle pre-cutover open bets in their original publication destination and
   original statistics period, including early COMBO loss once and remaining
   leg tracking. Do not migrate them by settlement date or re-send them.
   Keep all-time history auditable. SINGLE 1.50 has its own policy cohort for
   comparison with 1.30; no deletion/reset of prior SINGLE history is requested.
6. Add bounded, product/period-specific summaries through existing reporting
   interfaces. Keep weekly service routing unchanged; any needed reporting
   behavior change must be reviewed explicitly in the future package.
7. Offline tests, evidence, local Git commit, and an exact-base operator
   package with compatible rollback. Deployment is an operator action.
   Verify the actual installed base again when building the package.

## Existing source constraints observed read-only

- app/lab_combo/service.py uses LAB_CHAT_ID in prediction/result claims, sends
  and receipt validation, including both modern and legacy delivery paths.
- Settlement requires proof of the original confirmed publication. A global
  LAB_CHAT_ID replacement would misroute old open bets or invalidate receipts.
- app/lab_v2_shadow/statistics.py binds confirmed SINGLE receipts to the Lab
  destination; public_single_snapshot currently spans all-time history.
- app/lab_combo/settlement.py contains separate SINGLE and COMBO totals.
  Product separation already exists in accounting, but a new prospective
  COMBO period needs explicit membership and compatible public readers.
- app/lab_v2_shadow/cli.py reports the existing authorized destination.
  Diagnostics, claim integrity and report readers must remain consistent.

## Required future offline acceptance coverage

- SINGLE 1.4999 rejected and exact 1.50 accepted, qualifying alternative market
  considered before ranking; COMBO 1.30 accepted and below 1.30 rejected.
- Fake transports prove product-specific prediction/result destinations,
  expected bot identity and acknowledgement binding; invalid config fails
  before a claim without cross-channel fallback.
- Open pre-cutover bets retain original route/period even if settled later;
  new-period results exclude them. Period boundary and replay are deterministic.
- Economic deduplication survives destination/policy changes; a second channel
  does not authorize a duplicate bet. Unknown deliveries remain terminal.
- Early loss, partial void, delayed remaining-leg completion and immutable
  frozen result messages preserve one financial outcome and notification.
- Fresh statistics do not erase losses, duplicate P/L, reattribute old bets,
  reset calibration data or inflate COMBO learning observations.
- Compatible rollback continues settlement of bets published into both routes;
  disabling new COMBO publication cannot orphan already published COMBO bets.

## Protected behavior and review

Official unchanged; LIVE and ADMIN Codex remain DISABLED. Champion, de-vig
research, frozen calibration plan and accumulated learning evidence remain
unchanged. Retain Riga today-only and early COMBO settlement.
No automatic deployment/promotion, manual operational cycles, provider calls,
test sends or historical bookmaker odds acquisition.

Changing the odds floor is an experiment, not evidence of improved predictive
quality or profit. Compare separately labelled forward cohorts with sample
size, selection volume, odds distribution and complete/pending outcomes.

This commit changes documentation only. Verification: scoped Git diff review
and git diff --check; no application tests rerun for a planning-only change.
