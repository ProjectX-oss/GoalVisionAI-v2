# Lab prediction reasoning operations

Reasoning is manual and offline. It performs no provider request, inference,
Telegram call, delivery creation, Official mutation, bankroll/statistics update,
scheduler change or production activation.

Operator sequence:

1. Complete and persist a live-78 Lab analysis and, when used, its forward-test
   observation.
2. Create reasoning from the console Reasoning page or run
   `python -m app.prediction_explainability explain-observation --database DB --id OBSERVATION_ID --output json`.
3. Inspect the positive/negative evidence, all market rejections, missing data,
   calibration/shift disclosures, counterfactuals and audit.
4. Recompute estimator contributions with `reproduce-reasoning`, or inspect
   `feature-contributions`, `explain-market` and `reasoning-diagnostics`.
5. Create a new publication review. A pre-reasoning review cannot pass. Only a
   passed audit can be bound to the exact reasoned message fingerprint.

For a safe fictional exercise, run `controlled-rehearsal` against an isolated
database. The rehearsal uses a deterministic fictional 78-feature input and
three multinomial estimators, creates all eleven market explanations, and
reports explicit zero-activity counters. Never run it against production data.
