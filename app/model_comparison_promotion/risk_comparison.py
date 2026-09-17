"""Risk and bankroll-resilience comparison."""

from decimal import Decimal

from .betting_comparison import _aggregate
from .models import Direction
from .predictive_comparison import build_metric_evaluation


LOWER = (
    "maximum_absolute_drawdown",
    "maximum_percentage_drawdown",
    "bankroll_volatility",
    "return_variance",
    "return_standard_deviation",
    "longest_losing_streak",
    "maximum_consecutive_drawdown_duration",
)
HIGHER = ("minimum_bankroll", "peak_bankroll", "bankroll_recovery_ratio")


def compare_risk_metrics(champion_run, challenger_run, policy, start_order=0):
    champion = _aggregate(champion_run)
    challenger = _aggregate(challenger_run)
    for values, run in (
        (champion, champion_run),
        (challenger, challenger_run),
    ):
        peak = values.get("peak_bankroll", run.command.initial_bankroll)
        minimum = values.get("minimum_bankroll", run.command.initial_bankroll)
        denominator = peak - minimum
        values["bankroll_recovery_ratio"] = (
            (values.get("final_bankroll", run.final_bankroll) - minimum)
            / denominator
            if denominator > 0
            else Decimal(1)
        )
    result = []
    for name in LOWER + HIGHER:
        if name not in champion or name not in challenger:
            continue
        catastrophic = (
            policy.maximum_drawdown_degradation
            if name == "maximum_percentage_drawdown"
            else None
        )
        result.append(
            build_metric_evaluation(
                "RISK",
                "OVERALL",
                name,
                champion[name],
                challenger[name],
                Direction.LOWER_IS_BETTER if name in LOWER else Direction.HIGHER_IS_BETTER,
                start_order + len(result),
                policy.material_improvement,
                catastrophic,
            )
        )
    return tuple(result)
