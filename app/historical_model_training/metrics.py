"""Deterministic descriptive raw-probability metrics."""

from __future__ import annotations

import json
import math
from decimal import Decimal

from app.historical_dataset_split import Partition
from app.historical_training_dataset import HistoricalTrainingExample

from .fingerprint import canonical_json
from .models import MetricRecord
from .numerics import deterministic_log, square


def calculate_metrics(partition: Partition, examples, predictions, start_order: int = 0):
    records = []
    losses, briers = [], []
    order = start_order
    target_names = tuple(item.target.value for item in predictions[0].ordered_probabilities) if predictions else ()
    for target in target_names:
        labels = [dict(item.labels)[target] for item in examples]
        probabilities = [float(pred.probability_for(_target(pred, target))) for pred in predictions]
        clipped = [min(max(value, 1e-15), 1 - 1e-15) for value in probabilities]
        loss = math.fsum(-(label * deterministic_log(prob) + (1 - label) * deterministic_log(1 - prob)) for label, prob in zip(labels, clipped)) / len(labels)
        brier = math.fsum(square(prob - label) for label, prob in zip(labels, probabilities)) / len(labels)
        accuracy = sum((prob >= 0.5) == bool(label) for label, prob in zip(labels, probabilities)) / len(labels)
        losses.append(loss); briers.append(brier)
        snapshot = canonical_json({
            "sample_count": len(labels), "positive_count": sum(labels),
            "negative_count": len(labels) - sum(labels), "class_distribution": (len(labels) - sum(labels), sum(labels)),
            "log_loss": loss, "brier_score": brier, "accuracy_at_0_5": accuracy,
            "probability_minimum": min(probabilities), "probability_maximum": max(probabilities),
            "probability_mean": math.fsum(probabilities) / len(probabilities),
        })
        for name, value in json.loads(snapshot).items():
            metric_value = Decimal(str(value)) if isinstance(value, (int, float)) else None
            records.append(MetricRecord(partition, target, name, metric_value, snapshot, order)); order += 1
    if predictions:
        result_names = ("HOME_WIN", "DRAW", "AWAY_WIN")
        result_probabilities = [
            tuple(float(pred.probability_for(_target(pred, name))) for name in result_names)
            for pred in predictions
        ]
        actual = [next(index for index, name in enumerate(result_names) if dict(item.labels)[name]) for item in examples]
        predicted = [max(range(3), key=lambda index: row[index]) for row in result_probabilities]
        multiclass_loss = math.fsum(-deterministic_log(max(row[label], 1e-15)) for row, label in zip(result_probabilities, actual)) / len(actual)
        multiclass_accuracy = sum(left == right for left, right in zip(actual, predicted)) / len(actual)
        confusion = tuple(tuple(sum(a == row and p == column for a, p in zip(actual, predicted)) for column in range(3)) for row in range(3))
        result_snapshot = canonical_json({
            "class_order": result_names, "sample_count": len(actual),
            "multiclass_log_loss": multiclass_loss, "multiclass_accuracy": multiclass_accuracy,
            "confusion_matrix": confusion,
        })
        for name, value in (
            ("multiclass_log_loss", Decimal(str(multiclass_loss))),
            ("multiclass_accuracy", Decimal(str(multiclass_accuracy))),
            ("confusion_matrix", None),
        ):
            records.append(MetricRecord(partition, "MATCH_RESULT", name, value, result_snapshot, order)); order += 1
    aggregate = (
        ("macro_brier_score", Decimal(str(math.fsum(briers) / len(briers)))),
        ("macro_log_loss", Decimal(str(math.fsum(losses) / len(losses)))),
        ("weighted_log_loss", Decimal(str(math.fsum(losses) / len(losses)))),
        ("exact_target_coverage", Decimal(str(len(target_names) / 11))),
    ) if target_names else ()
    aggregate_snapshot = canonical_json(dict(aggregate))
    for name, value in aggregate:
        records.append(MetricRecord(partition, "AGGREGATE", name, value, aggregate_snapshot, order)); order += 1
    return tuple(records), aggregate


def _target(prediction, value):
    return next(item.target for item in prediction.ordered_probabilities if item.target.value == value)
