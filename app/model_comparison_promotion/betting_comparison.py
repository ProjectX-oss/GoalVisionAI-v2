"""Stake- and sample-aware betting performance comparisons."""

from dataclasses import replace
from decimal import Decimal

from app.historical_backtesting import calculate_betting_metrics

from .fingerprint import metric_comparison_fingerprint
from .models import Direction, Materiality
from .predictive_comparison import build_metric_evaluation


LOWER = frozenset(
    {
        "losses",
        "voids",
        "expected_realized_difference",
        "selected_bet_brier_score",
        "selected_bet_calibration_error",
    }
)
HIGHER = frozenset(
    {
        "selected_bets",
        "wins",
        "strike_rate",
        "total_stake",
        "gross_return",
        "net_profit",
        "roi",
        "yield",
        "average_odds",
        "median_odds",
        "average_calibrated_probability",
        "average_expected_value",
        "expected_profit",
        "realized_profit",
        "realized_return_per_bet",
        "final_bankroll",
        "bankroll_growth_percentage",
        "clv_available_count",
        "clv_positive_count",
        "clv_average",
        "clv_median",
    }
)
INFORMATIONAL = frozenset(
    {
        "selected_bets",
        "wins",
        "losses",
        "voids",
        "total_stake",
        "gross_return",
        "net_profit",
        "average_odds",
        "median_odds",
        "final_bankroll",
        "clv_available_count",
    }
)


def compare_betting_metrics(champion_run, challenger_run, policy, start_order=0):
    champion = _aggregate(champion_run)
    challenger = _aggregate(challenger_run)
    evaluations = []
    for name in sorted((LOWER | HIGHER) & set(champion) & set(challenger)):
        champion_value = champion[name]
        challenger_value = challenger[name]
        if name == "expected_realized_difference":
            champion_value = abs(champion_value)
            challenger_value = abs(challenger_value)
        evaluation = build_metric_evaluation(
                "BETTING",
                "OVERALL",
                name,
                champion_value,
                challenger_value,
                Direction.LOWER_IS_BETTER if name in LOWER else Direction.HIGHER_IS_BETTER,
                start_order + len(evaluations),
                policy.material_improvement,
            )
        if name in INFORMATIONAL:
            reasons = evaluation.reason_codes + ("INFORMATIONAL_NOT_SCORED",)
            fingerprint = metric_comparison_fingerprint(
                {
                    "category": evaluation.category,
                    "group": evaluation.group_identity,
                    "metric": evaluation.metric_name,
                    "direction": evaluation.direction,
                    "champion": evaluation.champion_value,
                    "challenger": evaluation.challenger_value,
                    "delta": evaluation.absolute_delta,
                    "relative": evaluation.relative_delta,
                    "score": Decimal("0.5"),
                    "materiality": Materiality.NO_MATERIAL_CHANGE,
                    "gate": evaluation.gate_status,
                    "reasons": reasons,
                }
            )
            evaluation = replace(
                evaluation,
                normalized_score=Decimal("0.5"),
                materiality=Materiality.NO_MATERIAL_CHANGE,
                reason_codes=reasons,
                metric_fingerprint=fingerprint,
            )
        evaluations.append(evaluation)
    return tuple(evaluations)


def _aggregate(run):
    _, aggregate = calculate_betting_metrics(
        run.predictions,
        run.assessments,
        run.selections,
        run.settlements,
        run.ledger,
        run.command.initial_bankroll,
        tuple(item for item in run.odds_snapshots if item.closing),
    )
    return dict(aggregate)
