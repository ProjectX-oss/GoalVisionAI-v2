# Prediction reasoning policy

Policy `goalvision-prediction-reasoning-policy-v1` is centralized in
`app/prediction_explainability/policy.py` and fingerprinted into every record.

- Public copy contains at most four supporting factors and three risks.
- Operator evidence may retain all 78 input features for every estimator class.
- Factors must pass absolute and relative materiality thresholds and remain
  traceable to exact signed contributions.
- Missing inputs, median imputation, unavailable lineups/injuries, odds age,
  calibration changes and distribution shift are disclosed when applicable.
- Confidence combines calibrated probability, actionability, evidence quality,
  missingness, shift, odds freshness and explanation stability.
- Extreme probabilities, required missing data, blocked calibration or blocked
  shift make reasoning ineligible.
- Correct-score, combo, certainty, guarantee and unsupported generic causal
  claims are prohibited.
- Public text is deterministic Latvian HTML and remains within the reserved
  Telegram message budget.

Changing thresholds or publication philosophy requires explicit approval under
`AGENTS.md` and must be backtested before any production use.
