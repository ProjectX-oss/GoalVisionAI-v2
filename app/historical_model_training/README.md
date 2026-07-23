# Historical Model Training Foundation

This package consumes exactly one verified immutable split fold and fits only its
`TRAIN` assignments. Optional `VALIDATION` examples are evaluation-only. `TEST`
and every excluded partition are never loaded by the service.

The production baseline is `MULTI_TARGET_LOGISTIC_REGRESSION_V1`, implemented as
deterministic batch-gradient logistic models with explicit settings and seed.
Match result uses one coherent three-class softmax. Totals use one four-bucket
softmax, from which cumulative over probabilities are derived; this guarantees
`OVER_3_5 <= OVER_2_5 <= OVER_1_5`. BTTS uses one binary softmax. Under and
`BTTS_NO` outputs are exact complements. The canonical output is the existing
11-target Prediction Inference raw-probability contract and is explicitly
uncalibrated.

Preprocessing validates the exact 145-position
`historical_training_features_v1` order, preserves the supplied mask and
provenance, fits median imputation from TRAIN only, then fits population standard
scaling from TRAIN only. All-missing features reject by default; zero-variance
features use documented unit scale. Decimal inputs are converted through their
canonical finite numeric value. Optional mask indicators are versioned.

Artifacts are safe canonical JSON-compatible parameter bundles, never opaque
pickles. They contain compatibility metadata, imputation/scaling values, ordered
coefficients and intercepts, class order, convergence evidence, metrics, example
provenance, explicit execution metadata, and SHA-256 fingerprints. The read-only
adapter applies only persisted preprocessing and parameters to a compatible
vector and returns artifact provenance with raw probabilities.

Migration v26 adds six append-only tables for training runs, artifacts, canonical
targets, preprocessing features, example links, and metrics. Foreign keys,
uniqueness constraints, deterministic indexes, atomic writes, and update/delete
triggers protect immutable history. Identical requests return the existing run
without refitting; changed content under the same request ID conflicts.

Training is an explicit injected call. There is no import-time or startup
training, TEST access, calibration fitting, backtesting, comparison, promotion,
shadow execution, live inference wiring, provider access, scheduling, candidate
generation, Quality Gate, publication, credential access, or Telegram activity.

The reviewed ML flow is:

```text
historical import -> historical training dataset -> historical dataset split
  -> historical model training -> historical probability calibration fitting
  -> historical backtesting
  -> model comparison and promotion -> shadow evaluation
```

`app.historical_probability_calibration` implements that next boundary. It
reproduces this artifact's raw probabilities for VALIDATION only, persists an
inactive compatible calibration artifact set, and never loads TEST.

`app.historical_backtesting` reproduces inference from this exact safe artifact
and persisted preprocessing on TEST only. It does not invoke training, alter
parameters, use live model wiring, compare or promote models, or activate an
artifact.
