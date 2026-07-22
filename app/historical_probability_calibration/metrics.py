"""Deterministic VALIDATION calibration metrics and reliability summaries."""

from __future__ import annotations

import math
import json
from decimal import Decimal

from .fingerprint import canonical_json, sha256_fingerprint
from .models import CalibrationMetric, ReliabilityBin


CALIBRATED_TARGETS = (
    "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5",
    "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO",
)


def calculate_calibration_metrics(examples_and_predictions, bin_count: int):
    metrics, bins = [], []
    order = 0
    raw_briers, calibrated_briers, raw_losses, calibrated_losses = [], [], [], []
    improved = worsened = 0
    for target in CALIBRATED_TARGETS:
        labels = tuple(dict(example.labels)[target] for example, _ in examples_and_predictions)
        raw = tuple(_value(prediction.raw_probabilities, target) for _, prediction in examples_and_predictions)
        calibrated = tuple(_value(prediction.calibrated_probabilities, target) for _, prediction in examples_and_predictions)
        raw_summary = _binary_summary(raw, labels)
        calibrated_summary = _binary_summary(calibrated, labels)
        raw_briers.append(raw_summary["brier_score"]); calibrated_briers.append(calibrated_summary["brier_score"])
        raw_losses.append(raw_summary["log_loss"]); calibrated_losses.append(calibrated_summary["log_loss"])
        improved += calibrated_summary["brier_score"] < raw_summary["brier_score"]
        worsened += calibrated_summary["brier_score"] > raw_summary["brier_score"]
        for phase, summary in (("RAW", raw_summary), ("CALIBRATED", calibrated_summary)):
            phase_values = raw if phase == "RAW" else calibrated
            phase_bins = _reliability(target, phase, phase_values, labels, bin_count)
            summary["expected_calibration_error"] = sum(
                (item.absolute_gap or Decimal(0)) * item.sample_count for item in phase_bins
            ) / len(labels)
            summary["maximum_calibration_error"] = max((item.absolute_gap or Decimal(0)) for item in phase_bins)
            snapshot = canonical_json(summary)
            for name, value in summary.items():
                metrics.append(CalibrationMetric(target, phase, name, value if isinstance(value, Decimal) else Decimal(value), snapshot, order)); order += 1
            bins.extend(phase_bins)
    # Coherent multiclass metrics are persisted separately from one-vs-rest summaries.
    for phase in ("RAW", "CALIBRATED"):
        rows = [prediction.raw_probabilities if phase == "RAW" else prediction.calibrated_probabilities for _, prediction in examples_and_predictions]
        actual = [next(index for index, name in enumerate(("HOME_WIN", "DRAW", "AWAY_WIN")) if dict(example.labels)[name]) for example, _ in examples_and_predictions]
        probabilities = [tuple(_value(row, name) for name in ("HOME_WIN", "DRAW", "AWAY_WIN")) for row in rows]
        summary = _multiclass_summary(probabilities, actual)
        snapshot = canonical_json(summary)
        for name, value in summary.items():
            metrics.append(CalibrationMetric("MATCH_RESULT", phase, name, value if isinstance(value, Decimal) else None, snapshot, order)); order += 1
    aggregate_raw = (
        ("macro_brier", sum(raw_briers, Decimal(0)) / len(raw_briers)),
        ("macro_log_loss", sum(raw_losses, Decimal(0)) / len(raw_losses)),
        ("weighted_log_loss", sum(raw_losses, Decimal(0)) / len(raw_losses)),
        ("exact_target_coverage", Decimal(1)),
    )
    aggregate_calibrated = (
        ("macro_brier", sum(calibrated_briers, Decimal(0)) / len(calibrated_briers)),
        ("macro_log_loss", sum(calibrated_losses, Decimal(0)) / len(calibrated_losses)),
        ("weighted_log_loss", sum(calibrated_losses, Decimal(0)) / len(calibrated_losses)),
        ("exact_target_coverage", Decimal(1)),
        ("improved_target_count", Decimal(improved)),
        ("worsened_target_count", Decimal(worsened)),
    )
    for phase, aggregate in (("RAW", aggregate_raw), ("CALIBRATED", aggregate_calibrated)):
        snapshot = canonical_json(aggregate)
        for name, value in aggregate:
            metrics.append(CalibrationMetric("AGGREGATE", phase, name, value, snapshot, order)); order += 1
    return tuple(metrics), tuple(bins), aggregate_raw, aggregate_calibrated


