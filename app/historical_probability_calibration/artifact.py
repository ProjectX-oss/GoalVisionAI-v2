"""Apply persisted calibration parameters with explicit reconciliation and projection."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.calibration import CalibratorSerializer
from app.prediction_inference import OFFICIAL_TARGET_ORDER, RawProbability, RawProbabilitySet

from .fingerprint import canonical_json
from .models import ValidationPrediction
from .validation import validate_calibrated_probabilities


def apply_calibration(prediction: ValidationPrediction, target_artifacts, policy):
    calibrators = {
        item.target_identity: CalibratorSerializer().deserialize(__import__("json").loads(item.fitted_parameters_snapshot))
        for item in target_artifacts if item.derivation_snapshot == "{}"
    }
    raw = {item.target.value: item.probability for item in prediction.raw_probabilities.ordered_probabilities}
    preliminary_result = tuple(_clamp(calibrators[name].calibrate(raw[name]), policy) for name in ("HOME_WIN", "DRAW", "AWAY_WIN"))
    result = _bounded_simplex(preliminary_result, policy.minimum_probability)
    reconciliation = canonical_json({
        "policy": "LOWER_BOUNDED_SIMPLEX_V1", "pre_reconciliation": preliminary_result,
        "post_reconciliation": result, "maximum_adjustment": max(abs(a - b) for a, b in zip(preliminary_result, result)),
    })
    preliminary_totals = tuple(_clamp(calibrators[name].calibrate(raw[name]), policy) for name in ("OVER_1_5", "OVER_2_5", "OVER_3_5"))
    totals = _decreasing_pava(preliminary_totals)
    total_adjustments = tuple(abs(a - b) for a, b in zip(preliminary_totals, totals))
    monotonicity = canonical_json({
        "policy": "DECREASING_PAVA_V1", "pre_projection": preliminary_totals,
        "post_projection": totals, "maximum_adjustment": max(total_adjustments),
        "mean_adjustment": sum(total_adjustments, Decimal(0)) / Decimal(3),
        "affected": any(value > 0 for value in total_adjustments),
    })
    btts_yes = _clamp(calibrators["BTTS_YES"].calibrate(raw["BTTS_YES"]), policy)
    values = {
        "HOME_WIN": result[0], "DRAW": result[1], "AWAY_WIN": result[2],
        "OVER_1_5": totals[0], "UNDER_1_5": Decimal(1) - totals[0],
        "OVER_2_5": totals[1], "UNDER_2_5": Decimal(1) - totals[1],
        "OVER_3_5": totals[2], "UNDER_3_5": Decimal(1) - totals[2],
        "BTTS_YES": btts_yes, "BTTS_NO": Decimal(1) - btts_yes,
    }
    calibrated = RawProbabilitySet(tuple(RawProbability(target, values[target.value]) for target in OFFICIAL_TARGET_ORDER))
    validate_calibrated_probabilities(calibrated, policy.minimum_probability, policy.maximum_probability, policy.reconciliation_tolerance)
    return replace(prediction, calibrated_probabilities=calibrated,
                   monotonicity_adjustment_snapshot=monotonicity,
                   reconciliation_snapshot=reconciliation)


def _clamp(value, policy):
    return min(policy.maximum_probability, max(policy.minimum_probability, value))


def _bounded_simplex(values, epsilon):
    available = Decimal(1) - Decimal(len(values)) * epsilon
    total = sum(values, Decimal(0))
    if total <= 0: raise ValueError("Cannot reconcile a zero probability vector.")
    weights = tuple(value / total for value in values)
    first = epsilon + available * weights[0]
    second = epsilon + available * weights[1]
    third = Decimal(1) - first - second
    return first, second, third


def _decreasing_pava(values):
    blocks = [[index, index, value, 1] for index, value in enumerate(values)]
    index = 0
    while index < len(blocks) - 1:
        if blocks[index][2] >= blocks[index + 1][2]:
            index += 1
            continue
        left, right = blocks[index], blocks[index + 1]
        count = left[3] + right[3]
        mean = (left[2] * left[3] + right[2] * right[3]) / count
        blocks[index:index + 2] = [[left[0], right[1], mean, count]]
        index = max(0, index - 1)
    result = [Decimal(0)] * len(values)
    for start, end, mean, _ in blocks:
        for position in range(start, end + 1): result[position] = mean
    return tuple(result)
