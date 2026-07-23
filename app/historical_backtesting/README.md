# Historical Backtesting Foundation

This package is the immutable, deterministic TEST-only evaluation boundary for
GoalVision AI historical machine-learning artifacts.

## Pipeline position

```text
historical import
  -> historical training dataset
  -> historical dataset split
  -> historical model training (TRAIN only)
  -> historical probability calibration fitting (VALIDATION only)
  -> historical backtesting (TEST only)
  -> model comparison and promotion recommendation
  -> future shadow evaluation
  -> future controlled production activation
```

Backtesting reproduces probabilities from one persisted safe model artifact and
one compatible persisted calibration artifact set. It does not fit, refit,
compare, promote, activate, schedule, publish, or contact Telegram.

## Safety and reproducibility

Before evaluation, the service verifies the complete split, fold, dataset,
assignment, example, model, and calibration fingerprint chains. It independently
checks chronology, partition exclusivity, equal-kickoff grouping, feature and
label schemas, source linkage, and prior-feature temporal safety. Only explicit
`TEST` assignments are loaded. `TRAIN`, `VALIDATION`, and excluded assignments
cannot enter evaluation.

Historical odds are caller-supplied immutable datasets. Decision snapshots must
be finite Decimal odds greater than 1.00, carry reproducible source provenance,
match the TEST fixture, and be strictly earlier than kickoff. The explicit
`exact-latest-supplied-pre-kickoff-v1` policy selects the newest observation per
bookmaker and logical market, retains every supplied bookmaker as an assessable
candidate, and deterministically ranks those candidates. It never fetches or
scrapes odds and never synthesizes a market across timestamps.

Optional immutable closing odds are loaded only after selections are frozen.
They can contribute CLV diagnostics but cannot affect selection, staking, or
settlement.

## Markets, value, selection, and staking

Supported Official single markets are match result, over/under 1.5, 2.5, and
3.5 goals, and both-teams-to-score yes/no. Correct score, combos, and
accumulators are unsupported.

For every supported market the package persists calibrated probability, fair
odds, bookmaker odds, implied probability, edge, exact
`probability * decimal_odds - 1` expected value, age, eligibility, and rejection
reasons. Missing and rejected odds remain auditable.

Selection is aligned to the versioned Official selection and ranking policy:
minimum odds 1.60, minimum EV 0.02, deterministic logical-market deduplication,
and at most one single bet per match. Staking is isolated from every real
bankroll and uses the Official 1%, 2%, and 3% bands. It never applies martingale,
loss recovery, borrowing, or loss-driven stake increases.

The explicitly fingerprinted `historical-official-ranking-adapter-v1` preserves
the Official EV, probability, edge, odds, freshness, market, selection, line,
bookmaker, and stable-identity precedence. Historical inputs use canonical
target identities and odds age in place of live assessment freshness objects;
that representation difference is deliberate, versioned, and does not weaken
eligibility.

## Equal kickoff, settlement, and bankroll

Examples are ordered by kickoff, competition, historical match ID, and training
example ID. Every selection at one kickoff is frozen against the same pre-group
bankroll. A deterministic 10% group exposure cap is applied before any match in
the group settles. Only then are immutable final scores settled and the
append-only ledger advanced in deterministic order.

Settlement covers match result, half-goal totals, and BTTS with explicit WON,
LOST, VOID, PUSH, UNSETTLED, and REJECTED states. Half-goal markets normally
produce only WON or LOST. The isolated ledger records stakes, returns, profit,
peaks, drawdown, and the complete fingerprint chain; no deposits, withdrawals,
external balances, or negative bankrolls are permitted.

## Metrics and persistence

Every eligible TEST prediction contributes raw and calibrated binary Brier and
log loss, multiclass Brier and log loss, accuracy, confusion matrices,
probability summaries, per-target reliability bins, ECE, MCE, macro and weighted
aggregates. TEST outcomes are used only after predictions are fixed and never
feed fitting.

Betting metrics cover selections, settlements, stake, return, profit, ROI,
yield, odds, EV, bankroll growth, streaks, volatility, drawdown, calibration
diagnostics, and deterministic target, competition, season, bucket, stake, and
month groups. Optional CLV reports the selected-to-closing odds relationship.
These historical descriptions are not promises of future profitability.

Migration v28 adds ten append-only tables for runs, predictions, supplied odds,
assessments, selections, settlements, the bankroll ledger, metrics, reliability
bins, and exclusions. A backtest is committed atomically. Identical request
replay returns the persisted run; the same request ID with different material
content is a conflict. Canonical Decimal/JSON SHA-256 fingerprints make the
request, prediction, assessment, selection, stake, settlement, ledger, and full
run independently reproducible.

The inspection API is read-only and supports summaries, record lookup, TEST-only
verification, raw and calibrated prediction reproduction, odds-safety checks,
Official-policy alignment, settlement and ledger reproduction, equal-kickoff
verification, metric reproduction, and complete fingerprint verification.

`app.model_comparison_promotion` consumes these completed immutable runs. Fair
comparison defaults to identical TEST examples, supplied odds, policies, and
initial bankroll; versioned intersection and policy-normalized modes preserve
all exclusions. Backtest records are never edited. Multiple challengers are
ranked deterministically, but the resulting recommendation cannot activate a
model.
