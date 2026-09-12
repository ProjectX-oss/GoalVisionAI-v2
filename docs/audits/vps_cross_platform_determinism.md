# VPS activation rehearsal determinism correction

Date: 2026-09-12. Scope: offline model artifacts and disposable rehearsals.

## Root cause and exact fingerprint chain

Python 3.13.14 reproduced the reported Linux failure. Read-only comparison with
a preserved fictional rehearsal database containing the expected Windows plan
identified these differing inputs to the activation plan hash:

- `request_fingerprint`: Windows
  `088b1f4007e4fe7f2892f28c2205b2497a73776329b3630636de9944ae111c7e`,
  Linux `1f8f05151a50a8b82c84b9bfb5d692c00ff0813b593d0f0d2b2276ff8f4d847f`.
- `expected_registry_fingerprint`: Windows
  `71e13a42f2c88473193a24e560b263cd50ab8ffc5f2471bc00031e4cbcf9657f`,
  Linux `ada49a391223969f8b31e8eb639f81f107c8245abc8c6ac19f72be1656fa2f8f`.
- `evidence`: Windows
  `12b1cbef10e65ab5941d685fc405b3c47433ce48941a13d8b1f0ac2a253f2508`,
  Linux `ecbaf8a67fffe603f32fe13af3040e58743824a76b94e89c18b03b490a8fbbef`.

Generation number, validation fingerprints, policy snapshot and preparation
timestamp match. The request differences are model/calibration references,
comparison/recommendation references and the champion generation reference.
Rehashing each stored plan's exact core on Linux reproduces its respective
Windows or Linux ID, confirming that activation canonicalization itself is stable.

Tracing backward reaches `historical_model_training.estimators._softmax`:
training calls the host C library through `math.exp`. Windows and Linux can
produce different final binary64 bits. The persisted first match-result model
coefficient at feature index 1 is `0.15580020197851588` on Windows and
`0.15580020197851585` on Linux. The complete preprocessing fingerprint is identical
(`3f9d3b3542aed20b1a8f8b16b7a68b2d15cc4849800b16a6ca465cae7c6ff345`),
as are training request identity, compatibility and provenance snapshots.

The lossless `.17g` serializer correctly distinguishes these different numbers.
Estimator differences propagate through training metrics, model artifacts,
calibration, comparison, shadow evidence, champion registration and activation.
Canonical JSON ordering, Decimal/text serialization, datetime normalization,
SQLite persistence, filesystem spelling, line endings and platform metadata are
not the source of this plan mismatch. Matching Python versions do not pin libm.

## Correction

The affected training/inference exponential, preprocessing square root, and
training/calibration metric logarithms now use exact `Decimal.from_float` input,
a fresh 80-digit, half-even context, and conversion back to binary64. Float
squares use multiplication rather than libm-backed exponentiation. Model settings,
feature ordering, thresholds, probability contracts and public interfaces stay
unchanged. Fingerprint serialization remains lossless and adjacent floats remain
distinct; no tolerance or rounding is added to an integrity check.

Both legacy fixture hashes describe platform-dependent numerical output:

- Windows: `activation-plan-52de46d3503b82ba317fd1aebf3b4d63439561b66f94336510f7f6f7131dfcac`
- Linux: `activation-plan-9c0726d30455f6ed8f3c6bda3f8f384f33a17d94a260db7aacaf3a118379a5cb`

The regenerated expectation after the numerical correction is
`activation-plan-5732a3dbc4f000a5abc6c6f71ab99bf71ded1a1642746ea20a52162bfed230cf`.
Its request fingerprint is
`179e0ed33c5eab5f3e2f06461a33b4b7d704bed1a4325f06c8dc84c8e4d95e36`.
This is a newly computed fixture identity, not adoption of the failing Linux hash.

Existing stored artifacts, fingerprints, plans and historical evidence are never
rewritten. Exact replay/conflict and append-only verification remain enforced.
Both retained Windows model artifacts still pass artifact and estimator
fingerprint verification under the corrected code through a read-only connection.
Fresh computations can differ in their last bits from legacy platform-dependent
computations; old artifacts must not be relabeled with the new identities or
silently treated as bit-identical reproductions. This correction does not claim
cross-platform determinism for unrelated algorithms such as the Platt fitter.

The focused rehearsal also exposed an existing report-redaction omission:
foundation command database paths were retained. Captured `--database` values
are now redacted regardless of path syntax. The old Windows assertion could
miss this because JSON escapes backslashes; an explicit two-path-style test
now exercises the redaction itself.

## Verification

Regression coverage fixes exact numerical outputs, rejects host exp/log/sqrt/pow
use during fictional fixture generation, varies ambient Decimal precision and
rounding, preserves distinctions between adjacent floats, and verifies the full
fixture manifest hash across LF/CRLF JSON and dictionary insertion order.
Existing audit/rehearsal tests exercise the regenerated plan through actual CLI
subprocesses, SQLite round trips, replay, conflicts, rollback and immutable guards.
Windows was not executed in this session; the backend-independence regressions
are the automated cross-platform evidence available on this VPS.

Focused verification: **150 passed, 28 subtests passed in 394.34 seconds** on
Python 3.13.14. This includes `test_model_activation_audit.py` (all 18 tests),
the new determinism regressions, model activation/operations tests, both Lab
rehearsal suites, the staging rehearsal, and historical training, calibration
and backtesting suites.

Full suite, run once after focused verification:
`python -m pytest tests -q --tb=short` — **1,516 passed, 563 subtests passed in
452.27 seconds**. No production deployment or activation was performed.

Comparison with the retained Windows fixture finds a maximum coefficient change
of `5.551115123125783e-17`. Validation aggregate Brier/log-loss metrics match;
TRAIN aggregate Brier differs only in its final represented digits. The retained
fixture backtest selections, settlements and bankroll ledger each contain eight
rows and match the corrected fixture in their compared business values. These
are fictional regression checks, not predictive-quality or profitability claims.

No production activation, Telegram delivery, Official publication, production
bankroll/statistics mutation, secrets access, scheduling or startup work is part
of this correction. Deployment still requires separately authorized readiness
checks and activation.
