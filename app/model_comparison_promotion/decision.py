"""Deterministic challenger recommendations and single-winner ranking."""

from .models import (
    GateStatus,
    Recommendation,
    UncertaintyClassification,
)


def recommend_challenger(gates, score, statistical_evidence, policy, *, scope_review=False):
    mandatory = tuple(item for item in gates if item.mandatory)
    reasons = tuple(
        reason
        for item in mandatory
        for reason in item.reason_codes
    )
    if any(item.status is GateStatus.INSUFFICIENT for item in mandatory):
        return Recommendation.INSUFFICIENT_EVIDENCE, reasons or ("INSUFFICIENT_EVIDENCE",)
    if scope_review or any(item.status is GateStatus.REVIEW for item in mandatory):
        return Recommendation.REVIEW_REQUIRED, reasons or ("REVIEW_REQUIRED",)
    if any(item.status is GateStatus.FAIL for item in mandatory):
        return Recommendation.REJECT_CHALLENGER, reasons or ("MANDATORY_GATE_FAILED",)
    material_improvement = any(
        item.evidence_name in ("BRIER_DELTA", "LOG_LOSS_DELTA", "ROI_DELTA")
        and item.effect_size is not None
        and item.effect_size > 0
        for item in statistical_evidence
    )
    if score >= policy.minimum_promotion_score and material_improvement:
        return Recommendation.PROMOTE_CHALLENGER, ("PROMOTION_POLICY_SATISFIED",)
    return Recommendation.KEEP_CHAMPION, ("PROMOTION_THRESHOLD_NOT_MET",)


def rank_challengers(evaluations):
    strength = {
        UncertaintyClassification.STRONG_EVIDENCE: 4,
        UncertaintyClassification.MODERATE_EVIDENCE: 3,
        UncertaintyClassification.WEAK_EVIDENCE: 2,
        UncertaintyClassification.INCONCLUSIVE: 1,
    }

    def evidence(item):
        return max(
            (strength[row.uncertainty_classification] for row in item.statistical_evidence),
            default=0,
        )

    def metric(item, category):
        values = [
            row.normalized_score
            for row in item.metric_evaluations
            if row.category == category
        ]
        return sum(values) / len(values) if values else 0

    def drawdown(item):
        values = [
            row.challenger_value
            for row in item.metric_evaluations
            if row.category == "RISK"
            and row.metric_name == "maximum_percentage_drawdown"
            and row.challenger_value is not None
        ]
        return values[0] if values else 1

    return tuple(
        sorted(
            evaluations,
            key=lambda item: (
                -item.promotion_score,
                -evidence(item),
                drawdown(item),
                -metric(item, "CALIBRATION"),
                -metric(item, "PREDICTIVE"),
                -metric(item, "BETTING"),
                item.candidate.challenger_candidate_id,
            ),
        )
    )
