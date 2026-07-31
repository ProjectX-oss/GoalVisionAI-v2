# Reviewed Historical Odds and Betting Evidence Foundation

## Outcome

The foundation is implemented and exercised with genuine timestamped
pre-kickoff odds, but promotion remains blocked. The only lawful source that
could be accessed without credentials was The Odds API's official public
Bundesliga sample. It covers 18 matches in October 2022, all in the immutable
TRAIN period, and therefore cannot be used for TEST betting evidence.

`GENUINE_TEST_PRE_KICKOFF_ODDS_UNAVAILABLE` is the controlling blocker. No
synthetic odds, closing-odds assumptions, or post-kickoff quotes replace the
missing evidence.

## Source review

Every source is reviewed before import. Reviews capture provider ownership,
access and authentication, terms, redistribution, commercial and storage
conditions, derived-data permission, historical/competition/bookmaker/market
coverage, timestamp precision, quote semantics, event identity, rate limits,
reliability, review time, operator note, and typed approval status.

- The Odds API public sample: `APPROVED_FOR_INTERNAL_DERIVED_DATA`. Provider
  terms permit analytical applications but prohibit standalone resale,
  repackaging, or redistribution. The raw snapshot stays outside Git.
- BALLDONTLIE opening odds: `ACCESS_UNAVAILABLE`. A GOAT subscription and API
  key are required; no credential was available and no access control was
  bypassed.
- DataHub/football-data.co.uk mirror: `TERMS_UNCLEAR`. Although DataHub states a
  PDDL license, upstream bookmaker-odds rights need clarification and quote
  capture timestamps are absent. It was not downloaded or imported.

Source reviews live under `docs/data_sources/`. Refreshing a source requires a
new version, UTC acquisition timestamp, file hashes, and a new immutable
manifest. Reusing a source ID/version with different content is rejected.

## Raw storage and reproduction

The reviewed raw sample is held only in operator-controlled temporary/ignored
storage. Git contains its SHA-256, byte count, provenance, source review,
manifest, sanitized aggregate evidence, and a synthetic provider-shape test
fixture. Credentials, private URLs, cookies, account sessions, and reconstructable
raw provider data are never exported.

Reproduction is offline:

1. Obtain the official public sample from the URL in its source review.
2. Verify SHA-256
   `e02b2f9b2f3ce643de7e03a8ee8c1e458553ddebfb40a8d681cad936c2c74c04`.
3. Copy the reviewed-real v33 pilot database to an isolated path.
4. Run `python -m app.reviewed_historical_odds run-pilot ...` with explicit
   review, evidence, branch, commit, and UTC timestamp arguments.
5. Validate the canonical evidence fingerprint and SQLite foreign keys.

Inspection commands never make network calls.

## Manifest and normalized odds

Migration 34 adds append-only, foreign-key-protected records for source reviews,
manifests, source files, event links, normalized quotes, quote selections,
coverage, betting integrity, betting evidence, shadow summaries, and audits.

The pilot parsed 591 genuine 1X2 quotes from 18 events and 12 bookmakers. Every
quote has a source identity, bookmaker, source market and selection, decimal
odds, bookmaker update timestamp, source snapshot timestamp, linked kickoff,
manifest reference, provenance fingerprint, and quote fingerprint. Eighty-one
exchange-lay rows were explicitly excluded because the current canonical
single-market contract does not model lay commission semantics.

Decimal, American, and fractional conversion functions are deterministic.
Non-finite values, odds at or below 1.0, unsupported mappings, unknown capture
times, post-kickoff timestamps, future acquisition-relative timestamps, and
conflicting duplicates fail closed.

## Event linkage and aliases

Linkage requires home/away orientation, kickoff UTC, and exact canonical team
identities. Ten reviewed aliases bridge documented provider spellings such as
`FC Koln` to `1. FC Köln`. Fuzzy-name-only linkage is forbidden. Exact,
reviewed-alias, explicitly configured timestamp-tolerance, ambiguous, missing,
reversed/conflicting outcomes are typed and persisted. All 18 sample events
linked; none were ambiguous or unlinked.

Kickoff tolerance defaults to zero. A postponed fixture may use a non-zero
tolerance only when an operator supplies and documents it; a reversed fixture
is always rejected.

## Pre-kickoff and quote-selection semantics

The decision policy is
`fixed-pinnacle-latest-at-or-before-24h-v1`:

- calculate `kickoff UTC - 86,400 seconds`;
- consider only immutable Pinnacle quotes captured at or before that cutoff;
- choose the latest eligible quote by capture time, source quote ID, then quote
  fingerprint;
- never search other bookmakers for the historically best price;
- never select a quote after prediction or outcome knowledge.

This models access to one fixed bookmaker and avoids best-price hindsight. The
sample produced 54 deterministic decisions across HOME_WIN, DRAW, and AWAY_WIN.
The same policy would apply to totals and BTTS when a reviewed source provides
those canonical markets.

## Coverage and partition isolation

Coverage is reported against all 2,142 reviewed Bundesliga matches:

- 18 matches with any odds and complete 1X2;
- 0 with totals, BTTS, or all 11 markets;
- 591 normalized TRAIN quotes;
- 0 VALIDATION quotes;
- 0 TEST quotes;
- 0 missing capture timestamps, post-kickoff exclusions, ambiguous links,
  unlinked events, conversion errors, or quote conflicts.

The 313-match TEST window is 2024-05-11T16:30:00Z through
2025-05-17T13:30:00Z. Because it has no valid odds, the TEST backtest does not
run. Candidate markets, selected bets, settlements, bankroll movement, ROI,
drawdown, volatility, confidence intervals, and subgroup betting stability are
all unavailable rather than reported as zero-performance evidence.

## Calibration, comparison, shadow, and activation

Odds are never labels and do not alter model fitting. Both reviewed-real
candidates retain their prior VALIDATION-only Platt calibration. Both remain
`CALIBRATION_QUALITY_INELIGIBLE` because AWAY_WIN and OVER_2_5 have excessive
maximum calibration error.

The best predictive candidate remains the regularized model, with TEST Brier
`0.2148169795669686676381753730` and log loss
`0.6194453508842156051318617485`. This is predictive evidence only.

The comparison and promotion outcome is `INSUFFICIENT_BETTING_EVIDENCE`.
Backtest integrity is blocked only by the absence of TEST selections. Independent
shadow evidence is also insufficient because no non-overlapping post-TEST odds
window exists. The aggregate audit is `AUDIT_BLOCKED`; staging activation and
Real Match Lab rehearsal were not executed.

## Safety and publication boundary

Evidence tier is `REVIEWED_REAL_HISTORICAL`, not `PRODUCTION_AUTHORIZED`.
Publication eligibility is false. The workflow performs no Telegram calls,
deliveries, Official publications, Official bankroll/statistics mutations,
production activation, scheduling, or fixture discovery. Reviewed historical
evidence never grants publication authorization by itself.

Historical backtest performance is not guaranteed future performance. Low
sample results are not proof of profitability. No Telegram publication or
production activation is authorized.

## Next required step

Acquire an authorized immutable timestamped Bundesliga odds archive covering
the exact 2024/25 TEST window and a separate post-TEST shadow window, ideally
with the same fixed bookmaker and all supported 1X2, totals, and BTTS markets.
Then rerun coverage, calibration-quality review, TEST-only backtesting,
uncertainty and stability analysis, independent shadow evaluation, comparison,
and audit. A genuine Lab publication can only be considered after every staging
gate passes and separate publication authorization is granted.
