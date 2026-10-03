# Dixon–Coles fit failure diagnosis — 2026-10-03

## Finding

Two recorded failures for fixture **1602097**, league **1141**, reproduce from
the exact cached result inputs available at their original 19:03:45 Riga capture.
The 1X2 and TOTAL_2_5 inputs have the same normalized training fingerprint:
`51b3660a83d0743c9dbc88eea6f4d58d54ebb5366d15e1db187ae881c75605a5`.

The existing optimizer reaches the frozen maximum goal-rate boundary of **8.0**.
Its line search then exhausts all 45 attempts at iterations **50 / 52**, before
the maximum **250** iterations. The maximum gradient remains about **0.006427**,
above the declared **0.000001** tolerance. The highest training goal rate is
8.0 to floating-point precision (remaining margin 1.8e-15 / 5.3e-15).
Low-cell factors stay positive (minimum about 0.417), away from their rejection
threshold. The replay takes roughly 0.12 seconds per family, at nice 10.

This identifies a boundary/line-search termination in the current implementation.
It is not evidence of a timer timeout or an exhausted iteration budget.
Raising only the iteration limit would not bypass this earlier line-search exit.
It does not establish that the stopped point is a constrained optimum.

## Input checks

43 eligible historical results, 11 teams; target teams have 12 and 4 observations.
These satisfy the declared count thresholds (40 league results / 3 per target team).
Source/candidate/capture fingerprints and original as-of references verify.
No normalized result exclusions were necessary. The largest observed individual
team score is 11; that is an observed data value, not proof of a provider error.

This is a narrow provenance/contract check, not a full independent audit of
football results. No odds history was acquired, no new forecasts were emitted
and no existing result or model was rewritten.

## Reproduction and safeguards

`diagnose_fit.py` reads the two exact diagnostic identities pinned by
`first_natural_cycle.json`, then their immutable capture/candidate/cache references.
It uses the unchanged `model.fit` and a read-only Python exception trace to inspect
optimizer locals. The script never changes POLICY or substitutes an optimizer.
SQLite connections are query-only; the output is a separate diagnostic JSON.
The process runs inside the existing offline test runner, with nice 10 and a
12 CPU-second limit. Both recorded failures reproduced successfully.

Run from the repository root:

```bash
nice -n 10 /home/arvis/GoalVisionAI/.venv/bin/python \
  docs/operations/offline_test_runner.py \
  /home/arvis/GoalVisionAI/.venv/bin/python \
  docs/evidence/dixon_coles_automation_20261003/diagnose_fit.py \
  --shadow /home/arvis/GoalVisionAI/var/lab_v2/shadow.db \
  --audit /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db \
  --research /var/lib/goalvision-dixon-coles/research.db \
  --output var/dc-fit-diagnostic-replay.json
```

Evidence:
- `fit_diagnostic_20261003.json`: exact replay diagnostics and policy.
- `fit_diagnostic_verification.json`: source/runtime/history checks.
- `second_natural_cycle.json`: independent evidence of continuing collection.

## Next development work

Normal priority: prepare an explicitly versioned research candidate with an
optimizer that handles the declared inequality constraints. Define acceptance
checks before comparing results: feasible goal rates and positive low cells,
appropriate constrained convergence, deterministic replay, bounded runtime,
interior-case consistency and explicit unavailable outcomes.

The current declared experiment remains unchanged. A candidate must get its
own prospective declaration and comparison cohort before any forward integration;
past failed captures must not be backfilled as successful forecasts. Increasing
the goal-rate ceiling or loosening convergence tolerance after this observation
would be a policy change and is not performed here. No automatic deployment,
champion promotion or change to SINGLE/COMBO selection.

## Collection continued naturally

The **19:40:30** timer completed successfully and stored one new forecast family:
fixture **1498855**, TOTAL_3_5, two paired markets. Its model converged in 77
iterations, gradient 6.40e-7. The original fixture **1641278** and all prior
research records remain intact.

Current prospective coverage: **2 unique pending fixtures, 5 families, 11 paired
market comparisons**; both fixtures start at **21:00 Riga**. No resolved games
are available yet. The 19:10 failure does not mean the collection pipeline has
stopped; it remains an explicit coverage limitation for that specific fit.
