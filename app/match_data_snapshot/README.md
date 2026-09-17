# Pre-Match Data Snapshots

`app.match_data_snapshot` owns immutable supplied football facts before kickoff.
It does not fetch, infer, predict, calculate stakes, register Official candidates,
or publish. The explicit boundary is
`register_match_data_snapshot(service, command)`; production composition uses
`build_match_data_snapshot_service(database)`.

The command carries provider/event/snapshot provenance, match and competition
identity, UTC kickoff/effective/source-update/registration timestamps, scheduled
status and venue facts, and optional recent form, venue splits, season records,
head-to-head, availability, context, and odds context. Missing optional facts stay
`None`; the validator never fabricates zeros. Decimal xG, percentages, distances,
lines, and odds are finite `Decimal` values and persist as canonical strings.
Names use Unicode NFKC and whitespace normalization, identifiers are case-folded,
and all timestamps serialize as timezone-aware UTC ISO-8601 values.

## Identity and lifecycle

Logical identity is SHA-256 over match ID, source provider, source event ID, and
kickoff. The source snapshot ID is deliberately provenance/version data: providers
may issue several evidence snapshots for the same scheduled match, so including it
in logical identity would prevent those snapshots from forming one version chain.
The content fingerprint covers every material normalized supplied fact, including
source snapshot identity, but excludes registration execution time. Repeating the
same facts therefore returns the existing version.

Version 1 is `ACTIVE`. A material change atomically appends the next version,
appends `SUPERSEDED` to the old version, and appends `ACTIVE` to the new version.
Explicit withdrawal and invalidation append `WITHDRAWN` or `INVALIDATED` events.
Nothing is updated, deleted, reactivated, or silently replaced.

Validation rejects missing/malformed identities, identical teams, naive or
contradictory timestamps, live/cancelled/completed data, inconsistent status flags,
negative or malformed counts, impossible result totals, clean-sheet or
failed-to-score counts beyond sample size, invalid possession, future evidence,
and malformed optional odds. Odds are context only and are not required.

Migration v15 adds `match_data_snapshot_versions` and
`match_data_snapshot_lifecycle_events`, including unique logical-version/content
identities, query indexes, foreign keys, and update/delete prevention triggers.
