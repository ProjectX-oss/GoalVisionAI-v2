# Reviewed historical odds

This package provides offline-only, deterministic source review, immutable
manifests, exact event linkage, quote normalization, a fixed-bookmaker 24-hour
cutoff, coverage reporting, and backtest-integrity auditing.

Schema v35 adds immutable source-review versions, the exact persisted-split
acquisition window, and partition-level coverage sufficiency. The offline
archive parser accepts deterministic JSON arrays or JSON Lines and supports all
11 canonical single markets. Source-specific quote selection is explicit and
versioned; the original fixed Pinnacle 24-hour policy remains the primary
default.

It never fetches data, publishes predictions, activates models, or mutates an
Official bankroll. Raw provider files remain in operator-controlled ignored
storage. Inspection and import require an explicit local file.

`build-extended-coverage-foundation` is network-inert. It records reviewed
access findings and returns `REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE` when no
approved raw archive overlaps TEST. It never treats missing evidence as zero
performance and cannot authorize publication or activation.
