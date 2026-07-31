# Recently calibrated live-78 champion foundation

## Scope and safety

This workflow is restricted to disposable Lab/staging databases. It does not
authorize production activation, runtime production wiring, automatic model
promotion, scheduling, fixture discovery, publication, bankroll mutation, or
Telegram delivery. Controlled synthetic performance is rehearsal evidence only
and is not evidence of real predictive quality.

## Exact freshness semantics

The Real Match Lab runtime loads the immutable historical calibration artifact
set and reads `artifact_set.command.calibration_timestamp`. It propagates that
same value to the calibrated assembly's `calibration_effective_timestamp`.
Market value assessment calculates:

`calibrated_age_seconds = assessment_timestamp - calibration_effective_timestamp`

Policy v1 classifies calibration as `FRESH` through 1,800 seconds, `AGING`
through 7,200 seconds, and `STALE` afterward. Stale data is non-actionable. The
runtime does not use source retrieval time, activation time, champion generation
time, database insertion time, or the newest validation kickoff as a substitute.
Negative age also fails closed in the champion freshness report.

The timestamp represents the explicit time at which the real calibration
service completed a fit from immutable VALIDATION predictions. A new recent
artifact must therefore be produced by that service. Existing calibration rows
and timestamps are append-only and must never be rewritten, copied under a new
identity, or edited in SQLite.

## Controlled recent data chronology

`CONTROLLED_SYNTHETIC_STAGING_SOURCE` is the existing supported synthetic source
boundary. The recent rehearsal profile contains 1,200 completed fixtures at a
daily cadence ending before the controlled clock. This preserves the previously
reviewed deterministic data characteristics and provides a 300-day TEST/shadow
window.
All fixture kickoffs precede import, and import, projection, split, training,
calibration, TEST backtesting, comparison, and evidence cutoff are explicit UTC
times. After the 12-row historical warm-up exclusion, the challenger split is
688 TRAIN, 200 VALIDATION, and 300 TEST rows.
Preprocessing fits on TRAIN only. Calibration reads VALIDATION only. Backtesting
reads TEST only. Equal-kickoff, target-match, future-source, immutable-odds, and
schema checks continue to be enforced by the existing domain services.

The canonical authority is `LIVE_MODEL_INPUT_CONTRACT`: schema identifier and
version, exactly 78 ordered features, required baselines, missingness rules, and
schema fingerprint must all match. Legacy 145-feature artifacts, reordered
vectors, wrong fingerprints, and missing required baselines remain rejected.

## Reviewed lifecycle

The controlled workflow builds candidates through the real training and
calibration services, runs TEST-only backtests, executes compatible comparison
and promotion gates without forcing their outcome, settles identical-input
shadow evidence, and runs the independent read-only activation audit. Only an
`AUDIT_PASSED` chain can enter the manual two-stage staging activation rehearsal.
Activation and rollback require their existing exact confirmation phrases,
append new generations, revalidate evidence, reject stale plans and conflicts,
and preserve atomic recovery and replay behavior.

After activation, the read-only freshness report resolves the active generation
and verifies model and calibration fingerprints, live-78 ordering and schema,
calibration age, and independent audit status. Missing or inconsistent values
fail closed.

## Real Match Lab implication

A controlled future fixture with an injected clock and fresh immutable odds can
then traverse the same snapshot, Feature Store, model-input, champion resolver,
inference, calibration, and market-value boundaries used by a manual operator
analysis. All 11 supported single markets are recorded. No correct score or
combo is produced. A fresh champion removes stale calibration as a universal
rejection reason; it does not guarantee positive expected value or a selection.

No send command is part of this rehearsal. A preview fingerprint is not a send
claim. Delivery records, Official publications, Official bankroll/statistics,
and production activation must remain unchanged.

## Preparing the next genuine match

In a separately reviewed operational task, collect one still-upcoming real
fixture and bookmaker snapshot with truthful source identities and timestamps.
Validate all required baselines and odds freshness, run `validate` and then
`analyze` without the send confirmation, inspect all market reasons and the
champion freshness report, and retain the JSON evidence. Do not reuse the
controlled fixture or describe synthetic metrics as real-world performance.

## Repository recovery

The expected commit `27fb6a2966a817dff5a3671e4b92bf87c79f05d4` existed as
an unreferenced continuation while the working tree was attached to `clean` at
`5387bd6`. It was preserved and attached to
`goalvision/live-78-fresh-calibration` without resetting, stashing, cleaning, or
altering the pre-existing untracked `data/` and `var/` artifacts.
