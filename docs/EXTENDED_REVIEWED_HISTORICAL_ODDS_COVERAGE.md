# Extended Reviewed Historical Odds Coverage Foundation

## Honest outcome

The foundation is complete, but no lawful source with authorized local access
provided odds for the immutable TEST partition. The controlling result is
`REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE`. No split boundary was moved, no
timestamp was inferred, and no synthetic or untimestamped odds were substituted.

The protected `data/goalvision.db` remained unchanged. All rehearsal writes were
isolated under ignored operator storage. Telegram calls, deliveries, Official
publications, bankroll/statistics mutations, production activation, and
scheduling/startup changes are zero.

## Immutable acquisition window

Split ID:
`historical-dataset-split-a86228e7921bc560b897a3fd0e3187bb78df31adedfbc6f5ce107ff87d7d9977`

Split fingerprint:
`2fb37779db0dd6eab9f46cc12482809780f68c5083c499b61b137d06c318a077`

| Partition | Matches | First kickoff UTC | Last kickoff UTC |
| --- | ---: | --- | --- |
| TRAIN | 1,459 | 2018-09-21T18:30:00Z | 2023-05-12T18:30:00Z |
| VALIDATION | 313 | 2023-05-13T13:30:00Z | 2024-05-11T13:30:00Z |
| TEST | 313 | 2024-05-11T16:30:00Z | 2025-05-17T13:30:00Z |

Equal kickoff groups remain indivisible. There are zero temporal-gap
exclusions. The reviewed universe spans Bundesliga seasons 2018/19 through
2024/25. All 313 VALIDATION and all 313 TEST matches need genuine odds. A
legitimate primary pilot requires complete HOME_WIN, DRAW, and AWAY_WIN quotes;
all 11 single markets are preferred.

## Additional source reviews

The source reviews under `docs/data_sources/` were recorded from normal public
documentation access on 2026-08-01.

- The Odds API historical archive is the closest technical fit. Official docs
  describe German Bundesliga historical snapshots and timestamp semantics, but
  historical access is paid-only and no authorized key exists in the
  environment. Status: `ACCESS_UNAVAILABLE`.
- Sportmonks Premium Odds Feed documents fixture-linked opening odds and price
  changes. Access requires a subscription and odds add-on; the general history
  endpoint is available only until seven days after kickoff, and no licensed
  retrospective export exists locally. Status: `ACCESS_UNAVAILABLE`.
- Betfair Historical Data supplies timestamped exchange data, but requires
  eligible account/package access and commission-aware exchange normalization.
  Personal bookmaker account data is outside scope. Status:
  `ACCESS_UNAVAILABLE`.

No API request, login, purchase, paywall bypass, scraping, or raw download was
attempted. Public CSV/mirror sources without capture timestamps remain blocked.

## Schema and replay

Migration v35 adds three append-only boundaries:

- versioned source reviews, allowing a new immutable legal/access assessment to
  supersede an older assessment without mutation;
- one fingerprinted acquisition window for the persisted split;
- fingerprinted partition coverage reports with explicit sufficiency status.

Every table is foreign-key protected where references exist and rejects UPDATE
and DELETE. Exact replay is idempotent; changed content under the same immutable
identity fails closed. Existing v34 evidence is not changed.

The offline The Odds API parser supports a single snapshot, a JSON array of
snapshots, or JSON Lines. It normalizes HOME_WIN, DRAW, AWAY_WIN, totals at
1.5/2.5/3.5, and BTTS yes/no. Missing capture time, odds at or below 1.0,
post-kickoff quotes, invalid points/selections, conflicting quote identities,
reversed fixtures, and ambiguous links remain non-actionable.

## Quote-selection policies

The primary policy remains
`fixed-pinnacle-latest-at-or-before-24h-v1`. It chooses the latest Pinnacle
quote at or before kickoff minus 24 hours and never searches historical best
prices.

The foundation also supports a typed reviewed-bookmaker-set policy. That policy
fails unless the exact bookmaker set and a genuine historical odds-comparison
capability were predeclared. It is not selected after model, ROI, or settlement
results. Sensitivity cutoffs remain secondary analysis only.

## Coverage, integrity, and promotion

Current new-source counts are zero: no manifest, raw quote, normalized quote,
linked event, VALIDATION match, TEST match, candidate market, or selected bet.
This is missing evidence, not zero-return evidence.

- Coverage: `REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE`
- Backtest integrity: `BACKTEST_INTEGRITY_BLOCKED` (`TEST_ONLY`)
- Calibration: unchanged and ineligible because AWAY_WIN and OVER_2_5 retain
  excessive MCE
- Shadow: `SHADOW_EVIDENCE_INSUFFICIENT`
- Comparison/promotion: `INSUFFICIENT_TEST_ODDS_COVERAGE`
- Independent audit: `AUDIT_BLOCKED`
- Staging activation: not executed
- Real Match Lab rehearsal: not executed
- Publication eligibility: false

No betting, ROI, yield, drawdown, volatility, confidence interval, or subgroup
stability metric is reported because no decisive TEST bet exists.

## Offline reproduction

1. Verify the protected database hash before work.
2. Review each source JSON and obtain explicit operator authorization before
   changing an access status.
3. Keep restricted raw files in ignored operator storage and verify their
   SHA-256 hashes.
4. Run `python -m app.reviewed_historical_odds validate-raw-odds-file ...`.
5. Run the explicit import against an isolated migrated database.
6. Inspect links, ambiguous/unmatched events, partition coverage, quote
   selections, TEST coverage, integrity, and canonical evidence offline.
7. Verify foreign keys, append-only triggers, deterministic replay, protected
   database hash, and zero side effects.

## Exact next step

An operator must provide either an approved licensed export or an authorized API
credential with sufficient historical quota for the exact 2023-05-13 through
2025-05-17 acquisition window. A separate post-TEST shadow window must be
registered before evaluation. Only after sufficient coverage, TEST-only
backtesting, calibration quality, independent shadow evidence, comparison, and
audit all pass could staging activation be considered. Any Lab publication
would still require separate explicit authorization.
