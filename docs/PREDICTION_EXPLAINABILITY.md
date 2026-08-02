# Prediction explainability foundation

GoalVision AI explains a live-78 prediction from the exact persisted model
artifact, preprocessing parameters and immutable model-input vector. The engine
does not call a language model and does not infer causes. It deterministically
reconstructs every multinomial class score as `intercept + sum(coefficient ×
transformed value)` and verifies the corresponding softmax probability within
the central reasoning policy tolerance.

The reviewed catalog covers all 78 canonical inputs in their contract order.
It records Latvian display wording, grouping, units, direction semantics,
missingness, expected range, source/cutoff expectations, public eligibility and
quality dependencies. Public evidence is selected only after materiality
filtering and grouping; the operator record retains complete class and feature
detail.

Match-result and BTTS selections use class-score contrasts. Totals are derived
from the four persisted total-goals bucket classes. Their evidence is therefore
labelled `DERIVED_BUCKET_SCORE_CONTRAST` or `COMPLEMENT_INVERSION`; GoalVision AI
never invents a direct market logit for a derived total.

Each immutable reasoning record links analysis, observation when present,
model input, artifact, calibration, catalog and policy fingerprints. It includes
positive and negative evidence, risks, missing data, calibration and shift
disclosures, confidence rationale, counterfactual sensitivity, all eleven
market explanations, and an exact trace fingerprint. Schema v40 stores the
record and normalized append-only contribution, group, factor, market and audit
children.

This is evidence about model mechanics, not causation, prediction correctness,
profitability or statistical significance.
