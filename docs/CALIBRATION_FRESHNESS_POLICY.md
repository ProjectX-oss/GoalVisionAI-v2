# Calibration freshness policy review

## Finding

The former 7,200-second actionability limit was introduced in commit
`67260ba5140f65ee683b8970f1d5109674f2b633` as a market-value engine default.
No product rule, engineering guide, roadmap item, or earlier policy rationale
defines a two-hour lifetime for a fitted calibration model. Runtime then reused
the fit command's `calibration_timestamp` as
`calibration_effective_timestamp`, conflating operational artifact creation
with the age of labelled validation evidence. The same market-value policy held
both this limit and the intentionally short bookmaker-odds limits.

This was an implementation assumption, not an evidenced business requirement.
Changing the number on the same field would preserve the domain error, so the
Lab path now derives calibration evidence time independently.

## Domain semantics

- Artifact integrity verifies immutable model/calibration linkage, fingerprints,
  schema, target contract, persisted VALIDATION row count, unique example links,
  and example fingerprints.
- Evidence time is the maximum immutable kickoff among the exact labelled
  VALIDATION examples fitted by the calibration run. Fit, copy, activation, and
  review times cannot alter it.
- Artifact creation time remains the persisted calibration command timestamp.
  It is operational provenance and is not a live-data clock.
- Review time is an injected independent-audit time. Lab review is valid for 24
  hours. Missing, future, or expired review time fails closed.
- Odds retain the existing 300-second fresh, 900-second aging, and 1,800-second
  stale boundaries. Stale odds remain non-actionable.
- Real Match Lab feature snapshots are limited to 900 seconds. Supplied
  lineup-sensitive timestamps are limited to 3,600 seconds. Missing lineup data
  remains explicit and is not silently represented as fresh.

Typed failures include `CALIBRATION_EVIDENCE_STALE`,
`CALIBRATION_REVIEW_EXPIRED`, `CALIBRATION_PROVENANCE_INVALID`,
`FEATURE_SNAPSHOT_STALE`, and `LINEUP_DATA_STALE`. Existing market-value rows
retain their outer compatibility statuses.

## Policy values and scope

`calibration-freshness-policy-v2` permits a maximum evidence age of 366 days
only in Lab and staging. This is a conservative one-season review horizon that
matches the project's season-scale historical source cadence and safely covers
leap-year boundaries; it is not a claim that model quality remains stable for a
year. Drift, schema, audit, and review checks remain separate gates.

No supported Official calibration-evidence lifetime can be established from
the repository's controlled synthetic data. Official therefore remains
fail-closed with `OFFICIAL_CALIBRATION_POLICY_UNSET`. Controlled synthetic
evidence can exercise architecture in Lab/staging only and cannot establish
real predictive quality or authorize production.

## Compatibility and persistence

No migration is required. Existing calibration artifacts remain readable and
unchanged. Evidence metadata is derived read-only through their immutable
calibration-prediction-to-training-example foreign-key chain. A legacy or
inconsistent record without a complete chain remains inspectable but is
non-actionable; timestamps are never fabricated or backfilled. Existing
append-only triggers continue to block updates and deletes.

Activation never changes evidence time. Re-fitting or copying calibration
parameters over unchanged validation examples also preserves the same evidence
time, so neither operation can fake freshness.
