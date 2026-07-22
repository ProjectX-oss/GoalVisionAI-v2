# Official Candidate Preparation

This package is the deterministic integration boundary between one immutable
successful Official selection and the existing Candidate Registry. It verifies
the persisted selection and value-assessment chain, consumes explicitly
supplied Official EUR bankroll and exposure snapshots, calls the existing risk
service exactly once, validates its typed result, and conditionally calls the
existing registry exactly once.

The package does not fetch data, recalculate probability/odds/EV/ranking,
duplicate stake or exposure policy, mutate bankroll or exposure, run the
Quality Gate, publish, schedule, or support live, combo, High Risk, Lab, or
AutoTrader workflows. All timestamps are caller supplied; there is no clock,
network, or random source.

## Decision flow

`ELIGIBLE` and `REDUCED_STAKE` risk results map to one complete registry
command. The exact risk-returned stake amount, internal percentage, band,
policy, bankroll/exposure identities, and full selection/model/calibration
fingerprints are retained as structured immutable provenance. The registry
remains authoritative for candidate identity, versioning, READY/supersession
lifecycle, publication protection, and registration status.

`REVIEW_REQUIRED` and `INELIGIBLE` are valid terminal no-registration
decisions. They and their exact risk reasons are persisted, and the registry is
not called. Risk execution failures and malformed risk responses also fail
closed without registration. Candidate preparation never claims that the
Quality Gate has approved a candidate: it uses the explicit
`PRE_PUBLICATION_GATE` risk phase with no gate status.

`quality_gate_handoff(...)` is a read-only typed mapping available only for a
persisted successful execution whose registered candidate is still `READY`.
It returns the candidate, risk, exposure, and bankroll records needed by the
existing downstream assembler. It does not execute or persist a gate decision.

## Persistence and recovery

Migration v21 adds `official_candidate_preparation_executions` and
`official_candidate_preparation_risk_snapshots`, plus the append-only structured
candidate `provenance_snapshot`. Executions and validated risk results are
written in one SQLite transaction and protected by update/delete rejection
triggers. Request, handoff, risk, mapping, and final integration SHA-256
fingerprints exclude execution time.

An exact terminal request replay returns `IDEMPOTENT_EXISTING` before another
risk or registry call. Reusing a request identity for different content returns
`CONFLICT`. Candidate registration occurs through the registry before the
integration audit append because the registry owns its transaction. If the
subsequent audit append fails, a retry safely repeats risk and receives the
registry's existing candidate; it never creates a duplicate candidate version.

Use `build_official_candidate_preparation_service(...)` and call
`prepare_official_candidate(...)` with one immutable command. Construction
requires explicit repositories, policy, risk service, Candidate Registry, and
lifecycle reader; it performs no preparation or startup work.
