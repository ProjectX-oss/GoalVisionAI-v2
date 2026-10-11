# PREMATCH manual research training — 2026-10-11

## Outcome

**PASS: three detached raw candidates trained and reproduced.**
Quality verdict: **BLOCKED_NEEDS_MORE_EVIDENCE**.
This is a completed one-shot research run requested by the operator (“Es gribu lai macibas uzsakas tagad”), not an automatic production learning cycle or model activation.

First fit started at 2026-10-11 21:26:24 Europe/Riga (18:26:24 UTC).
The corrected complete run started at 21:27:03 and finished at **21:27:06** (18:27:06.927620 UTC).
All three artifacts reproduce exactly across two fits per candidate and across the two executions.

Application model, feature, policy and calendar code was reused without modification. Only a dated operator research recipe and documentation/evidence were added.

## Dataset and provenance

Source: private, detached, read-only SQLite snapshot taken at 2026-10-11 20:42:42 Riga / 17:42:42.676844 UTC.
The trainer receives **only the existing frozen TRAIN partition**:
- 1,804 observations from 560 independent fixtures; 666 WON / 1,138 LOST.
- Sources restricted by the existing calendar allocator to SINGLE/SHADOW. COMBO is excluded.
- TRAIN: 2026-09-18 00:00 UTC through 2026-10-02 00:00 UTC.
- Prediction-before-kickoff, label availability before embargo, binary class diversity, cohort integrity and whole-fixture calendar separation checked.
- TRAIN fixture intersections with CALIBRATION_FIT, VALIDATION_EVALUATION and SEALED_HOLDOUT: all zero.
- Feature schema: LAB_FROZEN_FEATURES_V1.
- Plan fingerprint: 9b154abc5b1ca4f18187150c2ca0a8d4d37b93b9c3893e97b2e61457329ca439.
- Source snapshot SHA256: bdfc92c8968bccfb058be1902838f56fb50815457fccd7c41d6fd609be30d22b.
- Dataset allocation fingerprint: 11aeec83547c727d1243ed2d9d8d48158ff9b0de62ebfd85a5a2b6f45f2846d6.
- TRAIN fingerprint: 94ec20d237671a5eb8b56adfe54e6f7fa8f94f98784f6a990029f1d0fbf3e28a.
- Recipe SHA256: d80c7fed6505bb9c8ab2a09e6a71ed79bd7cb4c42989fea55a7a503d5cbf78ba.
- Completed manifest fingerprint: 00a21154a11d29f5690827a991c25e648a2adafbbedffa5a6b0305a9f5a2c785.

Champion:
generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a.

Champion artifact fingerprint:
85ad28129ec1581a9ce3d6f72cc1551fe5cf4df401b1dc1fd0965999d4892a49.

The existing pure models.train API supports caller-supplied TRAIN research. The production AutoLearner/coordinator were not invoked: their full-cycle validation/holdout/promotion gates remain intact. The automatic 90-day eligibility rule was not changed.

## Predeclared candidates and TRAIN diagnostics

Three specs from LAB_MODEL_REGISTRY_V1 were fixed before fitting. Each uses the same four reviewed base features (prior probability, implied probability, uncertainty, evidence-family count), GLOBAL scope, no interactions/decay/history restriction, seed 1729 and 150 iterations. L2 is 0.1 where used by the family. No hyperparameter search, winner selection or manually invented coefficients.

These scores use **the training sample itself**. They do not establish improvement over champion, forecast accuracy or profit.

| Candidate | TRAIN Brier | TRAIN log loss | TRAIN ECE | Calibration bias | Probability range |
|---|---:|---:|---:|---:|---:|
| LOGISTIC | 0.197578 | 0.579969 | 0.016612 | +0.001498 | 0.079858–0.823911 |
| REGULARIZED_LOGISTIC | 0.199008 | 0.584244 | 0.030799 | +0.000759 | 0.116490–0.750454 |
| STUMP_ENSEMBLE | 0.211939 | 0.613347 | 0.085580 | +0.000321 | 0.230319–0.480001 |

