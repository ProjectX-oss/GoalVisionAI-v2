"""Deterministic activation evidence derived from immutable settled shadow rows."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .exceptions import ActivationNotEligibleError
from .fingerprint import sha256_fingerprint
from .models import ActivationEvidence


def build_activation_evidence(request, shadow_repository) -> ActivationEvidence:
    executions = tuple(
        item for item in shadow_repository.list_executions_for_model_pair(
            request.current_champion.model_artifact_id,
            request.challenger.model_artifact_id,
        )
        if _time(item.command.evaluation_timestamp_utc) <= _time(request.evidence_cutoff_timestamp_utc)
    )
    settled_pairs = tuple(
        (item, shadow_repository.find_settlement_for_execution(item.shadow_execution_id))
        for item in executions
    )
    cutoff = _time(request.evidence_cutoff_timestamp_utc)
    settled_pairs = tuple(
        (execution, settlement) for execution, settlement in settled_pairs
        if settlement is not None and _time(settlement.settlement_timestamp_utc) <= cutoff
    )
    if not settled_pairs:
        raise ActivationNotEligibleError("No settled shadow evidence exists for the exact model pair.")
    for execution, _ in settled_pairs:
        if (
            execution.command.champion_model_artifact_fingerprint != request.current_champion.model_artifact_fingerprint
            or execution.command.challenger_model_artifact_fingerprint != request.challenger.model_artifact_fingerprint
            or execution.command.champion_calibration_artifact_set_fingerprint != request.current_champion.calibration_artifact_set_fingerprint
            or execution.command.challenger_calibration_artifact_set_fingerprint != request.challenger.calibration_artifact_set_fingerprint
            or execution.command.comparison_run_id != request.comparison_run_id
            or execution.command.comparison_run_fingerprint != request.comparison_run_fingerprint
            or execution.command.challenger_candidate_id != request.challenger_candidate_id
            or execution.command.recommendation_id != request.recommendation_id
            or execution.command.recommendation_fingerprint != request.recommendation_fingerprint
        ):
            raise ActivationNotEligibleError("Shadow evidence provenance differs from the activation request.")
    ordered = sorted(settled_pairs, key=lambda pair: (_time(pair[0].command.evaluation_timestamp_utc), pair[0].shadow_execution_id))
    first = _time(ordered[0][0].command.evaluation_timestamp_utc)
    last = _time(ordered[-1][0].command.evaluation_timestamp_utc)
    count = len(ordered)
    agreement = sum(
        item.comparison.disagreement_type.value in ("EXACT_AGREEMENT", "BOTH_NO_SELECTION")
        for item, _ in ordered
    )
    critical = sum(item.comparison.severity.value == "CRITICAL" for item, _ in ordered)
    champion_brier, challenger_brier = _brier_pair(ordered)
    champion_calibration, challenger_calibration = _calibration_pair(ordered)
    champion_profit = sum((settlement.champion_profit_per_unit for _, settlement in ordered), Decimal(0)) / Decimal(count)
    challenger_profit = sum((settlement.challenger_profit_per_unit for _, settlement in ordered), Decimal(0)) / Decimal(count)
    champion_drawdown = _maximum_drawdown(tuple(settlement.champion_profit_per_unit for _, settlement in ordered))
    challenger_drawdown = _maximum_drawdown(tuple(settlement.challenger_profit_per_unit for _, settlement in ordered))
    completeness = sum((item.input_snapshot.completeness_score for item, _ in ordered), Decimal(0)) / Decimal(count)
    core = {
        "executions": tuple(item.execution_fingerprint for item, _ in ordered),
        "settlements": tuple(item.settlement_fingerprint for _, item in ordered),
        "count": count, "first": first, "last": last, "agreement": agreement,
        "critical": critical, "champion_brier": champion_brier,
        "challenger_brier": challenger_brier, "champion_calibration": champion_calibration,
        "challenger_calibration": challenger_calibration,
        "champion_profit": champion_profit, "challenger_profit": challenger_profit,
        "champion_drawdown": champion_drawdown, "challenger_drawdown": challenger_drawdown,
        "completeness": completeness,
    }
    fingerprint = sha256_fingerprint(core)
    return ActivationEvidence(
        settled_count=count,
        observation_days=Decimal(str((last - first).total_seconds())) / Decimal(86400),
        agreement_ratio=Decimal(agreement) / Decimal(count),
        critical_disagreement_ratio=Decimal(critical) / Decimal(count),
        predictive_degradation=challenger_brier - champion_brier,
        calibration_degradation=challenger_calibration - champion_calibration,
        betting_performance_degradation=champion_profit - challenger_profit,
        drawdown_deterioration=challenger_drawdown - champion_drawdown,
        evidence_completeness=completeness,
        shadow_execution_ids=tuple(item.shadow_execution_id for item, _ in ordered),
        shadow_execution_fingerprints=tuple(item.execution_fingerprint for item, _ in ordered),
        shadow_settlement_fingerprints=tuple(item.settlement_fingerprint for _, item in ordered),
        evidence_fingerprint=fingerprint,
    )


def _brier_pair(rows):
    champion = challenger = Decimal(0)
    observations = 0
    for execution, settlement in rows:
        labels = _labels(settlement.final_home_score, settlement.final_away_score)
        for inference, destination in zip(execution.inferences, ("champion", "challenger")):
            value = sum(
                (item.probability - Decimal(labels[item.target.value])) ** 2
                for item in inference.calibrated_probabilities.ordered_probabilities
            )
            if destination == "champion": champion += value
            else: challenger += value
        observations += len(labels)
    return champion / Decimal(observations), challenger / Decimal(observations)


def _calibration_pair(rows):
    sums = {"champion": Decimal(0), "challenger": Decimal(0)}
    labels_total = {}
    probability_total = {"champion": {}, "challenger": {}}
    for execution, settlement in rows:
        labels = _labels(settlement.final_home_score, settlement.final_away_score)
        for name, value in labels.items(): labels_total[name] = labels_total.get(name, 0) + value
        for inference, role in zip(execution.inferences, ("champion", "challenger")):
            for item in inference.calibrated_probabilities.ordered_probabilities:
                probability_total[role][item.target.value] = probability_total[role].get(item.target.value, Decimal(0)) + item.probability
    count = Decimal(len(rows))
    for role in sums:
        sums[role] = sum(
            abs(probability_total[role][name] / count - Decimal(labels_total[name]) / count)
            for name in labels_total
        ) / Decimal(len(labels_total))
    return sums["champion"], sums["challenger"]


def _labels(home, away):
    total = home + away
    return {
        "HOME_WIN": int(home > away), "DRAW": int(home == away), "AWAY_WIN": int(away > home),
        "OVER_1_5": int(total > 1.5), "UNDER_1_5": int(total < 1.5),
        "OVER_2_5": int(total > 2.5), "UNDER_2_5": int(total < 2.5),
        "OVER_3_5": int(total > 3.5), "UNDER_3_5": int(total < 3.5),
        "BTTS_YES": int(home > 0 and away > 0), "BTTS_NO": int(home == 0 or away == 0),
    }


def _maximum_drawdown(profits):
    balance = peak = Decimal(0)
    maximum = Decimal(0)
    for profit in profits:
        balance += profit
        peak = max(peak, balance)
        maximum = max(maximum, peak - balance)
    return maximum / Decimal(max(1, len(profits)))


def _time(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
