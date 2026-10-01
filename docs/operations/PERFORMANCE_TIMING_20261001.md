# Unified Lab performance and timing diagnostics — 2026-10-01

Status: PASS (implementation, deterministic tests, read-only runtime snapshot).
Scope: plan stages 3 and 5. No deployment or publication threshold changes.

performance.py reads confirmed SENT receipts and immutable settlements as of a
declared timestamp. SINGLE/COMBO separately report published, settled, W/L/VOID,
pending, partial void, hit rate, one-unit P/L, ROI, average and median odds.
ROI denominator includes every settled ticket, including void stakes. Pending
tickets are excluded. Average odds covers all confirmed published tickets.
Partial-void combos retain authoritative payout and are excluded from binary
hit rate. COMBO results never create calibration or model-learning targets.
Missing timestamps, probabilities or payout are explicit, never fabricated.

Every current health/AI CLI audit, observer run and persisted discovery health
receives PERFORMANCE. Missing/unreadable ledger produces UNAVAILABLE, not zeros.
Old immutable cycle evidence retains an explicit absent-snapshot marker.
V2 loss postmortems now use their frozen decision evidence without requiring a
V1-only timestamp or fetching retrospective provider data.

Separate negative/zero/positive EV cohorts and one-dimensional segments:
odds/probability, market, league/profile, model confidence/disagreement,
lead time [0,10), [10,25), [25,45), [45,90), [90,inf) minutes;
odds age [0,60), [60,300), [300,900), [900,1800), [1800,3600),
[3600,14400), [14400,inf) seconds.
Timing is measured at the captured selection time, never against today's clock.
Selected candidates capture timing; older frozen observations derive it from
their retained timestamps. Missing values stay MISSING.
Candidate diagnostics include no-pick reasons and invalid/stale rates with
candidate-market denominators. Unscored fixtures cannot be assigned fabricated
timing buckets. Settled SINGLE segments include Brier/log loss/ECE/reliability.

Read-only current ledger: 126 SINGLE published, 117 settled (32 W / 85 L),
9 pending; P/L -25.83 units, ROI -22.0769%. 19 COMBO settled (1 W / 18 L),
P/L -5.572924 units, ROI -29.3312%. These are cumulative mixed-policy results,
not evidence about the newly deployed accuracy COMBO mode. Full dated evidence:
docs/evidence/forward_ai_ml_20261001/performance_snapshot.json.
Three legacy SINGLE predictions lack model probabilities and are excluded only
from probability metrics, not from W/L or financial accounting.

Tests: 68 snapshot/schedule tests pass; 149 adjacent delivery/combo/shadow tests
pass. Earlier expanded adaptive metrics/autonomy run: 266 pass plus one obsolete
exact-dictionary expectation, updated and passing in the 68-test run.
Changed modules: adaptive_lab performance/health/observer/prematch/metrics,
lab_v2_shadow publication/cli/audit; focused snapshot and audit regression tests.
