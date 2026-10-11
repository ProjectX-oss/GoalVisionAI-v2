# PREMATCH calibration research — 2026-10-10

**PASS — research fit. BLOCKED_NEEDS_MORE_EVIDENCE — independent quality and activation.**

Authoritative snapshot: 2026-10-10 19:47:52.397924 Europe/Riga
(16:47:52.397924 UTC). Actual isolated fitting timestamp: 19:57:01.386171 Riga.
No production calibration was registered or activated. Existing raw forecasts
and historical results were not rewritten.

## Readiness and provenance

| Item | Verified value |
|---|---|
| Independent calibration examples | 346 / required 300 |
| TRAIN | 1804 observations / 560 fixtures |
| CALIBRATION_FIT | 346 observations / 346 fixtures |
| VALIDATION | 0 |
| SEALED_HOLDOUT | 0 |
| PURGED | 766 observations / 304 fixtures |
| Excluded | 22 observations / 20 fixtures |
| Cross-partition fixture intersections | 0 |
| Champion family | EXISTING_PREMATCH_BASELINE_V1 |
| Feature schema | LAB_FROZEN_FEATURES_V1 |
| Raw probability replay | 346 exact Decimal matches to frozen bootstrap inference |
| Production calibration artifacts | 0; detached research artifact only |
| Promotion | NOT_ELIGIBLE |

Champion:
`generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`.
Bootstrap artifact:
`bootstrap-artifact-694ab4cc98179ddb0bb2e62d9d77a01c0fee5f3e6d3eff28f9e240e34f929f8d`.
Internal model artifact fingerprint:
`85ad28129ec1581a9ce3d6f72cc1551fe5cf4df401b1dc1fd0965999d4892a49`.
The bootstrap ID uses the complete document digest, while the internal fingerprint
uses the model's existing schema; these are deliberately different identities.

Frozen plan fingerprint:
`9b154abc5b1ca4f18187150c2ca0a8d4d37b93b9c3893e97b2e61457329ca439`.
Dataset fingerprint:
`c3d15632ee63c6354703d893ce98246962148f19d7b8d6762779cb4be165d534`.
Research artifact fingerprint:
`db7397acf8cf924cb544bf502ad8663ec7658a15e3b5ca3f9257c198bed40aaf`.

CALIBRATION_FIT closed on October 10 at 03:00 Riga. The frozen UTC calendar starts
VALIDATION October 11 at 00:00 UTC / 03:00 Riga and SEALED_HOLDOUT October 19 at
00:00 UTC / 03:00 Riga. No boundaries moved. Later partition documents are excluded
in SQL before deserialization; no validation/holdout labels are fitted or evaluated.
The existing complete research gate remains blocked. The new adapter implements
only this explicitly authorized detached fit, not a bypass of promotion gates.

## Method comparison

All metrics below are **CALIBRATION_FIT in-sample**, not forward validation.
Positive bias means predicted probability exceeds observed frequency.

| Method | Brier | Log loss | ECE | MCE | Calibration bias |
|---|---:|---:|---:|---:|---:|
| Identity/raw | 0.230160 | 0.654071 | 0.024123 | 0.421179 | −0.008563 |
| Platt/sigmoid | 0.229341 | 0.651289 | 0.010801 | 0.169861 | −0.000001 |
| Temperature | 0.230215 | 0.653973 | 0.023134 | 0.488650 | −0.014661 |
| Isotonic | NOT_FITTED | — | — | — | — |

Platt: slope parameter a=0.39582002621737844, intercept b=0.3640315473799575;
regularization=0.001, epsilon=1e−12. Existing reviewed fitter converged in five
iterations. Reusing the regularized logit diagnostic gives raw slope/intercept
0.395820/0.364032, Platt 0.998861/0.000666 and temperature 0.416446/0.364037.
These estimates also use the fit sample and are not independent validation.

Platt reduces fit Brier by 0.000819 and fit log loss by 0.002782. That small change
does not establish prospective benefit. Its compression into mostly 60–70%
probabilities can reduce in-sample calibration errors without proving discrimination
or betting value. No winning method has been selected.

Isotonic was skipped: 346 is below the existing 1000-example minimum, and no
independent validation is available. No minimum was relaxed.

## Reliability and sample limitations

