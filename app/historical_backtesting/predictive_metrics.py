"""TEST-only predictive quality and calibration metrics."""

from __future__ import annotations

from decimal import Decimal, localcontext

from .fingerprint import canonical_json, sha256_fingerprint
from .models import BacktestMetric, BacktestReliabilityBin


def calculate_predictive_metrics(predictions, bin_count=10, start_order=0, *, run_namespace=""):
    rows = []
    bins = []
    aggregate_values = {}
    target_names = tuple(
        item.target.value for item in predictions[0].raw_probabilities.ordered_probabilities
    ) if predictions else ()
    phases = (("RAW", "raw_probabilities"), ("CALIBRATED", "calibrated_probabilities"))
    for phase, attribute in phases:
        per_target = []
        for target in target_names:
            observations = tuple(
                (_probability(getattr(item, attribute), target), dict(item.labels)[target])
                for item in predictions
            )
            brier = _mean(tuple((p - Decimal(y)) ** 2 for p, y in observations))
            log_loss = _mean(tuple(_binary_log_loss(p, y) for p, y in observations))
            probabilities = tuple(item[0] for item in observations)
            target_bins = reliability_bins(target, phase, observations, bin_count, run_namespace=run_namespace)
            bins.extend(target_bins)
            ece = sum(
                (
                    (Decimal(item.sample_count) / Decimal(len(observations))) * (item.absolute_gap or Decimal(0))
                    for item in target_bins
                ),
                Decimal(0),
            ) if observations else Decimal(0)
            mce = max((item.absolute_gap or Decimal(0) for item in target_bins), default=Decimal(0))
            values = {
                "sample_count": Decimal(len(observations)),
                "target_coverage": Decimal(1) if observations else Decimal(0),
                "binary_brier_score": brier,
                "binary_log_loss": log_loss,
                "probability_minimum": min(probabilities, default=Decimal(0)),
                "probability_maximum": max(probabilities, default=Decimal(0)),
                "probability_mean": _mean(probabilities),
                "expected_calibration_error": ece,
                "maximum_calibration_error": mce,
            }
            per_target.append(values)
            rows.extend(_metric_rows("PREDICTIVE", f"{phase}:{target}", values, start_order + len(rows), run_namespace))
        result_observations = tuple(
            (
                tuple(_probability(getattr(item, attribute), target) for target in ("HOME_WIN", "DRAW", "AWAY_WIN")),
                _result_index(dict(item.labels)),
            )
            for item in predictions
        )
        multiclass_log = _mean(tuple(_multiclass_log_loss(p, y) for p, y in result_observations))
        multiclass_brier = _mean(tuple(_multiclass_brier(p, y) for p, y in result_observations))
        accuracy = _mean(
            tuple(
                Decimal(int(max(range(3), key=lambda index: values[index]) == outcome))
                for values, outcome in result_observations
            )
        )
        confusion = [[0, 0, 0] for _ in range(3)]
        for values, outcome in result_observations:
            confusion[outcome][max(range(3), key=lambda index: values[index])] += 1
        aggregate = {
            "sample_count": Decimal(len(predictions)),
            "multiclass_log_loss": multiclass_log,
            "multiclass_brier_score": multiclass_brier,
            "accuracy": accuracy,
            "macro_binary_log_loss": _mean(tuple(item["binary_log_loss"] for item in per_target)),
            "macro_binary_brier_score": _mean(tuple(item["binary_brier_score"] for item in per_target)),
            "weighted_binary_log_loss": _mean(tuple(item["binary_log_loss"] for item in per_target)),
            "weighted_binary_brier_score": _mean(tuple(item["binary_brier_score"] for item in per_target)),
        }
        rows.extend(_metric_rows("PREDICTIVE", f"{phase}:AGGREGATE", aggregate, start_order + len(rows), run_namespace))
        rows.append(_snapshot_row("PREDICTIVE", f"{phase}:CONFUSION_MATRIX", "confusion_matrix", confusion, start_order + len(rows), run_namespace))
        aggregate_values.update({f"{phase.lower()}_{name}": value for name, value in aggregate.items()})
    if predictions:
        aggregate_values["calibration_brier_improvement"] = (
            aggregate_values["raw_macro_binary_brier_score"]
            - aggregate_values["calibrated_macro_binary_brier_score"]
        )
        aggregate_values["calibration_log_loss_improvement"] = (
            aggregate_values["raw_macro_binary_log_loss"]
            - aggregate_values["calibrated_macro_binary_log_loss"]
        )
    return tuple(rows), tuple(bins), tuple(sorted(aggregate_values.items()))


