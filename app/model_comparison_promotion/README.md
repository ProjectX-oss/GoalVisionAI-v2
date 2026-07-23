# Model Comparison and Promotion Foundation

This Lab-only package compares one explicit immutable champion against one or
more explicit immutable challengers. It produces auditable evidence and a
promotion **recommendation**, never model activation.

## Sources and fair scope

Every model artifact, calibration artifact set, and completed TEST backtest is
loaded by explicit identity and fingerprint. Model/calibration/backtest
linkage, the canonical 11-target contract, feature and label schemas, policy
versions, currency, metrics, settlements, and bankroll ledger must verify.
Uncertainty fails closed.

The preferred `EXACT_SHARED_BACKTEST_SCOPE` requires identical TEST examples,
odds identity, policies, and starting bankroll. `INTERSECTION_SCOPE` retains
only the deterministic overlap and records every exclusion.
`POLICY_NORMALIZED_SCOPE` permits only explicit, versioned alignment and
forces review when material caveats remain. Missing bets and outcomes are
never invented.

## Evidence and decisions

The comparison records lower-is-better and higher-is-better predictive,
calibration, betting, and risk deltas; per-target evidence; reliability
quality; grouped market, competition, season, month, odds, probability, EV,
and stake stability; profit concentration; and paired deterministic bootstrap
intervals. Bootstrap seeds derive from comparison identity.

Mandatory source, scope, predictive, calibration, betting, risk, stability,
and evidence gates cannot be offset by a large ROI. Central policy weights are
20% predictive, 20% calibration, 25% betting, 20% risk, 10% stability, and 5%
evidence. Scores are bounded to `[0, 1]`.

Each challenger receives exactly one of:

- `PROMOTE_CHALLENGER`
- `KEEP_CHAMPION`
- `REJECT_CHALLENGER`
- `REVIEW_REQUIRED`
- `INSUFFICIENT_EVIDENCE`

All challengers are evaluated independently. Ranking uses score, evidence
strength, lower drawdown, calibration, predictive quality, betting quality,
then candidate ID. At most one final promotion recommendation is retained.

## Immutability and reproduction

Migration v29 adds ten append-only tables for runs, candidates, source
evidence, metrics, stability, statistical evidence, gates, score components,
recommendations, and exclusions. Complete comparisons commit atomically.
Request reuse is idempotent; changed content under the same request ID is a
conflict. Canonical SHA-256 identities cover requests, sources, metrics,
stability, statistics, candidate evaluations, ranking, and final runs.
Inspection and reproduction helpers are read-only.

This package does not train, recalibrate, backtest, fetch odds, schedule,
publish, access Telegram, change production configuration, run shadow
evaluation, wire live inference, activate a model, or claim guaranteed
profitability.

## ML flow

```text
historical import
  -> historical training dataset
  -> historical dataset split
  -> historical model training
  -> historical probability calibration fitting
  -> historical backtesting
  -> model comparison and promotion recommendation
  -> shadow evaluation (deferred)
  -> controlled production activation (deferred)
```