| Raw probability bin | n | Mean prediction | Observed frequency |
|---|---:|---:|---:|
| 0.50–0.60 | 99 | 0.575782 | 0.585859 |
| 0.60–0.70 | 199 | 0.634889 | 0.658291 |
| 0.70–0.80 | 43 | 0.734558 | 0.720930 |
| 0.80–0.90 | 5 | 0.821179 | 0.400000 |

The five-example high-probability bin is a warning to collect evidence, not a
reliable estimate for threshold changes. Extreme-probability probes at .001,
.01, .1, .5, .9, .99 and .999 are numerical diagnostics only; they are not observed
extreme-frequency evidence. Full before/after bins, extrema and probes are in JSON.

Market-family sample: TOTAL 234, BTTS 102, 1X2 10 (HOME_WIN 8, AWAY_WIN 2,
DRAW 0). Per-market and family scores are included in the artifact. A draw
calibration conclusion is unavailable, and no family-specific calibrator was
fitted. The global fit must not be treated as an evaluated three-way probability
vector transform or automatically applied to LIVE/COMBO.

## Isolation, tests and reproducibility

The detached artifact has production_eligible=false, activation_allowed=false,
promotion_allowed=false and method_selection=null. The existing serialized
Platt foundation has a nested numerical fit eligibility flag; that flag is not
governance permission. This enclosing artifact is not a registry model wrapper.
It has no production loader, pointer or worker hook.

14 new synthetic tests cover minimum sample, exact frozen probability replay,
missing context, model provenance, chronology, invalid 0/1/NaN probabilities,
COMBO exclusion and future-label isolation. The final adjacent matrix passed
1088 tests plus five subtests. Repeating the real isolated CLI produced byte-identical
artifact output. Real socket connections were disabled.

Private immutable source copies are retained outside Git at
`/home/arvis/goalvision-research/calibration-live-recovery-20261010/`.
They must not be uploaded to GitHub. Reproduce from the reviewed branch:

```bash
cd /home/arvis/goalvision-worktrees/calibration-live-recovery-20261010
/home/arvis/GoalVisionAI/.venv/bin/python -B operations/calibration-live-recovery/calibrate.py \
  --database /home/arvis/goalvision-research/calibration-live-recovery-20261010/audit.db \
  --as-of 2026-10-10T16:47:52.397924+00:00 \
  --fitted-at 2026-10-10T16:57:01.386171+00:00 \
  --output /home/arvis/goalvision-research/calibration-live-recovery-20261010/calibration_final.json
```

Source audit DB SHA256:
`0f5059ba0a5fe4293288974689c50f61334d71ad05d13690ec5789d46fc6ec19`.
Source ledger DB SHA256:
`144a05b5065774c52daed1a656ce939d13cce7ac589c756db9fa8fc45314c50d`.
The pinned fitted-at parameter reproduces this experiment; it must never be used
to backdate a new fit using later information.

Next legal action: keep this artifact frozen, collect validation in its declared
window, then evaluate the fixed alternatives on independent evidence. Do not
activate, tune on validation/holdout or recommend champion promotion now.

Evidence: `docs/evidence/calibration_live_recovery_20261010/calibration.json`.

## 2026-10-11 continuation check

Read-only snapshot at 11:05:21.700896 UTC / 14:05:21 Riga confirms the same
champion, artifact, calendar and 346-fixture FIT sample. TRAIN remains 1804;
VALIDATION and SEALED_HOLDOUT remain 0. PURGED is now 782 observations / 320
fixtures; excluded remains 22 / 20. All six cross-partition fixture intersections
are zero. The current readiness dataset fingerprint is
`66323033232432894c28e8a0c5a65aa3718c70a5decb27edc349ec6cec414174`;
this larger readiness population is distinct from the frozen experiment dataset.

The October 10 command above was rerun against its original immutable DB copy:
byte-identical output, fingerprint `db7397acf8cf924cb544bf502ad8663ec7658a15e3b5ca3f9257c198bed40aaf`.
No new fit was backdated or run on October 11 data. The code rejects a new fit
at or after the validation boundary. The resumed focused matrix passed 64 tests
and the adjacent matrix passed 841 tests (overlapping runs, not additive counts).

Governance remains CHALLENGER_RESEARCH, 59 model artifacts, 133 training runs,
0 production calibration artifacts, 0 validation results, 0 shadow comparisons,
0 promotion gates and 0 rollback events. The one activation is the original
bootstrap. Legacy COMBO_LEG rows remain immutable and excluded from learning.
No evidence currently supports calibration activation or champion promotion.