All predictions satisfy 0 < p < 1. Full reliability bins are retained in the private result file. No calibrated wrapper was fitted.

Artifact fingerprints:
- LOGISTIC: 3254e42d17f94ca464c2ca8f71963ab4c2545de3e288504d3bb51013decc01e8.
- REGULARIZED_LOGISTIC: f87e4a49abeec0e426e751385a331a5108e560998d336053e3a87349f5f2b250.
- STUMP_ENSEMBLE: fd3cb58ad1a2e836423e7e8927e0458bf72748d7cbc7cea087456b1e78b74c03.

None of these fingerprints was present in the 59-artifact source registry. New artifacts are detached research files, not additions to the production registry.

## Chronology and remaining evidence

The new candidates were created after the frozen VALIDATION window opened. They cannot be retroactively presented as prospective forecasts for already observed validation outcomes. Before assessing quality or promotion, declare and review a separate future evaluation protocol for these artifacts without moving the existing calendar.

The original 2026-10-10 calibration experiment remains frozen and independent. No calibration refit, validation scoring or sealed holdout evaluation occurred. The existing frozen experiment still awaits independent validation/holdout evidence. At the 20:42 snapshot, VALIDATION had 22 independent fixtures / 56 observations (minimum 30 fixtures and window close still required).

The dynamic full-database FIT projection still fails readiness after late SHADOW additions; this TRAIN-only run does not repair or override that gate. Calendar boundaries, source probabilities and production selection/publication thresholds are unchanged.

## Runtime and verification

- Existing model/calendar/source-isolation/chronology regressions: **96 passed, 0 failed**; outbound socket connections denied.
- Three candidate fits each reproduced exactly; the complete run exited 0.
- Source snapshot byte hash unchanged.
- CPU hard limit 180 seconds; address-space hard limit 768 MiB; nice +10.
- Registry operation estimate 12,988,800, below unchanged 250,000,000 budget.
- First execution fit all candidates but exited 1 during its final full-buffer snapshot hash (MemoryError). Streaming file hashing fixed the research recipe without increasing limits. First-run artifacts and an execution-failure record were preserved; the second execution used a new output directory.
- Production readback at 21:27:36 Riga: unchanged champion, 59 model artifacts, 133 training records, 3 learning cycles, 1 bootstrap activation, 0 rollback, validation or holdout results.
- PREMATCH learning and observer now reference /opt/goalvision-prematch-recovery-380bcf7-20261011/release.env, consistent with operator installation of the earlier package. The agent did not deploy it.
- Actual goalvision-lab-live-evening.timer remains **active/enabled**. Desired Watch state is DISABLED; no timer change was performed.
- Existing daily PREMATCH learning check remains active/enabled with its existing gates. This run did not install or start an automatic worker cycle.

Production deployment by this action = NONE. Production DB writes = 0. Telegram sends = 0. Provider calls = 0. Official changes = NONE. Model activation = NONE.

## Reproduction and operator action

No sudo command or installation is needed for this completed research fit.

Successful private output:
 /home/arvis/goalvision-research/prematch-train-only-20261011-r2

It contains manifest.json, train_rows.json, result.json and three JSON model artifacts. Raw observations and database files are not committed to GitHub.

The dated recipe requires a new output directory and a detached snapshot under the private research root. It refuses execution at/after the sealed holdout window begins.

```bash
cd /home/arvis/goalvision-worktrees/calibration-live-recovery-20261010
/home/arvis/GoalVisionAI/.venv/bin/python -B operations/prematch-train-only/run.py \
  --snapshot-directory /home/arvis/goalvision-research/learning-watch-20261011-evening \
  --output /home/arvis/goalvision-research/prematch-train-only-20261011-reproduction
```

Repeated fitting on the same TRAIN data is a reproducibility check, not new independent learning evidence. No candidate is selected for deployment.
