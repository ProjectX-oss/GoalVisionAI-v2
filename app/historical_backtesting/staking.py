"""Deterministic 1%/2%/3% Official stake recommendations and batch exposure."""

from __future__ import annotations

from decimal import Decimal

from .fingerprint import sha256_fingerprint
from .models import BacktestSelection
from .selection import selection_fingerprint


def create_group_selections(predictions, assessments, winners, bankroll, policy, start_order=0, *, run_namespace=""):
    prediction_by_row = {item.prediction_row_id: item for item in predictions}
    by_prediction = {}
    for item in assessments:
        by_prediction.setdefault(item.prediction_row_id, []).append(item)
    result = []
    applied_total = Decimal(0)
    exposure_limit = (bankroll * policy.maximum_equal_kickoff_exposure).quantize(
        policy.currency_quantum, rounding=policy.rounding
    )
    for winner in sorted(winners, key=lambda item: (
        prediction_by_row[item.prediction_row_id].competition,
        item.historical_match_id,
        prediction_by_row[item.prediction_row_id].training_example_id,
    )):
        prediction = prediction_by_row[winner.prediction_row_id]
        percentage, classification = _stake_band(
            winner.expected_value, winner.calibrated_probability, policy
        )
        recommended = (bankroll * percentage).quantize(policy.currency_quantum, rounding=policy.rounding)
        remaining_exposure = max(Decimal(0), exposure_limit - applied_total)
        remaining_bankroll = max(Decimal(0), bankroll - applied_total)
        applied = min(recommended, remaining_exposure, remaining_bankroll)
        reduction = None if applied == recommended else "EQUAL_KICKOFF_EXPOSURE_LIMIT"
        rejection = None if applied > 0 else "EXPOSURE_LIMIT"
        selected_fp = selection_fingerprint(by_prediction[winner.prediction_row_id], winner, policy)
        stake_fp = sha256_fingerprint(
            {
                "selection_fingerprint": selected_fp, "bankroll_snapshot": bankroll,
                "risk_inputs": {
                    "expected_value": winner.expected_value,
                    "probability": winner.calibrated_probability,
                    "group_applied_before": applied_total,
                    "group_exposure_limit": exposure_limit,
                },
                "stake_percentage": percentage, "recommended": recommended,
                "applied": applied, "reduction_reason": reduction,
                "rejection_reason": rejection,
                "policy_version": policy.staking_policy_version,
            }
        )
        group_id = f"historical-backtest-kickoff-group-{sha256_fingerprint((run_namespace, prediction.kickoff_utc))}"
        selection_id = f"historical-backtest-selection-{sha256_fingerprint((run_namespace, selected_fp, stake_fp))}"
        result.append(
            BacktestSelection(
                selection_id=selection_id, historical_match_id=prediction.historical_match_id,
                kickoff_utc=prediction.kickoff_utc, kickoff_group_id=group_id,
                selected_assessment_id=winner.assessment_id,
                market_identity=winner.market_identity, decimal_odds=winner.decimal_odds,
                calibrated_probability=winner.calibrated_probability,
                expected_value=winner.expected_value, bankroll_snapshot=bankroll,
                stake_percentage=percentage, recommended_stake_amount=recommended,
                applied_stake_amount=applied, stake_classification=classification,
                reduction_reason=reduction, rejection_reason=rejection,
                selection_fingerprint=selected_fp, stake_fingerprint=stake_fp,
                deterministic_order=start_order + len(result),
            )
        )
        applied_total += applied
    return tuple(result)


def _stake_band(ev, probability, policy):
    if ev >= policy.exceptional_expected_value and probability >= Decimal("0.80"):
        return policy.maximum_stake_percentage, "MAXIMUM"
    if ev >= policy.strong_expected_value and probability >= Decimal("0.70"):
        return policy.standard_stake_percentage, "STANDARD"
    return policy.conservative_stake_percentage, "CONSERVATIVE"
