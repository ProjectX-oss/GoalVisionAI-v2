# Probability Calibration Boundary

Probability calibration remains downstream of raw model inference and upstream
of future market prediction assembly. `app.prediction_inference` produces and
persists immutable raw probabilities; its `to_calibration_input(...)` mapper can
select one typed target while preserving inference and model provenance. It does
not execute this package automatically.

Calibration never changes the stored raw inference. A future reviewed caller may
calibrate each target using historical calibration data, then pass calibrated
values to market prediction assembly. Calibration must not register candidates,
run the Quality Gate, alter bankroll or risk state, or publish messages.
