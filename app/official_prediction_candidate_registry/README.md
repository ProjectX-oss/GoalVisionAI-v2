# Official Prediction Candidate Registry

This package is the deterministic ingestion boundary between existing or future
prediction-generation components and the manual Official run coordinator. It
accepts fully supplied pre-match facts, validates and normalizes them, appends
an immutable candidate version, and exposes only the current structurally
`READY` version for later orchestration.

`READY` means structurally complete and discoverable. It does not mean that the
candidate passed calibration selection, model-health checks, risk, exposure,
bankroll checks, the Official Quality Gate, publication claims, or Telegram
delivery. Those responsibilities remain in their existing packages.

## Registration boundary

`register_official_prediction_candidate(registry, command)` requires all facts
and timestamps explicitly. The production composition function is
`build_official_prediction_candidate_registry(...)`. Construction performs the
v14 additive migration but never ingests, runs the coordinator, constructs
Telegram credentials, or publishes.

Only Official bankroll and destination scopes and these pre-match single-bet
markets are accepted:

- match winner / moneyline / 1X2;
- double chance;
- totals / over-under with a positive finite line;
- both teams to score.

Correct score, live/in-play, accumulators, arbitrary selections, non-Official
scopes, malformed Decimal facts, future source facts, and post-kickoff
registration are rejected before persistence. Odds below or equal to `1.00`
are structurally invalid, but final publication thresholds such as Official
minimum odds and EV policy remain Quality Gate responsibilities.

Reasoning is a bounded ordered tuple of approved structured fact types. Text is
Unicode/whitespace normalized without inventing or rewriting evidence. URLs,
HTML, affiliate or credential content, promotional guarantees, risk-free
claims, and correct-score wording are rejected.

## Normalization and identity

IDs use bounded NFKC, case-folded safe identifiers. Public competition and team
display names are retained in NFC display form, while separate NFKC/case-folded
comparison names drive identity-independent matching. Decimal values use
lossless normalized strings, timestamps use explicit UTC ISO-8601 strings, and
reasoning facts are ordered by type, normalized text, and source reference.

The logical identity contains prediction ID, match ID, model version,
normalized market/selection/line, and Official bankroll/destination scopes.
The source event ID is provenance, not logical identity.

The content SHA-256 adds all material supplied facts: source event and source
snapshot identities, competition and teams, timestamps, model and market facts,
probability, EV, odds and source, lineup and injury facts, confidence,
supporting-data and market-availability states, ordered reasoning facts, and
scopes. Registration time is stored in the append-only audit but excluded from
the content fingerprint, so repeated identical ingestion remains idempotent.
Display-only whitespace or Unicode representation changes do not allocate a
new version.

## Lifecycle and publication protection

Version 1 is appended as `READY`. Identical content returns the existing
version. Materially changed content receives the next transactionally allocated
version, appends `SUPERSEDED` for the prior active version, and appends `READY`
for the replacement in one SQLite transaction. Only the latest active version
is discoverable; historical snapshots and previous Quality Gate,
orchestration, publication, settlement, and run history remain immutable.

`withdraw_candidate(...)` and `invalidate_candidate(...)` require explicit
reason codes and append `WITHDRAWN` or `INVALIDATED`. Historical versions cannot
be reactivated in place; a new valid version must be registered.

An identical already-recorded submission remains idempotent. A materially
changed submission is not activated when prediction-level state is published,
actively claimed, indeterminate, or unknown. The registry does not implement
correction messages and never weakens atomic publisher duplicate protection.

Registration statuses are `REGISTERED`, `IDEMPOTENT_EXISTING`,
`SUPERSEDED_PREVIOUS`, `REJECTED_INVALID`, `REJECTED_SCOPE`,
`ALREADY_PUBLISHED`, `CORRECTION_REQUIRED`, `CONFLICT`, and
`PERSISTENCE_FAILURE`.

## Coordinator and orchestration integration

`build_registry_candidate_source(database, context_provider)` creates the
read-only adapter for the existing coordinator source port. The registry
repository returns only active, unexpired, Official `READY` versions in explicit
kickoff, prediction-creation, prediction-ID, and candidate-version order. The
coordinator then applies its configured lookahead, minimum time, batch limit,
publication history, retry, rejection/review freshness, active-claim, and
indeterminate rules.

The injected context provider reads existing calibration, model-health, risk,
exposure, and bankroll records. The adapter does not calculate or copy them; it
supplies them to `prepare_and_publish_official_prediction(...)`, whose assembler
still selects the applicable records and whose Quality Gate still decides
publication eligibility. Registry candidate identity and content fingerprint
are retained in the orchestration normalized snapshot. The registry never calls
the publisher directly.

Migration v14 adds `official_prediction_candidate_versions` and
`official_prediction_candidate_lifecycle_events`, with deterministic snapshots,
foreign keys, unique content/version identities, ordered indexes, and update and
delete prevention triggers.

Intentionally deferred: prediction generation, external providers, scraping,
bookmaker APIs, automatic ingestion, scheduling, background workers, correction
messages, Telegram delivery, live betting, Combo, High Risk, Lab, and AutoTrader
workflows.

## Future upstream data boundary

The independent `app.match_data_snapshot` and `app.feature_store` packages now own
supplied pre-match provenance and deterministic model-ready features. They do not
invoke this registry. A future reviewed prediction engine may consume a feature set
and then supply its complete prediction facts here; registry identity, validation,
versioning, and publication protection remain unchanged.
