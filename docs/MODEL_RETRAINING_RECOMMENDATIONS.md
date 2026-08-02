# Model Retraining Recommendations

Retraining evidence is produced when persistent predictive/input deterioration or multiple blocked scopes justify manual review. Outcomes are `RETRAINING_NOT_REQUIRED`, `RETRAINING_MONITOR`, `RETRAINING_RECOMMENDED`, or urgent review where policy supports it.

The record includes affected scopes, minimum settled evidence, dataset-boundary review, historical-odds review, calibration requirements, and whether LAB use may continue. It never invokes the training pipeline. An operator must separately review chronology, leakage, competition support, data licensing, and backtesting before any future training task.
