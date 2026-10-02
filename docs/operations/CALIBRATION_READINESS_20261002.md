# PREMATCH calibration readiness — 2026-10-02

Status: READ-ONLY AUDIT COMPLETE; CALIBRATION_DATASET_NOT_READY.
Observed at 22:02:32 Europe/Riga using the installed de-vig release.

## Existing implementation

The installed research path already contains Platt and positive temperature
calibration, with isotonic eligible at 1,000 fitting observations. It separates
TRAIN, calibration fitting, later method evaluation and sealed holdout, groups
by fixture, and applies a 24-hour label-availability embargo. Required samples
are 300 calibration-fitting observations and 30 later evaluation observations.
The calibration implementation should not be rebuilt merely to add these methods.

## Current evidence

- 2,305 retained PREMATCH learning records: 175 SINGLE, 2,118 SHADOW and 12 legacy
  COMBO_LEG. The 12 legacy COMBO records remain excluded.
- 2,293 eligible resolved observations represent 773 fixtures over 14 days;
  multiple markets from the same fixture are correlated observations.
- Current partitions: TRAIN 896 observations / 294 fixtures; VALIDATION 0;
  SEALED_HOLDOUT 311 / 155; PURGED 1,086 / 324.
- All cross-partition fixture intersections are empty.
- Before purging, the validation allocation contained 531 observations from
  155 fixtures. Its first prediction is September 26 07:03:43 UTC and the
  holdout boundary is September 27 07:33:57 UTC. The embargo therefore requires
  validation labels before September 26 07:33:57 UTC. The earliest actual
  validation settlement is September 26 10:10:21 UTC: every validation fixture
  fails label availability; 134 also have predictions inside the embargo.
- Consequently calibration fitting and later evaluation have no input rows.
  This is a split/calendar-coverage bottleneck, not proof of a missing calibrator
  or evidence that the embargo should be weakened.
- Research also remains under the seven-day cooldown, ending October 5 at
  05:15:03 Europe/Riga. Its end does not establish dataset readiness.
- The PREMATCH champion remains generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a.
  There are zero holdout-result and challenger-shadow records. No fresh
  calibration performance claim or champion improvement is established.

## Next engineering work

Review and implement an isolated research dataset-window candidate using
predeclared chronological calendar windows and frozen boundaries, with explicit
TRAIN, calibration fitting, later evaluation, embargo gaps and sealed holdout.
Assess window feasibility from timestamps, availability and sample counts;
never choose boundaries by looking at holdout outcomes or model performance.
Preserve fixture grouping, label-availability protection, COMBO exclusion,
independent fixture counts and separate model/policy provenance.

Add regressions for clustered kickoff dates, late settlements, empty validation,
same-fixture leakage and unchanged sealed evidence. Compare readiness to the
current splitter on an offline snapshot; keep the production splitter and
scheduled cycles unchanged until a separately reviewed operator deployment.
If genuine time coverage remains insufficient, retain a blocked result and
collect natural future observations rather than reuse TRAIN/holdout rows.

Once independently ready, compare uncalibrated probabilities and fitted methods
on later evidence using Brier, log loss and reliability bins, then accumulate
future shadow evidence. De-vig probabilities are benchmark estimates, never
outcome labels or automatic calibration proof. Any eventual champion promotion
remains an explicit separate operator decision.

## Scope and evidence

This audit called only pure readiness/splitting functions on a query-only SQLite
snapshot and closed the connection before analysis. Network access was disabled
inside the audit subprocess. No research cycle, model fitting, holdout performance
evaluation, production write, provider call, test message, deployment or promotion
was invoked. Official, LIVE and ADMIN Codex settings were not changed. SINGLE
minimum 1.30, no COMBO floor, today-only and early COMBO settlement remain intact.

Evidence: docs/evidence/calibration_readiness_20261002/readiness.json, including
module hashes, independent counts, timestamps, blocked reasons and protected
state counts. This is a descriptive readiness audit, not a new test suite.
