# Reviewed historical odds

This package provides deterministic source review, immutable
manifests, exact event linkage, quote normalization, a fixed-bookmaker 24-hour
cutoff, coverage reporting, and backtest-integrity auditing.

Schema v35 adds immutable source-review versions, the exact persisted-split
acquisition window, and partition-level coverage sufficiency. The offline
archive parser accepts deterministic JSON arrays or JSON Lines and supports all
11 canonical single markets. Source-specific quote selection is explicit and
versioned; the original fixed Pinnacle 24-hour policy remains the primary
default.

It never fetches data during import, application startup, or ordinary inspection,
publishes predictions, activates models, or mutates an Official bankroll. Raw
provider files remain in operator-controlled ignored storage. The only network
paths are the explicitly invoked `provider-diagnose` and `coverage-probe`
commands. Both are bounded and fail before client creation when the documented
provider credential is absent.

`build-extended-coverage-foundation` is network-inert. It records reviewed
access findings and returns `REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE` when no
approved raw archive overlaps TEST. It never treats missing evidence as zero
performance and cannot authorize publication or activation.

The credential-ready workflow is documented in
`docs/HISTORICAL_ODDS_PROVIDER_COVERAGE_PROBE.md`. Bulk acquisition remains
separately gated by approved terms, confirmed sampled coverage, sufficient
provider-reported quota, and an exact operator confirmation phrase.

The Football-Data CSV adapter is a separate offline, fail-closed raw-evidence
path. It preserves source file/row/column/bookmaker/value provenance and exact
fixture links, but never converts Football-Data cells into actionable quotes
because the archives have no row-level capture timestamps. See
`docs/FOOTBALL_DATA_HISTORICAL_ODDS_FOUNDATION.md` and the
`import-football-data-foundation` CLI command.