def calibration_parameter_metrics(target_artifacts, starting_order: int):
    """Expose Platt/identity calibration slope and intercept when defined."""
    result = []
    order = starting_order
    for artifact in target_artifacts:
        if artifact.derivation_snapshot != "{}":
            continue
        payload = json.loads(artifact.fitted_parameters_snapshot)
        parameters = payload["parameters"]
        if payload["method"] == "platt":
            values = (("calibration_slope", Decimal(parameters["a"])),
                      ("calibration_intercept", Decimal(parameters["b"])))
        elif payload["method"] == "identity":
            values = (("calibration_slope", Decimal(1)),
                      ("calibration_intercept", Decimal(0)))
        else:
            continue
        snapshot = canonical_json({name: value for name, value in values})
        for name, value in values:
            result.append(CalibrationMetric(
                artifact.target_identity, "CALIBRATED", name, value, snapshot, order,
            ))
            order += 1
    return tuple(result)


def _binary_summary(probabilities, labels):
    count = len(labels)
    clipped = tuple(min(Decimal("0.999999999999999"), max(Decimal("0.000000000000001"), value)) for value in probabilities)
    brier = sum((value - label) ** 2 for value, label in zip(probabilities, labels)) / count
    log_loss = Decimal(str(math.fsum(-(label * math.log(float(value)) + (1-label) * math.log(1-float(value))) for value, label in zip(clipped, labels)) / count))
    return {
        "sample_count": Decimal(count), "positive_count": Decimal(sum(labels)),
        "negative_count": Decimal(count - sum(labels)), "brier_score": brier,
        "log_loss": log_loss, "probability_minimum": min(probabilities),
        "probability_maximum": max(probabilities),
        "probability_mean": sum(probabilities, Decimal(0)) / count,
    }


def _multiclass_summary(probabilities, actual):
    count = len(actual)
    loss = Decimal(str(math.fsum(-math.log(max(float(row[label]), 1e-15)) for row, label in zip(probabilities, actual)) / count))
    brier = sum(sum((value - (1 if index == label else 0)) ** 2 for index, value in enumerate(row)) for row, label in zip(probabilities, actual)) / count
    predicted = tuple(max(range(3), key=lambda index: row[index]) for row in probabilities)
    confusion = tuple(tuple(sum(a == row and p == column for a, p in zip(actual, predicted)) for column in range(3)) for row in range(3))
    return {
        "multiclass_log_loss": loss, "multiclass_brier_score": brier,
        "accuracy": Decimal(sum(a == p for a, p in zip(actual, predicted))) / count,
        "confusion_matrix": confusion,
    }


def _reliability(target, phase, probabilities, labels, count):
    result = []
    for index in range(count):
        lower, upper = Decimal(index) / count, Decimal(index + 1) / count
        selected = tuple((p, y) for p, y in zip(probabilities, labels) if lower <= p < upper or (index == count - 1 and p == upper))
        if selected:
            mean = sum((item[0] for item in selected), Decimal(0)) / len(selected)
            observed = Decimal(sum(item[1] for item in selected)) / len(selected)
            gap = abs(mean - observed)
        else: mean = observed = gap = None
        fingerprint = sha256_fingerprint({"target": target, "phase": phase, "index": index, "lower": lower, "upper": upper, "sample_count": len(selected), "mean": mean, "observed": observed, "gap": gap})
        result.append(ReliabilityBin(target, phase, index, lower, upper, len(selected), mean, observed, gap, fingerprint))
    return result


def _value(probabilities, target):
    return next(item.probability for item in probabilities.ordered_probabilities if item.target.value == target)
