# Calibration request readiness — 2026-10-07

Status: BLOCKED_NEEDS_MORE_EVIDENCE. User asked to calibrate after reviewing
the previous day's private SINGLE candidates. The previously approved rule
forbids fitting or creating a calibration artifact below 300 independent
CALIBRATION_FIT examples. No threshold or time window has been changed.

## Current evidence

Read-only audit as of 2026-10-07 08:33:24 Europe/Riga, using the installed release
/opt/goalvision-prematch-combo-double-170-6489f92-20261006.
Audited source commit: 796ac0f893e04c75e487511440f6dfd34af0c7cc.

| Frozen partition | Observations | Independent fixtures |
|---|---:|---:|
| TRAIN | 1804 | 560 |
| CALIBRATION_FIT | 222 | 222 |
| VALIDATION_EVALUATION | 0 | 0 |
| SEALED_HOLDOUT | 0 | 0 |
| PURGED | 760 | 298 |
| EXCLUDED | 22 | 20 |

CALIBRATION_FIT is short by 78 independent examples. Its declared window closes
2026-10-10 03:00 Riga. Validation begins 2026-10-11 03:00 Riga and sealed holdout
begins 2026-10-19 03:00 Riga. Those dates and embargo gaps remain frozen.
All cross-partition fixture intersections are zero.

Retained observations: 2808. Independent-source observations: 2796; this count
is observations, not independent fixtures and includes a non-binary outcome.
Latest natural observer reported 2795 resolved eligible observations and
CHALLENGER_RESEARCH at 08:08 Riga.

Champion remains generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a,
family EXISTING_PREMATCH_BASELINE_V1, reason BOOTSTRAP.
PREMATCH validation results, holdout results, shadow runs and promotion gates
are zero. Promotion status is NOT_ELIGIBLE. Existing training/artifact records
were only counted; none were created in this task.

The CLI also returns a legacy rolling projection. It is descriptive and must not
replace the declared calendar allocation or supply rows to meet the minimum.

## Work performed and next action

- Re-read applicable repository rules and the existing calibration/calendar code.
- Execute a fresh bounded query-only readiness audit from the immutable installed
  application; deny outbound sockets and verify installed/source equality.
- Verify champion pointer and governance counts unchanged before/after.
- Run the three focused calendar readiness suites: 54 passed in 10.54 seconds,
  with outbound network denied. No application implementation change was needed.
- Preserve complete readiness and verification evidence in
  docs/evidence/calibration_readiness_20261007/.

Continue the existing natural collection. At >=300 eligible independent examples,
reassess the declared calendar/class-support rules and prepare the isolated
identity, Platt and temperature comparison. Isotonic retains its existing 1000
minimum. Calibration fitting uses CALIBRATION_FIT only; later validation evaluates
quality, and sealed holdout is not consumed prematurely. Reaching 300 alone does
not authorize activation or bypass remaining evaluation gates.

No new calibrator, model, calibration metrics or claim of quality improvement was
produced. No new timer or future task was scheduled. Deployment and activation
remain separate operator decisions.

Agent activity: zero provider/Telegram calls or sends, manual service cycles,
production database writes, deployments, promotions and rollbacks. Publication
thresholds and current champion are unchanged. Official is untouched and LIVE
remains disabled. Original dirty main checkout was not edited.
