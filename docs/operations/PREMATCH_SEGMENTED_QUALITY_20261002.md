# PREMATCH Lab — segmented forward quality review, 2026-10-02

**Analysis/reconciliation: PASS.**
**New policy superiority, threshold changes and promotion: NEEDS_MORE_EVIDENCE.**

Read-only snapshot: 12:50:18 Europe/Riga. Confirmed publications: 165 SINGLE and 53 COMBO.
Financially settled: 131 SINGLE and 23 COMBO. Only GoalVision's own frozen quotes captured
at publication and subsequent results were used; no historical bookmaker-odds feed was acquired.

## Main finding

The older broad-coverage ensemble accounts for 109 settled SINGLE tickets:
31 WON / 78 LOST, hit rate 28.44%, -21.58u, ROI -19.80%.
Its mean frozen estimated probability was 48.78%.
On exactly the same 109 tickets, ensemble Brier was 0.23444 and frozen market-consensus
Brier was 0.18248 (lower is better). This selected forward sample supports investigating
probability calibration and model-market disagreement before treating model-estimated
positive EV as reliable.

This is descriptive evidence from previously selected tickets, not a new holdout or
a causal proof that replacing the current model would improve future returns.

## Policy cohorts

| SINGLE policy | Published | Settled | WON / LOST | Pending | Hit rate | P/L | ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Earliest experimental | 3 | 3 | 0 / 3 | 0 | 0% | -3.00u | -100% |
| Older broad-coverage ensemble | 109 | 109 | 31 / 78 | 0 | 28.44% | -21.58u | -19.80% |
| Probability-first V1 | 5 | 5 | 1 / 4 | 0 | 20% | -1.25u | -25% |
| Accuracy-first V1, original 1.30 floor | 27 | 14 | 9 / 5 | 13 | 64.29% | -1.52u | -10.86% |
| Accuracy-first V2, no floor | 18 | 0 | — | 18 | — | 0u settled | — |
| Accuracy-first V3, restored 1.30 floor | 3 | 0 | — | 3 | — | 0u settled | — |

Accuracy V1 began October 1. V2 was published October 2 at 09:04–11:33 Riga;
V3 at 12:02 Riga. V2 and V3 have no resolved outcomes at the cutoff.
Their zero settled P/L is not evidence of breakeven performance.

The accuracy V1 cohort has only 14 settlements from 13 distinct fixtures.
It has higher observed hit rate than the older cohort but remains financially negative.
Cohorts differ in dates, markets and selection rules and cannot be treated as randomized alternatives.

## EV and frozen probability quality

| Frozen EV group, SINGLE | Settled | WON / LOST | P/L | ROI | Brier |
|---|---:|---:|---:|---:|---:|
| Positive | 114 | 32 / 82 | -22.83u | -20.03% | 0.23688 |
| Negative | 14 | 9 / 5 | -1.52u | -10.86% | 0.22963 |
| Missing | 3 | 0 / 3 | -3.00u | -100% | unavailable |

All 14 resolved negative-EV tickets are the accuracy V1 cohort, and all use market-only
probability evidence. Their ensemble and market probabilities are identical. Consequently,
the table does not establish that negative EV is preferable: it primarily compares different policies.
There is no resolved within-policy positive-versus-negative EV comparison for the new versions.

Across the 128 settled SINGLEs with frozen probabilities, mean predicted probability is 50.72%
versus observed 32.03%. Brier is 0.23609, log loss 0.66441 and ten-bin ECE 0.19025.
The paired frozen market Brier is 0.18986. Three legacy tickets are excluded only from
probability scoring; they remain in all financial totals.

162 modern published SINGLEs retain calibration_status=UNCALIBRATED_LAB_ENSEMBLE
and confidence=LOW. Thus the current confidence field provides no between-group discrimination.
This is not evidence of a missing calibrated artifact being silently replaced:
the retained status explicitly identifies uncalibrated estimates. Actual challenger calibration
still requires the separate validation/evidence chain.

## Markets and odds

The larger negative market totals are HOME_WIN: 1/13, -10.90u; OVER_2_5: 5/16, -8.04u.
AWAY_WIN is 5/17, +4.62u; DRAW 12/44, -0.04u.
These pooled numbers largely describe older policies.

