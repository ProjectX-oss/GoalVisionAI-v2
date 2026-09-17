# Reviewed Real Historical Data

This package is the network-inert governance and audit boundary for genuine
historical sources. It requires a typed source review before manifest
registration or import, fingerprints every supplied file, parses only explicit
operator-provided snapshots, and fails closed for rejected, unclear, unavailable,
or review-required sources.

The OpenLigaDB adapter accepts only finished matches with an explicit UTC kickoff,
teams, competition, season, and valid final score. Raw acquisition is deliberately
outside runtime and outside Git. The adapter never calls a network, guesses a
kickoff, fabricates odds, fuzzy-merges teams, or treats post-match fields as
pre-kickoff features.

Migration 33 adds append-only source reviews, manifests, source-file identities,
team aliases, feature coverage, data-quality and leakage reports, plus explicit
evidence tiers. `REVIEWED_REAL_HISTORICAL` is constrained to remain publication
ineligible. `PRODUCTION_AUTHORIZED` requires a separate authorization reference;
this package never creates that tier.

The pilot composes the existing historical import, canonical 78-feature projection,
chronological split, training, validation-only calibration, and TEST prediction
foundations. Missing genuine pre-kickoff odds produce a typed betting-evidence
limitation and block comparison promotion, shadow readiness, audit readiness,
activation, rehearsal, and publication.

Operator commands:

```text
python -m app.reviewed_real_historical_data review-source --review <review.json>
python -m app.reviewed_real_historical_data validate-source-files --source-file <season.json> --dataset-version <version>
python -m app.reviewed_real_historical_data run-pilot --database <isolated.db> --source-file <season.json> --review <review.json> --source-version <version> --execution-timestamp <UTC>
```

All commands are manual. Inspection and validation never make network calls. No
command constructs Telegram, Official publication, bankroll, activation, scheduler,
or production resolver services.
