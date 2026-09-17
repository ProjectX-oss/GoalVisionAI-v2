"""Approval and artifact compatibility verification without activation."""

from app.model_comparison_promotion import GateStatus, Recommendation
from app.historical_model_training.inspection import (
    verify_artifact_fingerprint, verify_estimator_fingerprints,
)
from app.historical_probability_calibration.inspection import (
    verify_calibration_artifact_fingerprint, verify_target_artifact_fingerprints,
)

from .exceptions import ShadowApprovalError, ShadowSourceError


def verify_approval(command, comparison_repository, policy):
    run = comparison_repository.load_comparison_run(command.comparison_run_id)
    if run is None or run.comparison_run_fingerprint != command.comparison_run_fingerprint:
        raise ShadowApprovalError("Promotion-comparison run is missing or differs.")
    evaluation = next(
        (item for item in run.evaluations if item.candidate.challenger_candidate_id == command.challenger_candidate_id),
        None,
    )
    if evaluation is None:
        raise ShadowApprovalError("Approved challenger candidate is absent from the comparison.")
    allowed = {Recommendation.PROMOTE_CHALLENGER}
    if policy.allow_review_recommendation:
        allowed.add(Recommendation.REVIEW_REQUIRED)
    if evaluation.recommendation not in allowed:
        raise ShadowApprovalError("Challenger recommendation is not allowed by shadow policy.")
    if (
        evaluation.recommendation is Recommendation.PROMOTE_CHALLENGER
        and (
            run.final_recommended_challenger_id != command.challenger_candidate_id
            or run.final_recommendation is not Recommendation.PROMOTE_CHALLENGER
        )
    ):
        raise ShadowApprovalError("Challenger is not the comparison's final approved shadow candidate.")
    recommendation = next(
        (item for item in comparison_repository.list_recommendations(run.comparison_run_id)
         if item.recommendation_id == command.recommendation_id),
        None,
    )
    if recommendation is None or recommendation.recommendation_fingerprint != command.recommendation_fingerprint:
        raise ShadowApprovalError("Promotion recommendation is missing or differs.")
    if recommendation.recommendation not in allowed:
        raise ShadowApprovalError("Referenced recommendation is not allowed by shadow policy.")
    failed = tuple(item.gate_name for item in evaluation.gate_evaluations if item.mandatory and item.status is not GateStatus.PASS)
    if failed:
        raise ShadowApprovalError("Mandatory comparison gates are not all PASS: " + ",".join(failed))
    candidate = evaluation.candidate
    if (
        candidate.model_artifact_id != command.challenger_model_artifact_id
        or candidate.model_artifact_fingerprint != command.challenger_model_artifact_fingerprint
        or candidate.calibration_artifact_set_id != command.challenger_calibration_artifact_set_id
        or candidate.calibration_artifact_set_fingerprint != command.challenger_calibration_artifact_set_fingerprint
    ):
        raise ShadowApprovalError("Command challenger differs from the promoted candidate.")
    if (
        run.command.champion_model_artifact_id != command.champion_model_artifact_id
        or run.command.champion_model_artifact_fingerprint != command.champion_model_artifact_fingerprint
        or run.command.champion_calibration_artifact_set_id != command.champion_calibration_artifact_set_id
        or run.command.champion_calibration_artifact_set_fingerprint != command.champion_calibration_artifact_set_fingerprint
    ):
        raise ShadowApprovalError("Command champion differs from the comparison champion.")
    return run, evaluation, recommendation


def load_model_bundle(command, model_repository, calibration_repository, role):
    model_id = getattr(command, f"{role}_model_artifact_id")
    model_fp = getattr(command, f"{role}_model_artifact_fingerprint")
    calibration_id = getattr(command, f"{role}_calibration_artifact_set_id")
    calibration_fp = getattr(command, f"{role}_calibration_artifact_set_fingerprint")
    artifact = model_repository.load_model_artifact(model_id)
    calibration = calibration_repository.load_calibration_artifact_set(calibration_id)
    if artifact is None or artifact.artifact_fingerprint != model_fp:
        raise ShadowSourceError(f"{role} model artifact is missing or differs.")
    if calibration is None or calibration.artifact_set_fingerprint != calibration_fp:
        raise ShadowSourceError(f"{role} calibration artifact is missing or differs.")
    model_failures = (
        *verify_artifact_fingerprint(model_repository, artifact.artifact_id),
        *verify_estimator_fingerprints(model_repository, artifact.artifact_id),
    )
    calibration_failures = (
        *verify_calibration_artifact_fingerprint(calibration_repository, calibration.artifact_set_id),
        *verify_target_artifact_fingerprints(calibration_repository, calibration.artifact_set_id),
    )
    if model_failures:
        raise ShadowSourceError(f"{role} model artifact integrity verification failed.")
    if calibration_failures:
        raise ShadowSourceError(f"{role} calibration artifact integrity verification failed.")
    if calibration.command.source_model_artifact_id != artifact.artifact_id:
        raise ShadowSourceError(f"{role} calibration is not linked to its model.")
    if (
        calibration.command.feature_schema_version != artifact.feature_schema_version
        or calibration.command.feature_schema_fingerprint != artifact.feature_schema_fingerprint
        or calibration.command.target_schema_version != artifact.target_schema_version
    ):
        raise ShadowSourceError(f"{role} model/calibration schema linkage differs.")
    return artifact, calibration
