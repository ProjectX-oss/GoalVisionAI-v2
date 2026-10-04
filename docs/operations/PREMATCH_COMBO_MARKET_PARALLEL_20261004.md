# Parallel market COMBO experiment — declaration 2026-10-04

User authorization: add another visible COMBO selection to collect results, preserving each leg's exact decimal odds >=1.30. Existing DC selection remains active; no champion promotion, Official/LIVE or SINGLE change.

The second policy LAB_COMBO_MULTI_BOOK_MARKET_V1, cohort COMBO_MARKET_20261004_V1, ranks existing accuracy-approved candidates by the lower of the median MULTIPLICATIVE and median POWER de-vig estimates across at least two complete, uniquely identified current bookmakers. Methods reuse reviewed existing arithmetic. This rank is not calibrated probability, a confidence bound, or independent model agreement. No external model/library is installed.

Retain the exact 1.30 floor, current quote/provenance/review guards, ensemble >=0.55, today-only Riga, supported markets and distinct fixtures/teams. Existing DC is prepared first. The market lane prepares at most one additional disjoint triple per natural discovery; never forces picks, silently falls back or adds provider requests. Existing claims block fixture reuse; cross-lane claims also atomically block same-day team overlap.

The bounded candidate pool is at most 600; rank at most the top 60 eligible fixtures for combination enumeration. Diagnose omitted rank tail honestly. A ten-second quote preparation budget fails the second lane closed. No inline fitting or research-model dependence.

Show COMBO Tirgus tests in the existing enrolled private COMBO bot. Keep original publication membership, a separate cohort and all wins/losses/voids. Early loss, remaining-leg tracking and text/photo Reply persist through compatible flag-off rollback. All-time aggregate remains the union; old cohorts remain unchanged.

Compare coverage, completed cohort win rate/flat ROI, odds and skips. Early losses resolve sooner than winners; unfinished cohort ROI cannot establish superiority. Disjoint published lanes are not a randomized same-fixture comparison. Development replay uses previously captured current odds and is not prospective performance evidence.

Sources reviewed in this conversation:
- https://github.com/martineastwood/penaltyblog and https://penaltyblog.readthedocs.io/en/latest/models/bayesian.html — uncertainty direction, deferred here.
- https://arxiv.org/html/2004.08607v1 — accumulator optimization; its high-odds experiment is not evidence for this policy.
- https://github.com/ohugonnot/golazo — current-market modelling example, not imported or claimed profitable.
The precise two-median policy is our prospective experimental choice, not a published proven method.

Implement/test at normal priority in an isolated worktree, retain exact-base package guards, prepare operator-only install/rollback. No production deployment, manual service cycle, provider request, test send, or automatic promotion during preparation.

## Implemented behavior and development evidence

The existing DC lane retains first choice each cycle. The market lane uses the
remaining eligible fixtures and has its own flag, label and frozen statistics.
Both policies retain their original source evidence; research captures are not
relabeled as publication authority. New quotes, model training and provider
requests are not added.

The existing four PREMATCH release routes receive the compatible reader build.
Rollback changes only GOALVISION_COMBO_MARKET_PARALLEL from 1 to 0; DC stays
enabled, SINGLE stays >=1.50, COMBO legs stay >=1.30, and both cohorts continue
settlement, early-loss tracking and original-message replies.

Two saved natural pools were replayed using query-only production input
connections and disposable empty publication ledgers. Previous production
claims were intentionally omitted, so this is a selection/dependency comparison,
not a reconstruction of actual publications or a performance backtest.

- Latest 12:30 Riga pool: 72 candidates; market lane has only two eligible
  fixtures and correctly produces no triple. Both modes retain the same two
  SINGLE selections.
- Preceding 12:00 Riga pool: 2,423 candidates; DC retains exactly the same
  selected triple and the same three SINGLE selections. The market lane has
  150 eligible fixtures, enumerates its declared top 60 and prepares one
  disjoint triple with leg odds 1.34, 1.30 and 1.30. The omitted rank tail is
  recorded as 90. No claims, receipts or Telegram sends are created.

Evidence: docs/evidence/combo_market_parallel_20261004/. These replays establish
mechanics and coverage only. No outcome-based tuning, profitability claim or
champion promotion follows from them.

## Operator activation

Prepared package installation is explicit and separate from development:

    python3 ~/goalvision-operations/combo-market-parallel.py
    sudo python3 ~/goalvision-operations/combo-market-parallel.py --apply

Compatible rollback, preserving the DC lane and both statistics readers:

    sudo python3 ~/goalvision-operations/combo-market-parallel.py --apply --rollback

The operator package pins the installed conservative release 6784969, all 845
base Python/JSON files, eleven reviewed overlays and exact protected service
routes. The assembled release has 847 Python/JSON files. It pauses only the
four existing timers, waits up to 45 seconds for active oneshots without killing
them, switches their release environment routes, and restores their prior
timer states. A busy/failed apply restores the prior configuration. No manual
cycle is started. Root apply additionally checks the installed ADMIN disable
guards; unprivileged preflight explicitly reports that remaining check.

After installation, await natural publication and settlement. Review separate
mature cohorts with comparable date windows, including unavailable/skip counts,
voids and unsettled coupons. A single winning or losing coupon is not a quality
verdict; the experiment currently has no prospective outcome evidence.

Offline regression: 637 passed in 31.87s with socket connections denied and nice 10. Full fake-provider/Telegram cycle confirms the second-lane reader, COMBO bot routing and durable publication receipts. Champion generation/counters remain unchanged.
