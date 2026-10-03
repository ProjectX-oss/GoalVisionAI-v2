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
