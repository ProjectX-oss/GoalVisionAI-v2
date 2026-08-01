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
`diagnose-fixture-discovery` preserves endpoint, method, non-secret query,
provider errors, result count, paging and exact quota headers under `var/` when
an ignored metadata output is requested. API-Football requires another selector
with `from`/`to`; an unfiltered range is a rejected HTTP-200 response, not an
empty schedule. Adaptive discovery therefore uses supported `date` plus `UTC`
queries and never interprets a non-empty provider `errors` object as zero data.

`discover-current-fixtures` accepts hard ceilings of 50 candidates and 40 real
HTTP attempts, keeps a daily quota reserve, and respects the independent
per-minute counter. The exact header meanings are: `x-ratelimit-requests-*` for
the daily subscription quota and `x-ratelimit-*` for the minute window. Missing
or inconsistent headers fail closed.

Competition identities and active seasons come from `/leagues?current=true`.
A provider `current=true` season whose end date is already past is rejected as
stale. The reviewed priority list is fixed before inference; discovery searches
priority competitions over accessible UTC dates, then falls back to all current
provider-covered senior League/Cup fixtures while excluding youth, reserves,
virtual/esports, friendlies, malformed identities, started, postponed,
cancelled, abandoned and too-close fixtures. Ordering is earliest safe kickoff,
competition priority, then provider fixture ID. At least one genuine completed
recent match for each team is required before a fixture's odds are requested;
the exact sample sizes remain explicit rather than pretending every team has
five accessible matches. Each fixture receives at most one odds
request, and inference remains a separate explicit operation.

Provider plan date coverage is itself evidence. The configured plan exposed
2026-07-31 through 2026-08-02 during the 2026-08-01 diagnostic; later requested
dates were rejected and were not treated as empty fixture days. Odds coverage
metadata comes from each league season's `coverage.odds`; `/odds/leagues` is not
a valid API-Football v3 endpoint.

### Discovery request efficiency

The current discovery request planner records integer call costs, retries,
cache hits/misses, required/optional status and the rejection reason for every
deeply considered candidate. Date-level fixture retrieval is a shared cost;
each candidate has zero incremental fixture-list cost. Before starting a
candidate, the planner reserves all uncached team-history calls plus one exact
fixture-odds call. Local snapshot sealing and observation creation have zero
provider-call cost. A candidate is never partially started when the complete
mandatory provider cost cannot be funded.

Fixture-list fields and the cached league-season coverage record now reject
malformed identities, incompatible seasons, unsupported types, explicit lack
of fixture or odds coverage, excluded classes, unsafe kickoffs and duplicate
events before detailed calls. Candidate order is fixed from pre-inference
facts: reviewed competition priority, reusable context-matched team data,
kickoff and provider fixture ID. Model probability, EV and market
attractiveness are never inputs to fixture selection.

The capability cache is sanitized, fingerprinted, conflict-checked and valid
for six hours under ignored `var/`. It records league, season, dates and
fixtures, standings, injuries, lineups, statistics and odds coverage. Loading
it does not trigger network activity; an explicit operator discovery refreshes
quota with one status request. Team histories are reusable for 15 minutes only
when team, league, season and evaluation cutoff all match. Standings use a
separate league-season cache. Optional standings, injuries, lineups and richer
statistics are not requested before required baseline viability. When later
required, run-local season aggregates, injuries and lineups are keyed by their
team/competition/fixture identities and expire after six hours, four hours and
one hour respectively.

API-Football documents multi-ID fixture retrieval for up to 20 known fixture
IDs and an injury `ids` filter. Neither can discover the unknown historical
fixture IDs needed for current team form. Pre-match odds can be queried by date
but return ten results per page; exact fixture odds remain the smallest,
identity-safe request. Bookmaker filtering is supported but GoalVision has no
predeclared single-bookmaker policy, while one bet filter cannot supply all
canonical markets.

The optimized real run returned 967 fixtures, prefiltered 620, planned seven
candidates and made deep calls for six. Each failed after one home-team history
call, rather than spending both team calls. The provider returned HTTP 200 with
`plan: Free plans do not have access to this season, try from 2022 to 2024.`
for the valid team+league+2026 query. Mixing 2022–2024 history into a 2026
league-season context would violate baseline provenance, so odds and inference
remained at zero. A provider plan with current-season history access is now the
honest prerequisite for the first genuine automated forward observation.

Reproduce only against an isolated schema-v36 database. Verify foreign keys and
append-only triggers, export sanitized evidence, and compare the protected
database hash before and after. A future Betfair Exchange read-only adapter may
reuse the current-odds contract only after explicit credential and legal review;
no authenticated Betfair work is included now.
