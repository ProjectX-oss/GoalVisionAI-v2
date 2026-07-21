# Official Prediction Selection Engine

This package is the deterministic boundary between persisted market-value
assessments and future Official risk assessment. It consumes only an explicit,
bounded collection of immutable `MarketValueAssessment` records for one match.
It verifies each record against durable history, evaluates every assessment,
deduplicates logical markets, applies the versioned ranking policy, and persists
either one selected Official single or an explicit no-selection decision.

## v1 policy

- Official bankroll and destination scopes only.
- Pre-match single markets only: match winner, double chance, totals, and both
  teams to score. Correct score and live markets remain forbidden.
- Decimal odds must be at least `1.60`; expected value must be at least `0.02`.
- Only upstream `POSITIVE` or `STRONG` and `ACTIONABLE` assessments qualify.
- Fresh assessments qualify. Aging assessments require an explicit policy;
  stale and expired assessments fail closed.
- Published, actively claimed, indeterminate, and unknown publication states
  fail closed. The adapter reads existing publication history without claiming
  or mutating it.
- At most one assessment is selected. Ranking is deterministic: expected value,
  fair probability, absolute edge, odds, freshness, odds-effective time, market
  priority, selection priority, line, bookmaker, assessment ID, and fingerprint.

The engine never calculates probabilities, calibration, odds, expected value,
stakes, exposure, or bankroll decisions. It never calls providers, candidate
registration, the Quality Gate, publication, Telegram, or scheduling. It has no
clock and no random source.

## Persistence and idempotency

Migration v20 adds append-only decision and evaluation tables. A selected and a
no-selection result are equally durable. Each request identity is unique; exact
replay returns `IDEMPOTENT_EXISTING`, while identity reuse with different
content returns `CONFLICT`. The decision and every evaluation are inserted in
one SQLite transaction and protected by update/delete rejection triggers.

Use `build_official_prediction_selection_service(...)` with explicit policies,
repository, and publication-state protection. Call
`select_official_prediction(...)` with an immutable command. A successful
selected decision can be mapped through `to_official_risk_handoff(...)`; that
mapping carries verified provenance and value facts only and makes no staking
recommendation.
