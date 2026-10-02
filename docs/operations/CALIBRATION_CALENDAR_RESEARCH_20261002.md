# PREMATCH fixed-calendar calibration research — 2026-10-02

Engineering and offline audit: PASS. Production wiring/deployment: NOT PERFORMED.
Real calibration readiness: BLOCKED pending prospective fitting/evaluation/holdout
windows and sufficient independent fixtures. No real calibration improvement is claimed.

## Why this candidate exists

The current fixture-quantile splitter can allocate a roughly one-day validation
interval when observations cluster on busy match dates. Its necessary 24-hour
label-availability embargo then removes that entire interval. Merely increasing
total observation count does not repair that geometry.

The new candidate uses one prespecified calendar schedule, not a search over
cutoffs or outcome performance. Four windows are separated by full 24-hour gaps:
14 days TRAIN, 7 days CALIBRATION_FIT, 7 days VALIDATION_EVALUATION, 7 days
SEALED_HOLDOUT. Their UTC boundaries are immutable in a fingerprinted JSON plan.
The start is supplied explicitly; no density or outcome optimizer chooses it.
These durations are an experimental design, not an empirically optimal claim.

## Implementation

- `app/adaptive_lab/calendar_research.py`: pure plan serialization, whole-fixture
  allocation, explicit exclusion reasons, readiness and existing-calibrator adapter.
- `app/adaptive_lab/calendar_audit.py`: explicit query-only SQLite snapshot and
  readiness comparison CLI. It never calls AutoLearner, fitting or governance.
- Existing datasets.py, calibration_research.py, AutoLearner, timers and prediction
  paths are unchanged. Nothing imports the candidate from production runtime.

The plan pins model generation, model artifact, competition policy and classifier
version. Missing or mixed provenance excludes the entire affected independent
fixture group. COMBO/legacy COMBO_LEG, LIVE and unknown source products are excluded.
All source observation fingerprints are checked; duplicate IDs or inconsistent
outcomes fail closed. Output is detached from caller-owned dictionaries.

A fixture spanning windows is purged as a whole. Each earlier partition requires
all labels strictly before the next partition starts minus 24 hours. Labels
exactly on the cutoff fail. VOID, pending/future labels and future predictions do
not become training observations. Consumed holdout fixtures cannot enter any
partition; a pinned prior holdout reservation cannot become TRAIN, fitting or
method-evaluation evidence. Every row remains accounted for, including exclusions.

Readiness reports both market observations and unique fixtures. This research
candidate conservatively requires the existing numeric sample minima also as
independent-fixture minima: 300 fitting, 30 later evaluation and 100 holdout.
At least ten different fitting fixtures per outcome class are required, and TRAIN
must contain both classes. The production LearningPolicy is not modified.
All windows must close; a plan declared at/after calibration starts remains an
explicitly blocked retrospective audit. Insufficient data never shifts a boundary,
borrows TRAIN/holdout rows, drops the embargo or manufactures fitting evidence.
`CALENDAR_READY_FOR_OFFLINE_REVIEW` is not permission to train or promote in production.

## Frozen prospective research plan

`docs/evidence/calibration_calendar_20261002/plan.json` was declared at
2026-10-02 22:15:05 Europe/Riga, before its calibration window. Its historical
TRAIN anchor is September 18, the first complete UTC collection day after retained
observations begin on September 17 at 20:15 UTC. The partial initial day is outside
this schedule; future calibration, evaluation and holdout windows were not chosen
using their results.

| Partition | Start UTC, inclusive | End UTC, exclusive |
|---|---|---|
| TRAIN | 2026-09-18 00:00 | 2026-10-02 00:00 |
| CALIBRATION_FIT | 2026-10-03 00:00 | 2026-10-10 00:00 |
| VALIDATION_EVALUATION | 2026-10-11 00:00 | 2026-10-18 00:00 |
| SEALED_HOLDOUT | 2026-10-19 00:00 | 2026-10-26 00:00 |

Do not regenerate/rebase this plan as new results arrive. Keep using its exact
fingerprint. Existing evidence capture continues naturally; the plan creates no
scheduler, provider request or message. Closing dates are not promises that the
sample, diversity, quality or subsequent shadow requirements will pass. If this
experiment stays underpowered, retain the blocked result; any new experiment
needs a separately predeclared plan and preserved holdout protection.

## Real read-only comparison

Snapshot at 22:15:05 Riga: 2,309 retained records, of which 2,297 are independent
SINGLE/SHADOW-source observations. No scoring, fitting or holdout performance
inspection was done. The current quantile projection is compared only by allocation.

