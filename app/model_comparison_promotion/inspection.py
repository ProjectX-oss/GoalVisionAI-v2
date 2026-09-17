"""Read-only inspection and deterministic reproduction helpers."""

from __future__ import annotations

import json

from .betting_comparison import compare_betting_metrics
from .calibration_comparison import compare_calibration_metrics
from .decision import rank_challengers, recommend_challenger
from .fingerprint import (
    challenger_evaluation_fingerprint,
    comparison_run_fingerprint,
    metric_comparison_fingerprint,
    source_compatibility_fingerprint,
)
from .normalization import verify_scope_compatibility
from .predictive_comparison import compare_predictive_metrics
from .risk_comparison import compare_risk_metrics
from .scoring import calculate_promotion_score
from .significance import calculate_statistical_evidence
from .source_verification import (
    verify_challenger_source_integrity,
    verify_champion_source_integrity,
)
from .stability import calculate_stability


def summarize_comparison_run(repository, comparison_run_id):
    run = repository.load_comparison_run(comparison_run_id)
    if run is None:
        return None
    return {
        "comparison_run_id": run.comparison_run_id,
        "comparison_request_id": run.command.comparison_request_id,
        "champion_model_artifact_id": run.command.champion_model_artifact_id,
        "challenger_count": len(run.command.challengers),
        "valid_challenger_count": len(run.evaluations),
        "final_recommended_challenger_id": run.final_recommended_challenger_id,
        "final_recommendation": run.final_recommendation,
    }


def inspect_challenger_evaluation(repository, comparison_run_id, candidate_id):
    run = repository.load_comparison_run(comparison_run_id)
    return next(
        (
            item
            for item in run.evaluations
            if item.candidate.challenger_candidate_id == candidate_id
        ),
        None,
    ) if run else None


def inspect_metric_comparison(repository, run_id, metric_evaluation_id):
    return _find(repository.list_metric_evaluations(run_id), "metric_evaluation_id", metric_evaluation_id)


def inspect_stability_group(repository, run_id, stability_row_id):
    return _find(repository.list_stability_groups(run_id), "stability_row_id", stability_row_id)


def inspect_statistical_evidence(repository, run_id, statistical_row_id):
    return _find(repository.list_statistical_evidence(run_id), "statistical_row_id", statistical_row_id)


def inspect_gate_evaluation(repository, run_id, gate_evaluation_id):
    return _find(repository.list_gate_evaluations(run_id), "gate_evaluation_id", gate_evaluation_id)


def inspect_score_breakdown(repository, run_id, candidate_id):
    evaluation = inspect_challenger_evaluation(repository, run_id, candidate_id)
    return evaluation.score_components if evaluation else ()


def inspect_final_recommendation(repository, run_id):
    return next(
        (
            item
            for item in repository.list_recommendations(run_id)
            if item.recommendation_scope == "FINAL"
        ),
        None,
    )


def verify_metric_reproduction(champion_run, challenger_run, policy, stored):
    reproduced = (
        compare_predictive_metrics(champion_run, challenger_run, policy)
        + compare_calibration_metrics(champion_run, challenger_run, policy)
        + compare_betting_metrics(champion_run, challenger_run, policy)
        + compare_risk_metrics(champion_run, challenger_run, policy)
    )
    expected = tuple(item.metric_fingerprint for item in stored)
    actual = tuple(item.metric_fingerprint for item in reproduced)
    return () if actual == expected else ("METRIC_REPRODUCTION_MISMATCH",)


def verify_stability_reproduction(champion_run, challenger_run, policy, stored):
    reproduced = calculate_stability(champion_run, challenger_run, policy)
    return () if tuple(item.stability_fingerprint for item in reproduced) == tuple(
        item.stability_fingerprint for item in stored
    ) else ("STABILITY_REPRODUCTION_MISMATCH",)


def verify_statistical_reproduction(
    champion_run, challenger_run, comparison_fingerprint, policy, stored
):
    reproduced = calculate_statistical_evidence(
        champion_run,
        challenger_run,
        comparison_fingerprint=comparison_fingerprint,
        policy=policy,
    )
    return () if tuple(item.evidence_fingerprint for item in reproduced) == tuple(
        item.evidence_fingerprint for item in stored
    ) else ("STATISTICAL_REPRODUCTION_MISMATCH",)


