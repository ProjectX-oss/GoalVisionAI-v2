# Current odds capture and forward-test foundation

## Decision and boundary

Paid historical-odds acquisition is paused. The existing provider-probe code is
dormant and inspectable, but operators must not configure or probe TheStatsAPI
for this workflow. GoalVision AI will instead accumulate prospective evidence
from current fixtures under the separate `FORWARD_TEST_REAL_TIME` tier.

Forward-test records never enter historical TRAIN, VALIDATION, TEST, historical
backtests, Official statistics, Official bankroll, High Risk, Combo, or
AutoTrader. They are experimental Lab evidence. This foundation cannot send
Telegram, place a bet, mutate a bankroll, activate production, schedule work, or
run at startup.

## Required order

The operator order is mandatory:

```text
fixture selected -> source/bookmaker selected -> odds captured -> odds sealed
-> match-data snapshot sealed -> Real Match Lab inference -> calibration
-> calibration-quality and shift checks -> market ranking -> forward record
```

Source selection, capture, retrieval, sealing, inference, and kickoff are UTC
timestamps. Capture after inference or kickoff, source changes, quote
replacement, incomplete provenance, and stale odds fail closed. Current odds
reuse the independent 5-minute FRESH, 15-minute AGING, 30-minute STALE scale;
forward observation creation accepts only FRESH or AGING odds, so anything over
15 minutes at inference is rejected. Calibration, feature, lineup, and audit
freshness remain governed by their independent existing policies.

## Input modes

API-assisted mode uses the existing API-Football/API-Sports client only under an
explicit CLI command. Fixture discovery, one-fixture inspection, and current
`/odds?fixture=` retrieval have bounded timeouts and at most two transient-only
retries. Authentication and quota failures are not retried. No API call occurs
at import or startup. If the response supplies `update`, it is retained as the
provider-origin timestamp. Otherwise GoalVision records its retrieval time as
`captured_at_by_goalvision=true`; it is never described as a provider historical
snapshot.

The canonical API-Football credential remains `FOOTBALL_API_KEY`. The client
resolves it lazily from the process environment or the project `.env` file; if
both canonical sources are configured they must agree. No alias is introduced.
Credential resolution never imports the broader startup configuration, prints
the value, mutates the process environment, or performs a network request.

Manual mode uses the versioned template at
`docs/templates/current_odds_manual_v1.json`. The operator may transcribe a
current bookmaker or Flashscore value but must supply provenance and confirm it
was captured before inference. Screenshots are not machine-readable evidence.
Automatic scraping, browser circumvention, CAPTCHAs, logins, and account data are
outside scope.

Both modes support only HOME_WIN, DRAW, AWAY_WIN, totals 1.5/2.5/3.5, and BTTS
yes/no. Correct score and combos are rejected. Decimal odds must be finite and
greater than 1.

## Observation, result, and settlement

Schema v36 adds append-only odds snapshots, observations, results, settlements,
and event chains. Every table rejects UPDATE and DELETE and uses deterministic
fingerprints, foreign keys, idempotent replay, and conflict detection. A forward
observation links one already immutable Real Match Lab analysis and copies its
fixture/features/model input/model/calibration/quality/shift/probability/market/
preview provenance. Legacy analyses are not silently reclassified.

An observation may be retained as completed, no-selection, or blocked.
Mathematical ranking is separate from actionability. All new observations set
Lab send eligibility and Official eligibility to false, including reviewed-real
models; controlled-synthetic models remain non-publication-eligible.

Results append after kickoff with fixture ID, completed status, final score,
source, retrieval time, and provenance. Conflicts fail. Settlement is statistical
only and deterministic for all 11 single markets. No-selection observations are
`NOT_APPLICABLE`; no bankroll transaction is created. The original analysis and
odds are never modified. Manual fallback uses
`docs/templates/forward_test_result_manual_v1.json`; API-Football remains the
preferred result source when an authorized key is available.

## Statistics and limitations

Statistics include every analysis, no-selection, blocked/unpublished record,
loss, settlement, market, competition, source, and month. They report calibrated
and raw Brier/log loss when outcomes exist, match-result and per-market accuracy,
calibration/confidence buckets, hit rate, captured odds/probability/EV, hypothetical
flat-stake ROI, simulated drawdown and runs, plus quality and shift distributions.

Centralized conservative settled-selection states are: below 30
`FORWARD_TEST_SAMPLE_INSUFFICIENT`, 30-99 `FORWARD_TEST_EARLY_EVIDENCE`, 100-299
`FORWARD_TEST_REVIEWABLE`, and 300+ `FORWARD_TEST_STATISTICALLY_MEANINGFUL`.
These are reporting maturity gates, not proof of profitability or authorization.
All ROI and drawdown values are explicitly simulated; no stake or bankroll exists.

The read-only integrity audit checks order, kickoff, provenance, model and
calibration links, quality and shift records, evidence-tier separation, and zero
Lab/Official authorization. Pending results remain visible rather than excluded.

## Operator commands

Run `python -m app.current_odds_forward_test --help` for all commands. The main
flow is `discover-current-fixtures` or manual fixture selection,
`capture-current-odds`, existing Real Match Lab `analyze`,
`create-forward-test-observation`, inspections, `record-forward-test-result`,
`settle-forward-test-observation`, `forward-test-statistics`, and
`audit-forward-test`. Inspection never creates a Telegram transport.

Use `diagnose-api-football` for a single explicit, sanitized account/plan check.
`discover-current-fixtures` accepts hard ceilings for candidate count and API
calls, orders fixtures by kickoff then provider ID, checks baseline recent-form
availability before requesting odds, and never runs inference itself. A zero
fixture response is an honest `NO_ELIGIBLE_CURRENT_FIXTURE` result.

Reproduce only against an isolated schema-v36 database. Verify foreign keys and
append-only triggers, export sanitized evidence, and compare the protected
database hash before and after. A future Betfair Exchange read-only adapter may
reuse the current-odds contract only after explicit credential and legal review;
no authenticated Betfair work is included now.
