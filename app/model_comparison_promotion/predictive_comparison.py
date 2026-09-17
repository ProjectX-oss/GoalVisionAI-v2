"""Normalized predictive comparisons with correct metric direction."""

from __future__ import annotations

from decimal import Decimal

from app.historical_backtesting import calculate_predictive_metrics

from .fingerprint import metric_comparison_fingerprint, sha256_fingerprint
from .models import (
    Direction,
    GateStatus,
    Materiality,
    MetricEvaluation,
)


LOWER_IS_BETTER = frozenset(
    {
        "binary_log_loss",
        "binary_brier_score",
        "multiclass_log_loss",
        "multiclass_brier_score",
        "macro_binary_log_loss",
        "macro_binary_brier_score",
        "weighted_binary_log_loss",
        "weighted_binary_brier_score",
    }
)


def compare_predictive_metrics(champion_run, challenger_run, policy):
    champion_rows, _, _ = calculate_predictive_metrics(champion_run.predictions)
    challenger_rows, _, _ = calculate_predictive_metrics(challenger_run.predictions)
    champion = _values(champion_rows)
    challenger = _values(challenger_rows)
    evaluations = []
    for key in sorted(set(champion) & set(challenger)):
        grouping, name = key
        if name not in LOWER_IS_BETTER | {"accuracy", "target_coverage", "sample_count", "probability_mean"}:
            continue
        direction = (
            Direction.LOWER_IS_BETTER
            if name in LOWER_IS_BETTER
            else Direction.HIGHER_IS_BETTER
        )
        catastrophic = (
            policy.catastrophic_predictive_degradation
            if name in LOWER_IS_BETTER
            else None
        )
        evaluations.append(
            build_metric_evaluation(
                "PREDICTIVE",
                grouping,
                name,
                champion[key],
                challenger[key],
                direction,
                len(evaluations),
                policy.material_improvement,
                catastrophic,
            )
        )
    champion_by_id = {
        item.training_example_id: item for item in champion_run.predictions
    }
    challenger_by_id = {
        item.training_example_id: item for item in challenger_run.predictions
    }
    shared = tuple(sorted(set(champion_by_id) & set(challenger_by_id)))
    if shared:
        targets = tuple(
            item.target.value
            for item in champion_by_id[shared[0]].calibrated_probabilities.ordered_probabilities
        )
        for target in targets:
            champion_accuracy, champion_frequency = _target_summary(
                tuple(champion_by_id[item] for item in shared), target
            )
            challenger_accuracy, challenger_frequency = _target_summary(
                tuple(challenger_by_id[item] for item in shared), target
            )
            for name, c_value, h_value in (
                ("binary_accuracy", champion_accuracy, challenger_accuracy),
                ("observed_frequency", champion_frequency, challenger_frequency),
            ):
                evaluations.append(
                    build_metric_evaluation(
                        "PREDICTIVE",
                        f"CALIBRATED:{target}",
                        name,
                        c_value,
                        h_value,
                        Direction.HIGHER_IS_BETTER,
                        len(evaluations),
                        policy.material_improvement,
                    )
                )
    return tuple(evaluations)


def build_metric_evaluation(
    category,
    group_identity,
    metric_name,
    champion_value,
    challenger_value,
    direction,
    order,
    material_threshold,
    catastrophic_threshold=None,
):
    if champion_value is None or challenger_value is None:
        delta = relative = None
        score = Decimal("0.5")
        materiality = Materiality.NO_MATERIAL_CHANGE
        gate = GateStatus.INSUFFICIENT
        reasons = ("METRIC_VALUE_MISSING",)
    else:
        delta = challenger_value - champion_value
        relative = delta / abs(champion_value) if champion_value != 0 else None
        improvement = -delta if direction is Direction.LOWER_IS_BETTER else delta
        denominator = max(abs(champion_value), Decimal("0.01"))
        normalized_improvement = improvement / denominator
        score = max(Decimal(0), min(Decimal(1), Decimal("0.5") + normalized_improvement))
        if improvement >= material_threshold:
            materiality = Materiality.MATERIAL_IMPROVEMENT
        elif improvement > 0:
            materiality = Materiality.SMALL_IMPROVEMENT
        elif improvement <= -material_threshold:
            materiality = Materiality.MATERIAL_DEGRADATION
        elif improvement < 0:
            materiality = Materiality.SMALL_DEGRADATION
        else:
            materiality = Materiality.NO_MATERIAL_CHANGE
        catastrophic = (
            catastrophic_threshold is not None
            and improvement < -catastrophic_threshold
        )
        gate = GateStatus.FAIL if catastrophic else GateStatus.PASS
        reasons = ("CATASTROPHIC_DEGRADATION",) if catastrophic else ()
    material = {
        "category": category,
        "group": group_identity,
        "metric": metric_name,
        "direction": direction,
        "champion": champion_value,
        "challenger": challenger_value,
        "delta": delta,
        "relative": relative,
        "score": score,
        "materiality": materiality,
        "gate": gate,
        "reasons": reasons,
    }
    fingerprint = metric_comparison_fingerprint(material)
    return MetricEvaluation(
        metric_evaluation_id=f"model-comparison-metric-{sha256_fingerprint((fingerprint, order))}",
        category=category,
        group_identity=group_identity,
        metric_name=metric_name,
        direction=direction,
        champion_value=champion_value,
        challenger_value=challenger_value,
        absolute_delta=delta,
        relative_delta=relative,
        normalized_score=score,
        materiality=materiality,
        gate_status=gate,
        reason_codes=reasons,
        metric_fingerprint=fingerprint,
        deterministic_order=order,
    )


def _values(rows):
    return {
        (item.grouping_identity, item.metric_name): item.metric_value
        for item in rows
        if item.metric_value is not None
    }


def _target_summary(predictions, target):
    correct = Decimal(0)
    observed = Decimal(0)
    for item in predictions:
        outcome = Decimal(dict(item.labels)[target])
        probability = next(
            value.probability
            for value in item.calibrated_probabilities.ordered_probabilities
            if value.target.value == target
        )
        correct += Decimal((probability >= Decimal(".5")) == bool(outcome))
        observed += outcome
    count = Decimal(len(predictions))
    return correct / count, observed / count
