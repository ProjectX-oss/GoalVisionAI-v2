"""Descriptive pre-match and post-settlement evidence metrics."""

from decimal import Decimal

from .fingerprint import canonical_json, sha256_fingerprint
from .models import ShadowAggregateSnapshot, ShadowMetric


def pre_match_metrics(execution_id, inferences, selections, comparison):
    rows = []
    for inference in inferences:
        for item in inference.calibrated_probabilities.ordered_probabilities:
            rows.append(_metric(execution_id, "PRE_MATCH", inference.model_role, "PROBABILITY", item.target.value, "CALIBRATED_PROBABILITY", item.probability, len(rows)))
    for selection in selections:
        rows.append(_metric(execution_id, "PRE_MATCH", selection.model_role, "DECISION", "OVERALL", "SELECTION_MADE", Decimal(selection.market_identity is not None), len(rows)))
        rows.append(_metric(execution_id, "PRE_MATCH", selection.model_role, "VALUE", selection.market_identity or "NO_SELECTION", "EXPECTED_VALUE", selection.expected_value, len(rows)))
    rows.append(_metric(execution_id, "PRE_MATCH", None, "DISAGREEMENT", comparison.disagreement_type.value, "MAX_PROBABILITY_DELTA", comparison.maximum_probability_delta, len(rows)))
    return tuple(rows)


def settlement_metrics(execution_id, settlement):
    return tuple(
        _metric(execution_id, "POST_SETTLEMENT", role, "OUTCOME", "OVERALL", name, value, order)
        for order, (role, name, value) in enumerate((
            (None, "SELECTION_AGREEMENT", Decimal(settlement.champion_outcome == settlement.challenger_outcome)),
            (None, "CHALLENGER_PROFIT_IMPROVEMENT", settlement.challenger_profit_per_unit - settlement.champion_profit_per_unit),
        ))
    )


def aggregate_snapshot(executions, settlements, category, identity, *, namespace=""):
    relevant = tuple(executions)
    settled = tuple(settlements)
    profits_champion = sum((item.champion_profit_per_unit for item in settled), Decimal(0))
    profits_challenger = sum((item.challenger_profit_per_unit for item in settled), Decimal(0))
    snapshot = canonical_json({
        "execution_count": len(relevant), "settled_count": len(settled),
        "champion_profit_per_unit": profits_champion,
        "challenger_profit_per_unit": profits_challenger,
        "challenger_profit_improvement": profits_challenger - profits_champion,
    })
    fingerprint = sha256_fingerprint((namespace, category, identity, snapshot))
    return ShadowAggregateSnapshot(
        aggregate_snapshot_id=f"shadow-aggregate-{fingerprint}", grouping_category=category,
        grouping_identity=identity, sample_count=len(relevant), settled_count=len(settled),
        metric_snapshot=snapshot, aggregate_fingerprint=fingerprint,
    )


def _metric(execution_id, phase, role, category, group, name, value, order):
    snapshot = canonical_json({"value": value})
    fingerprint = sha256_fingerprint((execution_id, phase, role, category, group, name, snapshot))
    return ShadowMetric(
        metric_id=f"shadow-metric-{fingerprint}", phase=phase, model_role=role,
        category=category, grouping_identity=group, metric_name=name, metric_value=value,
        metric_snapshot=snapshot, metric_fingerprint=fingerprint,
    )
