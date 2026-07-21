# Official Prediction Orchestration

This package is the deterministic application boundary future scheduling calls
through
`OfficialPredictionOrchestrationService.prepare_and_publish_official_prediction`.
It assembles supplied immutable Official facts, persists the final Publication
Quality Gate evaluation, and only then delegates an approved candidate to the
injected atomic prediction publisher.

It performs no prediction generation, calibration fitting, expected-value
selection, risk calculation, exposure calculation, bankroll mutation, Telegram
formatting, scheduling, external API access, or direct Telegram sending.

## Ownership and flow

1. Prediction owns the raw probability, market identity, confidence, match
   identity, and prediction time.
2. Probability Calibration owns persisted calibrated probabilities and their
   Brier Score, Log Loss, ECE, MCE, method, version, sample size, and timestamp.
3. Odds and upstream value analysis own decimal odds, odds time, and the
   supplied expected value. Assembly recomputes `calibrated_probability * odds
   - 1` only as a separate audit value and never overwrites supplied EV.
4. Model monitoring owns model-health facts.
5. Risk Management and Exposure own their immutable decisions. Orchestration
   selects matching facts but never recalculates either decision.
6. Bankroll owns the Official scope and snapshot identity. Orchestration never
   reserves or changes money.
7. Publication persistence owns delivery state. Assembly only reads it.
8. The Publication Quality Gate owns final eligibility policy and is persisted
   before any publisher call.
9. The injected atomic publisher owns claims, retries, Telegram delivery, and
   the published marker. This package never sends a Telegram message itself.

## Selection rules

- Calibration records must match both model version and raw probability. The
  newest record at or before the supplied evaluation time is selected; equal
  timestamps use lexicographically greatest calibration run ID. Identity is
  accepted only when it is an explicit persisted Identity report.
- Model-health records must match the model version and cutoff. Equal
  timestamps use record ID.
- Risk and exposure records must match prediction ID, match ID, model version,
  normalized market, normalized selection, market line, and Official bankroll
  scope. The newest matching record at or before evaluation time is selected;
  equal timestamps use evaluation ID.
- Future records are ignored. Absence of a matching record fails closed.
- Publication state distinguishes never attempted, claimed, attempting,
  published, confirmed retryable failure, and indeterminate failure.

## Fingerprint v1

The canonical SHA-256 fingerprint contains every material selected fact:
prediction and match IDs; model version; normalized market, selection, and
line; raw and calibrated probabilities; supplied and verified EV; odds and
odds time; confidence; prediction, kickoff, evaluation, and core-data times;
supporting-data, market-availability, lineup, and injury states; calibration
run, version, method, timestamp, sample size, Brier Score, Log Loss, ECE, and
MCE; model-health record, state, and timestamp; risk and exposure evaluation
IDs, decisions, and timestamps; bankroll reference, scope, and timestamp; and
publication state, state timestamp, and attempt reference.

Keys are sorted, Decimals use normalized base-10 text, aware datetimes are UTC
ISO-8601 text, and enums use their stable values. Input collection order is not
included, so irrelevant repository ordering cannot change the fingerprint.

## Outcomes and failure behavior

The service returns exactly one immutable status: `PUBLISHED`,
`APPROVED_NOT_PUBLISHED`, `REJECTED`, `REVIEW_REQUIRED`, `DUPLICATE_BLOCKED`,
`RETRYABLE_PUBLICATION_FAILURE`, `INDETERMINATE_PUBLICATION_FAILURE`, or
`ASSEMBLY_FAILED`.

Assembly, Quality Gate evaluation, and Quality Gate persistence fail closed.
Confirmed pre-send failures may use the publisher's existing retry path.
Unknown or post-send failures become indeterminate and are never automatically
resent. No SQLite transaction remains open while the publisher performs its
network operation.

Dry-run still assembles and persists the gate evaluation, records
`APPROVED_NOT_PUBLISHED` for approved facts, and never invokes the publisher or
mutates Telegram, bankroll, settlement, or publication state. A disabled
injected publisher behaves the same and is explicitly reason-coded.

## Runtime integration

`build_official_prediction_orchestration_service(database, publisher)` builds
the production service using SQLite gate/orchestration history and publication
state adapters. Alternatively, supplying the Telegram sender, public-facts
provider, Official destination, and clock constructs the concrete atomic
publisher in `app.official_prediction_publication`. Construction has no side
effects beyond additive migration. No scheduler calls it today, and application
startup does not create a claim or send a message.

Intentionally deferred: automatic scheduling, provider ingestion, explicit
operator recovery for active or indeterminate claims, combo creation, live
betting, and non-Official products.

## Manual batch caller

`app.official_prediction_run_coordinator` is the application layer immediately
above this package. It supplies each persisted immutable request with the
explicit batch evaluation timestamp and dry-run flag, then calls
`prepare_and_publish_official_prediction(...)` exactly once for every eligible
reference. It does not enter or modify assembly, Quality Gate, or publisher
logic. No scheduler or startup hook invokes the coordinator.

## Registry-supplied candidates

`app.official_prediction_candidate_registry` can supply the immutable
prediction facts at the front of `OfficialCandidateAssemblyRequest`. Its
adapter also injects existing calibration, model-health, risk, exposure, and
bankroll records through a read-only context port. This assembler remains the
only component that selects those records, verifies EV, reads publication
state, and creates the Quality Gate candidate. Registry candidate ID and
content fingerprint are included in normalized orchestration input for audit
linkage; they do not bypass or replace the assembled candidate fingerprint.
