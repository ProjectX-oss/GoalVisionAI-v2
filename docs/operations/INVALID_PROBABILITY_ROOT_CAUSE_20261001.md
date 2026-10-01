# INVALID_MODEL_PROBABILITY root cause — 2026-10-01

Status: PASS for the inspected forward window; no numerical repair warranted.
Evidence: docs/evidence/forward_ai_ml_20261001/invalid_probability.json.
Scope: 12 immutable rehearsal cycles, 07:30–13:00 UTC on 2026-10-01,
3481 candidate documents, 63 invalid incidents, 20 unique fixtures.
HOME_WIN: 43; AWAY_WIN: 20. Repeated fixtures are separate captured incidents.

Every incident contains raw provider "0%", normalized API probability "0E+1",
and ensemble probability "0E+1". Producer and independence group are
API_FOOTBALL_PREDICTION. Each has the CURRENT_/PREDICTIONS normalization version
and source fingerprint; current-market consensus is independently recorded.

Trace: Decimal("0") / Decimal(100), then distribution sum normalization,
then the single-predictive-family weighted mean. All preserve exact zero.
No complement calculation is involved for these HOME_WIN/AWAY_WIN outcomes.
Decimal's exponent notation and JSON string round-trip do not introduce zero.
The source is the provider's endpoint estimate; no evidence establishes why
the provider assigned zero or whether it rounded a small nonzero probability.

The candidate calibration is UNCALIBRATED_LAB_ENSEMBLE. Per-incident missing
inputs, model generation and absent/present artifact identity are explicit.
Missing artifact identity must not be filled with a fabricated calibration.
Existing INVALID_MODEL_PROBABILITY rejection remains fail-closed.
No clamp, epsilon replacement, probability threshold or publication change.

Tests: test_provider_zero_trace.py plus test_prematch_probability_guard.py
reproduce provider normalization, serialization, ensemble rejection and continued
processing of subsequent valid candidates. This does not assert all historical
incidents share this root cause; the report identifies its inspected window.