| Partition | Existing projection: observations / fixtures | Calendar candidate: observations / fixtures |
|---|---:|---:|
| TRAIN | 896 / 294 | 1,804 / 560 |
| VALIDATION, before calibration split | 0 / 0 | Separate future windows below |
| CALIBRATION_FIT | unavailable | 0 / 0 |
| VALIDATION_EVALUATION | unavailable | 0 / 0 |
| SEALED_HOLDOUT | 303 / 156 | 0 / 0, future window |
| PURGED | 1,098 / 326 | 483 / 206 |
| EXCLUDED | 12 legacy COMBO records before splitting | 22 / 20 |

The new plan reserves all 156 fixtures in the current old holdout projection.
It does not relabel those 303 existing holdout observations as fitting data.
Candidate purge reasons: 265 reserved-holdout observations, 180 late labels and
38 outside-window/embargo observations. Exclusions: 12 legacy COMBO rows and ten
rows lacking matching generation provenance. Fixture counts in rejected categories
can overlap; they are not additive independent sample sizes.

The greater TRAIN allocation is an allocation result, not evidence of better
prediction accuracy. All later candidate windows still have zero observations
and remain blocked. The sealed old outcomes were not used to tune this schedule.

## Verification

- 654 tests and 42 subtests PASS in 124.35 seconds; includes 35 new tests.
  The complete adaptive_lab suite and relevant existing calibration suites ran
  under kernel-level network denial inherited by subprocesses.
- Clustered kickoff dates reproduce zero legacy validation while the calendar
  candidate retains timestamp-eligible fitting observations and honestly blocks
  undersized later samples.
- Covered exact embargo cutoffs, cross-window/late-member fixture purges,
  preserved/consumed holdout, class and fixture independence, missing/mixed
  provenance, COMBO/LIVE exclusion, immature/retrospective plans, invalid/tampered
  input and plan documents, row conservation and stable future append behavior.
- A controlled synthetic overconfident model passes through the existing genuine
  calibration fitter using calendar partitions; artifacts reproduce exactly and
  no sealed holdout row enters fitting or method evaluation. This is a synthetic
  compatibility regression, not football performance evidence.
- SQLite/CLI tests prove query-only inspection leaves database bytes and plan
  bytes unchanged, creates no missing database and never trains or writes.
- Separate real-data assertions at 22:19:50 Riga reproduce the result with reversed
  input, verify every retained assignment against timestamps/cohort/embargo,
  conserve all 2,314 then-retained rows, preserve reservations and find zero
  cross-partition fixture overlaps. The later source fingerprint differs because
  natural settlement added records; the plan fingerprint stays unchanged.
- Protected state before/after: learning_cycles=3, training_runs=133,
  model_artifacts=59, holdout_results=0, shadow_runs=0, activation_events=1,
  champion_generations=1, live_publications=0. Champion unchanged.
- PREMATCH, weekly, monitor and worker configured routes unchanged; ADMIN worker
  inactive/PID 0 and timer disabled. No real research cycle, provider call, test
  send, deployment or promotion was invoked.

## Use and remaining work

From this isolated worktree, an explicit read-only inspection is:

```bash
PYTHONPATH=. /home/arvis/GoalVisionAI/.venv/bin/python \
  docs/operations/offline_test_runner.py \
  /home/arvis/GoalVisionAI/.venv/bin/python -m app.adaptive_lab.calendar_audit \
  --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db \
  --plan docs/evidence/calibration_calendar_20261002/plan.json \
  --as-of 2026-10-02T19:15:05.590944+00:00
```

For a fresh inspection supply its actual as-of timestamp and retain the same
plan. This reads the latest snapshot; exact source fingerprints/counts can differ
as immutable observations are appended. Do not interpret it as a production
research attempt. Output deliberately contains no raw outcomes or model metrics.

Next evidence is natural prospective collection for this plan. After readiness,
separate offline calibrated/raw probability comparison can use the existing
fitters, followed by sealed holdout and later shadow evaluation. Outcome quality,
calibration uncertainty and governance gates must pass before any deployment or
explicit champion decision. Integrating this candidate into scheduled research
is a separate reviewed change; no operator deployment package is included here.

Official unchanged; LIVE and ADMIN Codex stay disabled. PREMATCH SINGLE >=1.30,
COMBO without an odds floor, today-only and early COMBO settlement are preserved.

Evidence: `docs/evidence/calibration_calendar_20261002/` contains the immutable
plan, initial allocation report, independent verification and regression JUnit.
