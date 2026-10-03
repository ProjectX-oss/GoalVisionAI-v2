# Constrained Dixon–Coles development candidate — 2026-10-03

The separate research candidate resolves the recorded numerical failure while
retaining the original likelihood and rate/low-cell bounds. It is development-only.
No installed application, current research cohort, publication or champion changed.

## Declaration and method

Protocol declared in commit **bf7c107** before candidate implementation/evaluation:
`2beb92ca977016a49edf9d4d67afb199cea3102794313808fc7dd1d57ddba7ce`.
The existing calendar and Dixon–Coles plan retain their exact bytes and hashes.

The candidate uses identifiable mean-zero team strengths, analytic first/second
derivatives, a decreasing log barrier and damped Newton steps. Success requires
strict primal feasibility, positive multiplier estimates, stationarity <=1e-6
and per-constraint complementarity <=1e-6. All constraints are retained:
training goal rates stay between exp(-12) and 8, and each low-cell factor exceeds
1e-10. No fitted or predicted rate is clipped.

The same decay, regularization and training-count/holdout rules apply.
The new protocol governs solver stages/limits; it does not replace V1's policy.
The local approximate KKT certificate is independently recomputed on artifact
verification. Neither convexity nor a global optimum is claimed. In particular,
the summed complementarity value is not a nonconvex objective-error bound.

## Evidence

| Check | Result |
|---|---|
| Offline regression matrix | 135 passed, including 31 candidate tests |
| Analytic derivatives | Central-difference checks, including near low-cell boundary |
| Known constrained solutions | Interior and both boundary optima verified |
| Negative curvature | Damped Hessian reaches expected local solution |
| Budget exhaustion | Explicit unavailable errors; no uncertified artifact |
| Fixture 1602097, two failed families | Both now satisfy local KKT at rate <8 |
| Maximum rate in recovered case | 7.99995165 |
| Recovered-case stationarity | About 4.42e-7 |
| Two genuine interior cases | Largest absolute probability change 4.05e-6 |
| Controlled synthetic replay | 30 fixtures / 90 market rows / 3 kickoff dates |
| Maximum-size synthetic fit | 500 matches / 64 teams, converged in about 1.52 CPU seconds |
| Reverse-order inputs | Exactly identical sealed artifact |
| V1/candidate isolation | Incompatible artifact versions; no current-store writes |

The two failed families concern one fixture, so they do not constitute two
independent games. The genuine cases were already known development inputs.
No past prediction was backfilled, no result was used to select hyperparameters,
and the synthetic metrics do not establish real forecast quality.
Measured runtimes describe these cases, not every possible workload.

## Files and reproduction

Implementation: `app/dixon_coles_constrained/`.
Tests: `tests/test_dixon_coles_constrained.py`.
Evidence: `docs/evidence/dixon_coles_constrained_20261003/`.

```bash
nice -n 10 /home/arvis/GoalVisionAI/.venv/bin/python \
  docs/operations/offline_test_runner.py \
  /home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q \
  tests/test_dixon_coles_constrained.py \
  tests/test_dixon_coles_research.py tests/test_dixon_coles_sources.py \
  tests/test_dixon_coles_automation.py
```

The evidence runner reads existing SQLite sources in query-only mode, accepts
`--shadow`, `--audit`, `--research` and `--output`, and writes only its separate
development JSON. Run it through the same offline test runner at nice 10.
It replays the two pinned failure records, checks the two previously successful
fixtures, runs controlled synthetic evaluation and the maximum-size fit.
The 20 CPU-second per-fit and deterministic iteration/evaluation limits remain
explicit; an enclosing integration would also need a whole-cycle wall budget.

## Next gate

Prepare a new prospectively declared paired-comparison cohort for this candidate.
It must preserve the installed V1 first-forecast store, exclude backfilled
development predictions and obey the existing worker resource/schedule guards.
No operator package or timer integration is included in this change.
No automatic deployment or champion promotion.

SINGLE >=1.50, COMBO legs >=1.30, separate bots/statistics, Reply settlement,
Riga today-only and early COMBO loss remain installed. Official is unchanged;
LIVE and ADMIN Codex remain disabled.

Method reference and applicability caveat are documented in the package README:
https://web.stanford.edu/class/ee364a/lectures/barrier.pdf