Within accuracy V1 alone:
- OVER_1_5: 4/5, +0.58u.
- OVER_2_5: 2/5, -2.27u.
- UNDER_3_5: 2/3, -0.18u.
- BTTS_NO: 1/1, +0.35u.

These small groups are monitoring targets, not evidence for market exclusions or promotions.

| Captured SINGLE odds | Settled | WON / LOST | P/L | ROI |
|---|---:|---:|---:|---:|
| Below 1.30 | 3 | 3 / 0 | +0.68u | +22.67% |
| 1.30–below 1.50 | 13 | 9 / 4 | -0.52u | -4.00% |
| 1.50–below 2.00 | 22 | 10 / 12 | -4.33u | -19.68% |
| 2.00–below 3.00 | 22 | 3 / 19 | -14.81u | -67.32% |
| 3.00–below 5.00 | 50 | 14 / 36 | -0.70u | -1.40% |
| 5.00–below 10.00 | 14 | 2 / 12 | -0.67u | -4.79% |
| 10.00+ | 7 | 0 / 7 | -7.00u | -100% |

The 2–3 odds band deserves review in the older model diagnostics. This is not a validated
reason to add an upper floor/cap or to reverse the user-authorized SINGLE minimum.
The three old below-1.30 winners likewise cannot validate a new no-floor strategy.

## Disagreement, league and timing

All 20 resolved selections with absolute model-market disagreement >=20 percentage points
belong to the older broad-coverage ensemble. Combined results are 2 WON / 18 LOST, -14.40u.
For the >=30-point subgroup, 0/6 and -6u. These records are not new-policy gate failures.

There are 73 league IDs represented, but only two have at least ten settled SINGLEs:
UEFA Nations League 10/26, +5.55u; Africa Cup of Nations Qualification 1/10, -6.20u.
Only four leagues have at least five settlements. The coverage is too thin for
reliable league whitelists/blacklists.

Selection lead-time results:
- 10–25 minutes: 8/24, -6.27u.
- 25–45 minutes: 14/47, -8.32u.
- 45–90 minutes: 16/52, -8.84u.
- 90+ minutes: 3/8, -3.92u; another 32 remain pending.
- 0–10 minutes: no published sample.

Provider quote timestamp age at selection is mostly 1–4 hours: 114 settled tickets,
38 WON / 76 LOST, -15.56u. The 30–60 minute bucket is 3/14, -8.79u.
Age is measured at the frozen selection timestamp, not as of today's audit, and does not
by itself establish a freshness violation. These cohorts are unbalanced and support no
publication timing or freshness-threshold change.

## COMBO

Older broad-coverage COMBOs: 19/19 settled, 1 WON / 18 LOST, -5.572924u.
Accuracy COMBOs: 34 published, four financially settled, 1 WON / 3 LOST,
-1.015900u, 30 pending. Of those four decisions, two are confirmed early losses
whose remaining legs are still pending.

Financial accounting is valid, but an immature cohort recognizes guaranteed losses
before potential winners can complete. Its current settled-only ROI cannot establish
a predictive-quality ranking. COMBOs remain excluded from model/calibration observations.
Full combo-policy, leg-policy and EV groups are retained in the evidence.

## Verification and decisions

Every dimension partitions the same 165 publications and reconciles to 131 settlements
and -27.35u. Independent overall counts, P/L, Brier, log loss and ECE match the 12:38
observer snapshot. Source fingerprints and segment reconciliation have zero errors.
The 131 SINGLE settlements span 121 fixtures, so not all historical rows are independent.

No application defect requiring a new code patch was established by this review.
No thresholds, publication rules, champion, database history, services or deployments were changed.
No training, holdout consumption, provider request or Telegram send was initiated.

Next implementation priority: review and wire the already prepared current-odds de-vig
comparators into research/shadow metrics. The paired market baseline is a useful existing
reference while sufficient forward validation/calibration examples accumulate.
Next quality check: evaluate the V2/V3 cohorts after their games resolve, preserving policy,
market and EV separation. No fixed hour can substitute for adequate resolved sample support.

Evidence: `docs/evidence/prematch_quality_segments_20261002/analysis.json`.
SHA-256: `15f74061e312a1f909fd7dd98e7d650d5af7e54d4f9854392c30da811ff82aa8`.
The evidence contains normalized ticket rows, all examined dimensions and policy-crossed groups.
