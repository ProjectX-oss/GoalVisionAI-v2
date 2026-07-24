# Controlled Model Activation and Rollback

`app.model_activation` is the manual boundary between Lab evidence and any
future production runtime integration. Promotion recommendations and Shadow
Evaluation never activate models. Preparing a plan never changes the champion.
Only `execute_activation(...)` or `execute_rollback(...)` appends a new current
champion generation.

Activation requires the exact final `PROMOTE_CHALLENGER` recommendation, all
mandatory comparison gates, verified model/preprocessing/calibration artifacts,
feature and target schemas, the canonical probability contract, runtime
compatibility, and sufficient settled shadow evidence for the exact current
champion/challenger pair. Conservative policy defaults require 30 settled
observations across 14 days, evidence completeness, agreement and critical
disagreement limits, and bounded predictive, calibration, betting, and
drawdown degradation.

The champion registry is an append-only generation ledger. The highest valid
generation number is the only current champion for a scope. Activation and
rollback append a generation and registry event atomically; prior generations
are never updated, retired destructively, or deleted. A one-time explicit
`bootstrap_champion(...)` is required before planning the first switch.

Rollback is also two-stage and manual. It targets a compatible prior generation
and requires a reason plus incident reference. Execution revalidates the
current champion and target, then activates the target artifact as a new
generation in the same transaction. A champion is never merely deactivated,
and failure cannot leave the scope without its previous champion.

Migration v31 adds ten append-only tables for activation requests/plans/
validations, champion generations/events, activation executions, rollback
requests/plans/executions, and exact shadow evidence links. Request and
execution replay is idempotent; changed content conflicts. All history tables
reject updates and deletes.

The read-only runtime resolver returns exact model, preprocessing, calibration,
schema, target, probability-contract, and runtime references. It fails closed
on missing or corrupted state and never infers, publishes, activates, falls
back, or calls external services. It is deliberately not wired into startup or
the existing production inference path.

Automatic promotion, scheduled activation, background workers, automatic
rollback, metric-triggered switching, Telegram changes, betting, bankroll
changes, and mutation of upstream evidence remain explicitly deferred.

`app.model_operations` now exposes this domain through an explicit manual CLI
and read-only audit/diagnostic views. It does not weaken any domain validation:
bootstrap, preparation, execution, stale-state rejection, idempotency, and
atomic generation appends remain owned here. Only exact confirmed execution
changes the registry; preparation remains non-activating, rollback creates a
new generation, and runtime inference remains disconnected from the resolver.
