# PREMATCH SINGLE floor and settlement — natural-cycle audit, 2026-10-02

**Operational verdict: PASS for the inspected 12:00 discovery, 12:08 observer and settlement through 12:25.**
Snapshot cutoff: 12:28:11 Europe/Riga.
Release: `/opt/goalvision-prematch-single-floor-f81aa2c-20261002`.

## Discovery and actual delivery

The scheduled discovery service ran 12:00:02–12:03:02, exiting successfully.
Persisted analysis and delivery statuses are COMPLETED. It made six publication
attempts and recorded six accepted deliveries: three SINGLE and three COMBO.
All six have matching durable Lab receipts, message IDs 383–388.

| SINGLE | Market | Captured odds | Kickoff, Riga |
|---|---|---:|---|
| Finn Harps – Kerry | OVER_1_5 | 1.36 | October 2, 21:45 |
| Gumi Sportstoto W – Suwon FMC W | UNDER_3_5 | 1.53 | October 2, 13:00 |
| Sturm Graz – Floridsdorfer AC | OVER_2_5 | 1.33 | October 2, 14:00 |

The persisted policy is `LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V3_MIN_ODDS_130`,
with minimum odds 1.30 and probability minimum 0.55. Preparation explicitly blocked
67 candidate markets with `LAB_SINGLE_ODDS_BELOW_1_30`. Other retained SINGLE
blockers were 918 below the probability minimum, 31 quality-policy rejections and
16 outside the Lab kickoff window. These are candidate-market counts, not fixture counts.

| COMBO message | Combined odds | Leg odds |
|---|---:|---|
| 386 | 4.134060 | 1.93 / 1.53 / 1.40 |
| 387 | 2.227680 | **1.17** / 1.36 / 1.40 |
| 388 | 2.822400 | 1.44 / 1.40 / 1.40 |

All nine COMBO legs retain the no-floor contract. The 1.17 leg is Smedby–Nyköping,
OVER_1_5, providing natural production evidence that the SINGLE floor does not
remove an otherwise eligible COMBO leg.

The three COMBOs contain nine distinct fixtures and eighteen distinct teams.
Every one of the twelve SINGLE/COMBO kickoff entries is October 2 in Europe/Riga.
Independent checks found no receipt, same-day, odds-product or batch identity mismatch.

## Settlement correction

Both previously known lost COMBOs were settled once at 11:55:04:
- Germany–Serbia, OVER_2_5, retained fulltime score 2:0.
- British Virgin Islands–Montserrat, OVER_2_5, retained fulltime score 0:2.

Each records LOST and -1u, with two remaining legs explicitly pending.
Their result messages were accepted at 11:55:37, IDs 381 and 382.
No published COMBO with a retained losing leg remains financially pending in this snapshot.

Both frozen result-message snapshots correctly show W2/L21, P/L -6.588824u.
They show 27 pending at their own creation time; the 12:00 cycle added three
new COMBOs, so the later observer and settlement correctly show 30 pending.
Historical message statistics remain snapshots, not continuously updated counters.

The remaining legs have future kickoffs. Full late leg-detail completion still
requires later natural cycles; this audit does not manufacture their results.

## Independent cumulative Lab reconciliation

| Population | Published | Settled | WON | LOST | VOID | Pending | Flat P/L | ROI on settled |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SINGLE | 165 | 131 | 41 | 90 | 0 | 34 | -27.35u | -20.88% |
| COMBO | 53 | 23 | 2 | 21 | 0 | 30 | -6.588824u | -28.65% |

These are all published Lab cohorts, including earlier policies, not the results
of the three new SINGLEs or three new COMBOs.

Recomputed all 131 SINGLE outcomes and returns, all 23 COMBO economic outcomes
and returns, and all 53 published COMBO odds products from retained immutable evidence.
The independent counts, P/L and ROI exactly match both the 12:08 observer snapshot
and the 12:25:41 settlement run.

All 154 persisted settled bets have accepted result receipts. Across 372
publication/result receipts: zero invalid receipts, zero claims without receipts,
and zero duplicated destination/message-ID pairs. All inspected source-document
fingerprints reproduce exactly.

The 12:08 observer reports PERFORMANCE COMPLETE, LIVE DISABLED, heavy_training=false,
api_calls=0 and telegram_sends=0. COMBO predictive/calibration observations remain zero.
Three older SINGLEs lack frozen probability evidence; financial totals still include them.

## Pending results explained

Dayrout–Ismaily SC, fixture 1594851, retains its original frozen October 1 kickoff.
The natural settlement diagnostics consistently report:
- current provider kickoff: October 2, **15:30 Riga**;
- provider status: NS;
- reason: RESCHEDULED_FUTURE_KICKOFF;
- schedule_changed: true.

This now establishes the provider-side reason for its pending status. Its frozen
history is preserved and no premature VOID/LOST decision was invented.

Four other started-but-unresolved COMBO legs were about 28–88 minutes after kickoff
at the snapshot cutoff; the existing result-check eligibility starts after 90 minutes.
The other started pending SINGLE was about 28 minutes after kickoff.
These records do not indicate a hung settlement worker. Latest inspected settlement
service ran 12:25:01–12:25:41 and exited successfully.

## Scope, evidence and next work

This was a read-only SQLite/systemd audit and independent in-memory arithmetic.
No application change, new regression suite, manual provider call, operational cycle,
Telegram send, deployment, training or promotion was performed.

Receipts prove Telegram acceptance; subsequent deletion or channel retention was
not independently checked. Score reconciliation uses retained provider scores, not
new external score requests.

Evidence: `docs/evidence/prematch_floor_natural_20261002/reconciliation.json`.
Evidence SHA-256: `ac48b03aed99443ecab3ce3c6a88329617fcaa648a08cee2a148ad5450ba9e79`.

Next planned work is segmented forward selection-quality analysis: separate policy
cohorts, SINGLE/COMBO accounting, non-positive EV, odds/probability bands and lead time.
Training/calibration readiness and future early-loss leg-detail completion remain
evidence to collect. Operational PASS is not a claim of predictive improvement.
