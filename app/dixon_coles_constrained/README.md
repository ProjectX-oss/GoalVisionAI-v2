# Dixon–Coles constrained development candidate

Separate development-only solver, declared before implementation/evaluation.
The deployed research V1 and its frozen policy/plan remain unchanged.
The same likelihood, regularization, decay and feasible region are retained.
Log-barrier damped Newton uses analytic gradients/Hessians and a local approximate
KKT certificate. DC is not established convex: no global optimum/duality-gap
guarantee is claimed. The barrier complementarity sum is reported, not treated
as a nonconvex global objective error bound. No forward integration, timer,
operator package, selection, promotion, provider requests or Telegram transport.

Known failed and prior successful fixtures are development inputs only.
Prospective comparison requires a later separate declaration and cohort;
never backfill previous failures into the installed evidence.

Method source: https://web.stanford.edu/class/ee364a/lectures/barrier.pdf
(slides 11.5–11.10, 11.14). The barrier adds a logarithm penalty for strictly
feasible constraint slack; decreasing its weight approaches the boundary.
Its first-order equation yields positive multiplier estimates and an
approximate complementarity residual. Convex guarantees in the reference
are not transferred to this nonlinear football model. No external code copied.

## Implementation

- `geometry.py`: reduced mean-zero attack/defence coordinates, exact likelihood
  gradient/Hessian and barrier derivatives for all eight training-row constraints.
- `solver.py`: deterministic Cholesky-damped Newton, feasible Armijo steps,
  per-stage/evaluation/CPU budgets and local approximate KKT stopping.
- `model.py`: sealed development-only fit artifacts, certificate recomputation,
  original prediction-domain checks and incompatible versioning versus V1.

The baseline POLICY remains a reference to the original model/data contract.
The independent protocol specifies the candidate solver's stages, iteration
limits and stopping criteria; V1's iteration limit is not used by this solver.
A feasible initial point may use unit rates when the original weighted-mean
initialization violates constraints. Fitted and predicted rates are never clipped.

KKT stationarity uses the identifiable reduced coordinates. Primal slack is
strictly positive; multiplier estimates are barrier_weight/slack and positive.
Complementarity is checked per constraint (infinity norm). Its sum is separately
reported and is **not a global objective error bound** for this nonconvex model.
A certificate describes a local first-order condition, not proven global optimality.

`verify_artifact` rebuilds input normalization/team counts/parameters and the
certificate. `predict` checks the target, chronology and unseen-pair rate domain.
The output is always DEVELOPMENT_ONLY / forward_eligible=false. It has no
ResearchStore, timer, provider, Telegram, selection or champion write path.

## Validation

135 offline tests passed: 31 new candidate/math/contract checks plus 104 prior
research/automation regressions. Checks cover analytic gradient/Hessian against
central differences (including near a low-cell boundary), exact V1 likelihood,
known constrained optima, indefinite-Hessian damping, budget rejection,
artifact tampering, holdout/time boundaries, neutral-only data, rate-boundary
initialization and deterministic reverse-order replay.

Both previously failed fixture 1602097 families now meet local KKT criteria while
remaining strictly below rate 8.0; stationarity is about 4.42e-7.
These are two captures of one development fixture, not two independent games.

Two previously successful genuine cases remain within declared compatibility
tolerances; largest probability difference is about 4.05e-6 (absolute).
The controlled 30-fixture/90-market replay is synthetic and provides no real
predictive-quality evidence. A synthetic maximum-size 500-game/64-team fit
converged in about 1.52 CPU seconds in this environment. This is one measured
case, not a runtime guarantee for every possible input.

See `docs/evidence/dixon_coles_constrained_20261003/` for reproducible
`verify_offline.py`, development comparisons, test/runtime verification and
limitations. Run tests through the existing offline_test_runner at nice 10.

## Next gate

A later forward integration must declare a new comparison cohort before its
first eligible capture, preserve the V1 first-forecast store, fit within the
whole worker cycle budget and prove correct paired evaluation. Development
captures cannot be backfilled into that cohort. No operator package or deployment
is prepared in this change. Selection, odds floors, existing bots/statistics,
Reply settlement, today-only and early COMBO settlement remain unchanged.
