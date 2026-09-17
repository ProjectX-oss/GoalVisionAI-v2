# Input and Data Drift Governance

The foundation compares recent and baseline feature distributions with deterministic summaries, missingness and PSI. It reports each feature separately and aggregates `INPUT_DRIFT_CLEAR`, `WARNING`, `BLOCKED`, or `SAMPLE_INSUFFICIENT`.

Data completeness separately tracks required and optional completeness, lineup and injury availability, provider timestamps, odds freshness, and result/settlement evidence where available. Material required-data deterioration blocks LAB eligibility even if recent outcomes are wins.

Drift is evidence of changed inputs, not proof that the change caused model degradation. Retraining recommendations remain manual evidence and never start training.
