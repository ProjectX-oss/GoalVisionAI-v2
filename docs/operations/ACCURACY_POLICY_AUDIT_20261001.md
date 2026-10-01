# Accuracy-first policy audit — 2026-10-01

Status: PASS for tested safety/identity/exposure contracts;
NEEDS_MORE_EVIDENCE for probability quality, calibration and realised performance.
Evidence: docs/evidence/forward_ai_ml_20261001/accuracy_policy_audit.json.

Nine confirmed SINGLE tickets today: eight negative EV, eight market-consensus
only, all nine UNCALIBRATED_LAB_ENSEMBLE. All nine replay the retained decision
evidence at publication time. This proves reproducibility, not calibration or
independent predictive skill. All nine were still pending in the snapshot.

NON_POSITIVE_VALUE remains the sole allowed hard rejection exemption.
55% is not sufficient alone: identity, quote freshness, frozen probability
replay, source decision, publication window, reviewed provenance, severe model/
market/context contradictions, preview and durable claim checks remain.
Signal endpoint probabilities, unavailable/zero-weight probability signals and
duplicate producer entries now fail closed. Multiple implementations in one
independence family still count as one group.

The user policy specifies no hard Lab odds minimum. The draft removes the
remaining 1.30 floor from new SINGLE/accuracy COMBO creation and delivery.
Only the decimal-odds domain (>1) remains. 1.70/2.00 floors are not introduced.
New selection version V2_NO_ODDS_FLOOR; JSON minimum is null. Frozen V1 tickets
retain their 1.30 contract and exact historical message text. No probability,
EV, calibration, confidence or timing thresholds were tuned to realised ROI.

A claimed/published SINGLE fixture now blocks subsequent SINGLE market exposure
for that fixture. Existing singly published fixtures may still form one COMBO,
as explicitly intended. COMBO requires three distinct fixtures, six distinct
teams, disjoint batches and no prior claimed combo fixture; independence remains
an assumption, not a proof against league/context/model error correlation.

Open evidence limits:
- The accepted totals/BTTS accuracy exception uses market consensus alone; it is
  explicitly not independent non-market model evidence. We retain this accepted
  policy and separately measure it rather than claim an independence PASS.
- Optional missing lineup, injury, form and advanced inputs remain recorded.
  Some retained context lacks a source timestamp, preventing full freshness proof.
- No calibration artifact supports these nine probabilities. Extreme but interior
  probabilities and league-quality differences need segmented forward evidence.
  Missing calibration is not silently converted to a calibrated eligibility PASS.
- Snapshot negative-EV W/L/Brier/ECE/ROI is separate; do not infer thresholds
  from this small unsettled cohort.

Tests: 212 pass across policy audit, accuracy delivery/combos, V2 shadow,
presentation and enablement. New tests cover 1.10 singles / 1.331 combo, fixture
exposure, unusable signals, and legacy review/preview preservation.
Changed: publication.py, publication_policy.py, accuracy_combo.py,
public_presentation.py, lab_combo/service.py and corresponding tests.
No deployment, production policy mutation, provider calls or Telegram sends.
