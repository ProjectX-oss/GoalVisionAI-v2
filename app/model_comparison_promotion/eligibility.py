"""Evidence sufficiency and mandatory fail-closed promotion gates."""

from __future__ import annotations

from .fingerprint import canonical_json, sha256_fingerprint
from .models import GateEvaluation, GateStatus


def evaluate_eligibility_gates(
    *,
    shared_prediction_count,
    shared_selected_bet_count,
    metric_evaluations,
    stability_groups,
    challenger_run,
    scope,
    policy,
    source_compatible=True,
    scope_review=False,
):
    by_metric = {
        (item.category, item.metric_name): item for item in metric_evaluations
        if item.group_identity == "OVERALL"
    }
    gates = []

    def add(category, name, status, mandatory=True, champion=None, challenger=None, threshold=None, reasons=()):
        order = len(gates)
        gates.append(
            GateEvaluation(
                gate_evaluation_id=f"model-comparison-gate-{sha256_fingerprint((category, name, status, order, champion, challenger, threshold))}",
                gate_category=category,
                gate_name=name,
                mandatory=mandatory,
                status=status,
                champion_value_snapshot=canonical_json(champion),
                challenger_value_snapshot=canonical_json(challenger),
                threshold_snapshot=canonical_json(threshold),
                reason_codes=tuple(reasons),
                deterministic_order=order,
            )
        )

    add("SOURCE", "SOURCE_INTEGRITY", GateStatus.PASS if source_compatible else GateStatus.FAIL, reasons=() if source_compatible else ("SOURCE_INTEGRITY_FAILED",))
    add("SCOPE", "FAIR_SCOPE", GateStatus.REVIEW if scope_review else GateStatus.PASS, reasons=("SCOPE_REVIEW_REQUIRED",) if scope_review else ())
    add(
        "EVIDENCE", "MINIMUM_SHARED_PREDICTIONS",
        GateStatus.PASS if shared_prediction_count >= scope.required_minimum_shared_sample_size else GateStatus.INSUFFICIENT,
        challenger=shared_prediction_count, threshold=scope.required_minimum_shared_sample_size,
        reasons=() if shared_prediction_count >= scope.required_minimum_shared_sample_size else ("INSUFFICIENT_SHARED_PREDICTIONS",),
    )
    add(
        "EVIDENCE", "MINIMUM_SELECTED_BETS",
        GateStatus.PASS if shared_selected_bet_count >= scope.required_minimum_selected_bet_count else GateStatus.INSUFFICIENT,
        challenger=shared_selected_bet_count, threshold=scope.required_minimum_selected_bet_count,
        reasons=() if shared_selected_bet_count >= scope.required_minimum_selected_bet_count else ("INSUFFICIENT_SELECTED_BETS",),
    )
    wins = sum(item.net_profit_loss > 0 for item in challenger_run.settlements)
    losses = sum(item.net_profit_loss < 0 for item in challenger_run.settlements)
    diverse = wins > 0 and losses > 0
    add(
        "EVIDENCE",
        "OUTCOME_DIVERSITY",
        GateStatus.PASS if diverse else GateStatus.INSUFFICIENT,
        challenger={"wins": wins, "losses": losses},
        threshold={"minimum_distinct_terminal_outcomes": 2},
        reasons=() if diverse else ("INSUFFICIENT_OUTCOME_DIVERSITY",),
    )
    prediction_competitions = {
        item.competition for item in challenger_run.predictions
    }
    prediction_seasons = {item.season for item in challenger_run.predictions}
    selected_markets = {
        item.market_identity.value for item in challenger_run.selections
    }
    coverage_missing = {
        "competitions": sorted(
            set(scope.required_competitions) - prediction_competitions
        ),
        "seasons": sorted(set(scope.required_seasons) - prediction_seasons),
        "markets": sorted(set(scope.required_markets) - selected_markets),
    }
    coverage_pass = not any(coverage_missing.values())
    add(
        "SCOPE",
        "REQUIRED_COVERAGE",
        GateStatus.PASS if coverage_pass else GateStatus.INSUFFICIENT,
        challenger=coverage_missing,
        threshold={
            "competitions": scope.required_competitions,
            "seasons": scope.required_seasons,
            "markets": scope.required_markets,
        },
        reasons=() if coverage_pass else ("INSUFFICIENT_REQUIRED_COVERAGE",),
    )
    predictive_bad = any(
        item.category == "PREDICTIVE" and item.gate_status is GateStatus.FAIL
        for item in metric_evaluations
    )
    calibration_bad = any(
        item.category == "CALIBRATION" and item.gate_status is GateStatus.FAIL
        for item in metric_evaluations
    )
    add("PREDICTIVE", "NO_CATASTROPHIC_DEGRADATION", GateStatus.FAIL if predictive_bad else GateStatus.PASS, reasons=("CATASTROPHIC_PREDICTIVE_DEGRADATION",) if predictive_bad else ())
    add("CALIBRATION", "NO_CATASTROPHIC_DEGRADATION", GateStatus.FAIL if calibration_bad else GateStatus.PASS, reasons=("CATASTROPHIC_CALIBRATION_DEGRADATION",) if calibration_bad else ())
    betting_values = dict(challenger_run.aggregate_betting_metrics)
    roi = betting_values.get("roi")
    yield_value = betting_values.get("yield")
    net = betting_values.get("net_profit")
    betting_pass = (
        roi is not None and roi >= policy.minimum_roi
        and yield_value is not None and yield_value >= policy.minimum_yield
        and net is not None and net >= policy.minimum_net_profit
    )
    add("BETTING", "PERFORMANCE_FLOOR", GateStatus.PASS if betting_pass else GateStatus.FAIL, challenger={"roi": roi, "yield": yield_value, "net_profit": net}, threshold={"roi": policy.minimum_roi, "yield": policy.minimum_yield, "net_profit": policy.minimum_net_profit}, reasons=() if betting_pass else ("BETTING_PERFORMANCE_FLOOR_FAILED",))
    minimum_bankroll = betting_values.get("minimum_bankroll", challenger_run.final_bankroll)
    drawdown = betting_values.get("maximum_percentage_drawdown")
    solvent = minimum_bankroll > challenger_run.command.initial_bankroll * policy.insolvency_floor_ratio
    risk_pass = solvent and drawdown is not None and drawdown <= policy.maximum_drawdown_percentage
    add("RISK", "BANKROLL_AND_DRAWDOWN", GateStatus.PASS if risk_pass else GateStatus.FAIL, challenger={"minimum_bankroll": minimum_bankroll, "drawdown": drawdown}, threshold={"insolvency_floor_ratio": policy.insolvency_floor_ratio, "maximum_drawdown": policy.maximum_drawdown_percentage}, reasons=() if risk_pass else ("RISK_LIMIT_FAILED",))
    volatility = next(
        (
            item
            for item in metric_evaluations
            if item.category == "RISK"
            and item.metric_name == "bankroll_volatility"
        ),
        None,
    )
    roi_evaluation = next(
        (
            item
            for item in metric_evaluations
            if item.category == "BETTING" and item.metric_name == "roi"
        ),
        None,
    )
    uncompensated = bool(
        volatility
        and volatility.relative_delta is not None
        and volatility.relative_delta > policy.maximum_volatility_degradation
        and (
            roi_evaluation is None
            or roi_evaluation.absolute_delta is None
            or roi_evaluation.absolute_delta <= 0
        )
    )
    add(
        "RISK",
        "VOLATILITY_RETURN_COMPENSATION",
        GateStatus.REVIEW if uncompensated else GateStatus.PASS,
        challenger=volatility.relative_delta if volatility else None,
        threshold=policy.maximum_volatility_degradation,
        reasons=("UNCOMPENSATED_VOLATILITY_DEGRADATION",)
        if uncompensated
        else (),
    )
    comparable_categories = {
        "COMPETITION",
        "SEASON",
        "CALENDAR_MONTH",
    }
    severe = sum(
        item.stability_status.value == "SEVERELY_DEGRADED"
        and item.group_category in comparable_categories
        for item in stability_groups
    )
    add("STABILITY", "SEVERE_DEGRADATION_LIMIT", GateStatus.PASS if severe <= policy.maximum_severe_stability_groups else GateStatus.FAIL, challenger=severe, threshold=policy.maximum_severe_stability_groups, reasons=() if severe <= policy.maximum_severe_stability_groups else ("STABILITY_COLLAPSE",))
    from .stability import summarize_stability

    stability_summary = summarize_stability(stability_groups)
    concentration = stability_summary["maximum_profit_concentration"]
    add(
        "RISK",
        "MAXIMUM_PROFIT_CONCENTRATION",
        GateStatus.PASS
        if concentration <= policy.maximum_profit_concentration
        else GateStatus.REVIEW,
        challenger=concentration,
        threshold=policy.maximum_profit_concentration,
        reasons=()
        if concentration <= policy.maximum_profit_concentration
        else ("EXCESSIVE_PROFIT_CONCENTRATION",),
    )
    if policy.require_clv:
        clv_available = betting_values.get("clv_available_count", 0) > 0
        add("BETTING", "CLV_EVIDENCE", GateStatus.PASS if clv_available else GateStatus.INSUFFICIENT, mandatory=True, reasons=() if clv_available else ("CLV_REQUIRED_BUT_UNAVAILABLE",))
    return tuple(gates)
