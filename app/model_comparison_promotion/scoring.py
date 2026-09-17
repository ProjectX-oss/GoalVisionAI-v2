"""Central bounded weighted promotion score."""

from __future__ import annotations

from decimal import Decimal

from .fingerprint import canonical_json, sha256_fingerprint
from .models import GateStatus, ScoreComponent, StabilityStatus
from .stability import summarize_stability


def calculate_promotion_score(metric_evaluations, stability_groups, gates, statistical_evidence, policy):
    category_scores = {}
    for category in ("PREDICTIVE", "CALIBRATION", "BETTING", "RISK"):
        values = tuple(
            item.normalized_score
            for item in metric_evaluations
            if item.category == category
            and item.gate_status is not GateStatus.INSUFFICIENT
        )
        category_scores[category] = _mean(values, default=Decimal("0.5"))
    summary = summarize_stability(stability_groups)
    category_scores["STABILITY"] = max(
        Decimal(0),
        min(
            Decimal(1),
            (
                summary["temporal_consistency_score"]
                + summary["cross_market_consistency_score"]
                + summary["cross_competition_consistency_score"]
            )
            / Decimal(3),
        ),
    )
    classifications = {
        "STRONG_EVIDENCE": Decimal(1),
        "MODERATE_EVIDENCE": Decimal("0.75"),
        "WEAK_EVIDENCE": Decimal("0.5"),
        "INCONCLUSIVE": Decimal(0),
    }
    category_scores["EVIDENCE"] = _mean(
        tuple(classifications[item.uncertainty_classification.value] for item in statistical_evidence),
        default=Decimal(0),
    )
    gate_by_category = {}
    for category, _ in policy.weights:
        relevant = tuple(item for item in gates if item.gate_category == category and item.mandatory)
        if any(item.status is GateStatus.FAIL for item in relevant):
            gate_by_category[category] = GateStatus.FAIL
        elif any(item.status is GateStatus.INSUFFICIENT for item in relevant):
            gate_by_category[category] = GateStatus.INSUFFICIENT
        elif any(item.status is GateStatus.REVIEW for item in relevant):
            gate_by_category[category] = GateStatus.REVIEW
        else:
            gate_by_category[category] = GateStatus.PASS
    components = []
    for category, weight in policy.weights:
        normalized = max(Decimal(0), min(Decimal(1), category_scores[category]))
        contribution = normalized * weight
        material = {
            "category": category,
            "raw": category_scores[category],
            "normalized": normalized,
            "weight": weight,
            "contribution": contribution,
            "gate": gate_by_category[category],
        }
        components.append(
            ScoreComponent(
                score_component_id=f"model-comparison-score-{sha256_fingerprint((material, len(components)))}",
                score_category=category,
                raw_score=category_scores[category],
                normalized_score=normalized,
                weight=weight,
                weighted_contribution=contribution,
                gate_status=gate_by_category[category],
                detail_snapshot=canonical_json(material),
                deterministic_order=len(components),
            )
        )
    total = sum((item.weighted_contribution for item in components), Decimal(0))
    return tuple(components), max(Decimal(0), min(Decimal(1), total))


def _mean(values, *, default):
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else default