def reliability_bins(target, phase, observations, bin_count, *, run_namespace=""):
    result = []
    width = Decimal(1) / Decimal(bin_count)
    for index in range(bin_count):
        lower = width * index
        upper = Decimal(1) if index == bin_count - 1 else width * (index + 1)
        selected = tuple(
            (probability, outcome) for probability, outcome in observations
            if probability >= lower and (probability <= upper if index == bin_count - 1 else probability < upper)
        )
        mean_probability = _mean(tuple(item[0] for item in selected)) if selected else None
        frequency = _mean(tuple(Decimal(item[1]) for item in selected)) if selected else None
        gap = abs(mean_probability - frequency) if selected else None
        fingerprint = sha256_fingerprint(
            {
                "target": target, "phase": phase, "bin_index": index,
                "bounds": (lower, upper), "sample_count": len(selected),
                "mean_probability": mean_probability, "observed_frequency": frequency,
            }
        )
        result.append(
            BacktestReliabilityBin(
                bin_row_id=f"historical-backtest-bin-{sha256_fingerprint((run_namespace, fingerprint))}",
                target_identity=target, probability_phase=phase,
                bin_index=index, lower_bound=lower, upper_bound=upper,
                sample_count=len(selected), mean_predicted_probability=mean_probability,
                observed_frequency=frequency, absolute_gap=gap,
                bin_fingerprint=fingerprint,
            )
        )
    return tuple(result)


def reproduce_predictive_metrics(predictions, bin_count=10):
    return calculate_predictive_metrics(predictions, bin_count)


def _probability(probabilities, target):
    return next(item.probability for item in probabilities.ordered_probabilities if item.target.value == target)


def _result_index(labels):
    return next(index for index, name in enumerate(("HOME_WIN", "DRAW", "AWAY_WIN")) if labels[name] == 1)


def _mean(values):
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else Decimal(0)


def _binary_log_loss(probability, outcome):
    with localcontext() as context:
        context.prec = 50
        return -(Decimal(outcome) * probability.ln() + Decimal(1 - outcome) * (Decimal(1) - probability).ln())


def _multiclass_log_loss(probabilities, outcome):
    with localcontext() as context:
        context.prec = 50
        return -probabilities[outcome].ln()


def _multiclass_brier(probabilities, outcome):
    return sum(
        ((probability - Decimal(int(index == outcome))) ** 2 for index, probability in enumerate(probabilities)),
        Decimal(0),
    ) / Decimal(3)


def _metric_rows(category, grouping, values, start, run_namespace):
    return tuple(
        BacktestMetric(
            metric_row_id=f"historical-backtest-metric-{sha256_fingerprint((run_namespace, category, grouping, name, value))}",
            category=category, grouping_identity=grouping, metric_name=name,
            metric_value=value, metric_snapshot=canonical_json({"value": value}),
            deterministic_order=start + index,
        )
        for index, (name, value) in enumerate(values.items())
    )


def _snapshot_row(category, grouping, name, snapshot, order, run_namespace):
    return BacktestMetric(
        metric_row_id=f"historical-backtest-metric-{sha256_fingerprint((run_namespace, category, grouping, name, snapshot))}",
        category=category, grouping_identity=grouping, metric_name=name,
        metric_value=None, metric_snapshot=canonical_json(snapshot), deterministic_order=order,
    )