def verify_gate_reproduction(stored, reproduced):
    material = lambda rows: tuple(
        (
            item.gate_category,
            item.gate_name,
            item.mandatory,
            item.status,
            item.reason_codes,
        )
        for item in rows
    )
    return () if material(stored) == material(reproduced) else ("GATE_REPRODUCTION_MISMATCH",)


def verify_score_reproduction(evaluation, policy):
    components, score = calculate_promotion_score(
        evaluation.metric_evaluations,
        evaluation.stability_groups,
        evaluation.gate_evaluations,
        evaluation.statistical_evidence,
        policy,
    )
    expected = tuple(
        (
            item.score_category,
            item.normalized_score,
            item.weight,
            item.weighted_contribution,
        )
        for item in evaluation.score_components
    )
    actual = tuple(
        (
            item.score_category,
            item.normalized_score,
            item.weight,
            item.weighted_contribution,
        )
        for item in components
    )
    return () if actual == expected and score == evaluation.promotion_score else ("SCORE_REPRODUCTION_MISMATCH",)


def verify_ranking_reproduction(run):
    expected = tuple(
        item.candidate.challenger_candidate_id
        for item in sorted(run.evaluations, key=lambda item: item.deterministic_rank)
    )
    actual = tuple(
        item.candidate.challenger_candidate_id
        for item in rank_challengers(run.evaluations)
    )
    return () if actual == expected else ("RANKING_REPRODUCTION_MISMATCH",)


def verify_comparison_fingerprints(repository, run_id):
    run = repository.load_comparison_run(run_id)
    if run is None:
        return ("COMPARISON_NOT_FOUND",)
    snapshot = json.loads(run.deterministic_run_snapshot)
    material = snapshot["run_material"]
    expected = comparison_run_fingerprint(
        run.request_fingerprint,
        tuple(item.evaluation_fingerprint for item in run.evaluations),
        tuple(material["ranking"]),
        run.final_recommendation.value,
        tuple(tuple(item) for item in material["policy_versions"]),
    )
    failures = []
    if expected != run.comparison_run_fingerprint:
        failures.append("COMPARISON_RUN_FINGERPRINT_MISMATCH")
    for item in run.evaluations:
        if source_compatibility_fingerprint(item.source_evidence) != item.source_compatibility_fingerprint:
            failures.append(f"{item.candidate.challenger_candidate_id}:SOURCE_FINGERPRINT_MISMATCH")
        for metric in item.metric_evaluations:
            if metric.metric_fingerprint != metric_comparison_fingerprint(
                {
                    "category": metric.category,
                    "group": metric.group_identity,
                    "metric": metric.metric_name,
                    "direction": metric.direction,
                    "champion": metric.champion_value,
                    "challenger": metric.challenger_value,
                    "delta": metric.absolute_delta,
                    "relative": metric.relative_delta,
                    "score": metric.normalized_score,
                    "materiality": metric.materiality,
                    "gate": metric.gate_status,
                    "reasons": metric.reason_codes,
                }
            ):
                failures.append(f"{metric.metric_evaluation_id}:METRIC_FINGERPRINT_MISMATCH")
    return tuple(failures)


def reproduce_final_recommendation(run, policy):
    reproduced = []
    for item in run.evaluations:
        recommendation, reasons = recommend_challenger(
            item.gate_evaluations,
            item.promotion_score,
            item.statistical_evidence,
            policy,
            scope_review=any(
                reason == "POLICY_NORMALIZED_SCOPE_REQUIRES_REVIEW"
                for reason in item.reason_codes
            ),
        )
        reproduced.append((item.candidate.challenger_candidate_id, recommendation, reasons))
    return tuple(reproduced)


def _find(values, attribute, identity):
    return next((item for item in values if getattr(item, attribute) == identity), None)


__all__ = [
    "summarize_comparison_run",
    "inspect_challenger_evaluation",
    "inspect_metric_comparison",
    "inspect_stability_group",
    "inspect_statistical_evidence",
    "inspect_gate_evaluation",
    "inspect_score_breakdown",
    "inspect_final_recommendation",
    "verify_champion_source_integrity",
    "verify_challenger_source_integrity",
    "verify_scope_compatibility",
    "verify_metric_reproduction",
    "verify_stability_reproduction",
    "verify_statistical_reproduction",
    "verify_gate_reproduction",
    "verify_score_reproduction",
    "verify_ranking_reproduction",
    "verify_comparison_fingerprints",
    "reproduce_final_recommendation",
]
