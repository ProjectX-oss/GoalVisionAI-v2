# Official Prediction Publication

This package is the deterministic public-message and delivery boundary for an
already approved Official prediction. It does not generate predictions, choose
markets, calculate probability, decide risk, reserve bankroll, settle bets, or
schedule publication.

## Public message contract

`OfficialPredictionMessageBuilder` accepts the immutable approved
orchestration result plus supplied public fixture, stake, and reasoning facts.
It emits Telegram HTML containing only the competition, teams, kickoff,
supported market and selection, approved odds, calibrated model probability,
public confidence, public stake stars, approved public reasoning, optional data
note, branding, and the responsible-betting notice.

The builder rejects non-Official scope, mismatched approval identities,
unapproved or dry-run inputs, odds below the Official minimum, unsupported or
inconsistent markets, exact-score content, missing reasoning, promotional or
guaranteed language, invalid stake recommendations, and oversized messages.
All supplied public text is HTML-escaped. Raw probability, expected value,
internal stake percentage, exposure details, calibration metrics, audit IDs,
and internal explanations are never rendered.

Public stake ratings are derived from the immutable risk recommendation:

- 1%: `★☆☆`
- 2%: `★★☆`
- 3%: `★★★`

Reduced recommendations use the completed lower band and never round upward.
Zero or ineligible recommendations fail closed.

## Message fingerprint v1

The immutable payload contains a SHA-256 fingerprint over the prediction,
match, orchestration, gate-evaluation, candidate, model, and policy identities;
the exact rendered message; parse mode; Official destination scope; approved
odds; calibrated probability; confidence; stake rating; and caller-supplied
creation timestamp. Destination credentials and channel identifiers are not
fingerprinted or persisted.

## Atomic delivery sequence

`OfficialPredictionPublisherAdapter` implements the orchestration publisher
port with this sequence:

1. Revalidate the approved gate, identities, candidate fingerprint, Official
   scope, publication state, and canonical public payload.
2. Append a `CLAIMED` event under an immediate SQLite write lock.
3. Send exactly the claimed immutable message through the injected Telegram
   sender.
4. Store the existing settlement-facing published-prediction reference.
5. Append the terminal `PUBLISHED` event.

A confirmed no-delivery response appends `FAILED` and permits a new numbered
attempt. An unknown send outcome or any post-send persistence failure appends
`INDETERMINATE` when possible and is never automatically resent. Existing
claims, published messages, and indeterminate attempts block duplicates. No
database transaction remains open during the Telegram operation.

Migration v12 creates `official_prediction_publication_events`, an append-only
event stream with database-enforced update and delete rejection, unique
attempt sequences, linkage to the persisted Quality Gate evaluation, and no
bankroll, exposure, risk, settlement, or result-publication mutation.

## Runtime construction

`build_official_prediction_publisher_adapter` composes the SQLite claim repository,
existing published-prediction writer, message builder, facts provider, Telegram
sender, Official destination, and injected clock. The orchestration factory can
build this adapter when those dependencies are supplied. Construction performs
additive migration only; startup and scheduling do not publish anything.

The manual batch coordinator does not send through this adapter directly. It
calls the single-prediction orchestration boundary, which remains the only
owner allowed to invoke this adapter after a persisted Quality Gate approval.
Batch idempotency supplements but never replaces prediction-level atomic
claims, confirmed-failure retries, or indeterminate resend blocking.

The Registered Candidate pipeline reuses this message builder for dry-run
previews and this complete atomic adapter for manual publication. It never
sends before a claim and treats post-send finalization uncertainty as
non-resendable.

`app/official_prediction_operations` adds outer environment/destination
verification and exact confirmation controls. Fixture dry-runs use a transport
sentinel that must never be invoked and require no credentials. Staging and
production transports remain injected by application/deployment composition;
the operations package does not load or log tokens. Explicit retry accepts only
confirmed pre-send or confirmed Telegram no-delivery failures and reuses
persisted gate evidence. Active claims and indeterminate post-send events remain
zero-send.
