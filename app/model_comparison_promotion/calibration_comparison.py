"""Calibration quality comparison from TEST reliability evidence."""

from decimal import Decimal

from app.historical_backtesting import calculate_predictive_metrics
from app.historical_backtesting.betting_metrics import calculate_betting_metrics

from .models import Direction
from .predictive_comparison import build_metric_evaluation


def compare_calibration_metrics(champion_run, challenger_run, policy, start_order=0):
    champion_rows, champion_bins, champion_aggregate = calculate_predictive_metrics(
        champion_run.predictions
    )
    challenger_rows, challenger_bins, challenger_aggregate = calculate_predictive_metrics(
        challenger_run.predictions
    )
    champion = {
        (row.grouping_identity, row.metric_name): row.metric_value
        for row in champion_rows
        if row.metric_value is not None
    }
    challenger = {
        (row.grouping_identity, row.metric_name): row.metric_value
        for row in challenger_rows
        if row.metric_value is not None
    }
    evaluations = []
    names = {
        "expected_calibration_error",
        "maximum_calibration_error",
    }
    for key in sorted(set(champion) & set(challenger)):
        if key[1] not in names or not key[0].startswith("CALIBRATED:"):
            continue
        evaluations.append(
            build_metric_evaluation(
                "CALIBRATION",
                key[0],
                key[1],
                champion[key],
                challenger[key],
                Direction.LOWER_IS_BETTER,
                start_order + len(evaluations),
                policy.material_improvement,
                policy.catastrophic_calibration_degradation,
            )
        )
    for name in ("calibration_brier_improvement", "calibration_log_loss_improvement"):
        c = dict(champion_aggregate).get(name)
        h = dict(challenger_aggregate).get(name)
        evaluations.append(
            build_metric_evaluation(
                "CALIBRATION",
                "OVERALL",
                name,
                c,
                h,
                Direction.HIGHER_IS_BETTER,
                start_order + len(evaluations),
                policy.material_improvement,
            )
        )
    champion_betting = dict(
        calculate_betting_metrics(
            champion_run.predictions,
            champion_run.assessments,
            champion_run.selections,
            champion_run.settlements,
            champion_run.ledger,
            champion_run.command.initial_bankroll,
        )[1]
    )
    challenger_betting = dict(
        calculate_betting_metrics(
            challenger_run.predictions,
            challenger_run.assessments,
            challenger_run.selections,
            challenger_run.settlements,
            challenger_run.ledger,
            challenger_run.command.initial_bankroll,
        )[1]
    )
    for name in (
        "selected_bet_calibration_error",
        "selected_bet_brier_score",
    ):
        evaluations.append(
            build_metric_evaluation(
                "CALIBRATION",
                "SELECTED_BETS",
                name,
                champion_betting.get(name),
                challenger_betting.get(name),
                Direction.LOWER_IS_BETTER,
                start_order + len(evaluations),
                policy.material_improvement,
                policy.catastrophic_calibration_degradation,
            )
        )
    champion_adjustment, champion_extreme = _adjustment_evidence(
        champion_run.predictions
    )
    challenger_adjustment, challenger_extreme = _adjustment_evidence(
        challenger_run.predictions
    )
    for name, champion_value, challenger_value in (
        (
            "mean_calibration_adjustment_magnitude",
            champion_adjustment,
            challenger_adjustment,
        ),
        (
            "extreme_calibrated_probability_count",
            champion_extreme,
            challenger_extreme,
        ),
    ):
        evaluations.append(
            build_metric_evaluation(
                "CALIBRATION",
                "OVERALL",
                name,
                champion_value,
                challenger_value,
                Direction.LOWER_IS_BETTER,
                start_order + len(evaluations),
                policy.material_improvement,
            )
        )
    champion_bias = _confidence_bias(champion_run.predictions)
    challenger_bias = _confidence_bias(challenger_run.predictions)
    for name in ("overconfidence_magnitude", "underconfidence_magnitude"):
        evaluations.append(
            build_metric_evaluation(
                "CALIBRATION",
                "OVERALL",
                name,
                champion_bias[name],
                challenger_bias[name],
                Direction.LOWER_IS_BETTER,
                start_order + len(evaluations),
                policy.material_improvement,
                policy.catastrophic_calibration_degradation,
            )
        )
    champion_sparse = Decimal(sum(item.sample_count < policy.minimum_group_sample_size for item in champion_bins))
    challenger_sparse = Decimal(sum(item.sample_count < policy.minimum_group_sample_size for item in challenger_bins))
    evaluations.append(
        build_metric_evaluation(
            "CALIBRATION",
            "OVERALL",
            "sparse_reliability_bins",
            champion_sparse,
            challenger_sparse,
            Direction.LOWER_IS_BETTER,
            start_order + len(evaluations),
            Decimal(1),
        )
    )
    return tuple(evaluations)


def _adjustment_evidence(predictions):
    adjustments = []
    extremes = 0
    for prediction in predictions:
        raw = {
            item.target.value: item.probability
            for item in prediction.raw_probabilities.ordered_probabilities
        }
        for item in prediction.calibrated_probabilities.ordered_probabilities:
            adjustments.append(abs(item.probability - raw[item.target.value]))
            extremes += item.probability <= Decimal(".01") or item.probability >= Decimal(".99")
    return (
        sum(adjustments, Decimal(0)) / Decimal(len(adjustments))
        if adjustments
        else Decimal(0),
        Decimal(extremes),
    )


def _confidence_bias(predictions):
    over = under = Decimal(0)
    count = Decimal(0)
    for prediction in predictions:
        labels = dict(prediction.labels)
        for item in prediction.calibrated_probabilities.ordered_probabilities:
            delta = item.probability - Decimal(labels[item.target.value])
            over += max(delta, Decimal(0))
            under += max(-delta, Decimal(0))
            count += 1
    return {
        "overconfidence_magnitude": over / count if count else Decimal(0),
        "underconfidence_magnitude": under / count if count else Decimal(0),
    }
