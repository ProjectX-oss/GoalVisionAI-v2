# Dataset readiness and independent evidence — 2026-10-01

Status: PASS (offline regression and read-only projection);
NEEDS_MORE_EVIDENCE (next natural eligible research attempt).

The 2026-10-01 natural research attempt returned CYCLE_COOLDOWN; it did not
reach readiness or train. The next timer is 2026-10-02T02:12Z, but the prior
cycle is dated 2026-09-28 and the seven-day cooldown remains applicable.
No natural eligible attempt was manufactured or production research invoked.

Read-only projection at 2026-10-01T13:28:03Z:
TRAIN=581, VALIDATION=28, SEALED_HOLDOUT=327, PURGED=807.
Status RESEARCH_DATASET_NOT_READY: VALIDATION_SAMPLE_INSUFFICIENT.
All cross-partition fixture/observation intersections are empty. The splitter
retains the 24-hour settlement-availability embargo. Holdout consumption is zero.
Exact evidence: docs/evidence/forward_ai_ml_20261001/dataset_readiness_projection.json.

The source audit contains 12 legacy COMBO_LEG records, 114 SINGLE, 1629 SHADOW.
Legacy records are preserved but excluded from eligibility, datasets, metrics
and training. New combo settlements only enter combo_analytics. Direct combo
ingestion/training fails closed. Independent single/shadow evidence cannot be
silenced by a legacy combo record with the same opportunity identity.

Each PREMATCH research attempt now includes a read-only readiness projection
even when cooldown/sample requirements prevent training. No-ready attempts
still create no cycle, model, split assignment or holdout record.

Changed: adaptive_lab contracts, observations, policy, datasets, metrics, models,
automl; test_forward_metrics.py and test_no_combo_learning.py.
Validation: 421 adaptive_lab tests pass, including no training or writes at
VALIDATION=0/29, insufficient/consumed holdout, train class diversity, source
snapshot locking, combo exclusion and explicit cooldown readiness.
No deployment, production writes, champion mutation or selection change.
