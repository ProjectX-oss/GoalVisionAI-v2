"""Promotion and runtime artifact provenance verification."""

from app.historical_model_training.inspection import (
    verify_artifact_fingerprint, verify_estimator_fingerprints,
)
from app.historical_probability_calibration.inspection import (
    verify_calibration_artifact_fingerprint, verify_target_artifact_fingerprints,
)
from app.model_comparison_promotion import GateStatus, Recommendation

from .exceptions import ActivationNotEligibleError


def verify_promotion(request, comparison_repository):
    run = comparison_repository.load_comparison_run(request.comparison_run_id)
    if run is None or run.comparison_run_fingerprint != request.comparison_run_fingerprint:
        raise ActivationNotEligibleError("Promotion comparison is missing or differs.")
    evaluation = next((item for item in run.evaluations if item.candidate.challenger_candidate_id == request.challenger_candidate_id), None)
    if evaluation is None or evaluation.recommendation is not Recommendation.PROMOTE_CHALLENGER:
        raise ActivationNotEligibleError("Challenger lacks PROMOTE_CHALLENGER approval.")
    if run.final_recommended_challenger_id != request.challenger_candidate_id or run.final_recommendation is not Recommendation.PROMOTE_CHALLENGER:
        raise ActivationNotEligibleError("Promotion recommendation is not final.")
    recommendation = next((item for item in comparison_repository.list_recommendations(run.comparison_run_id) if item.recommendation_id == request.recommendation_id), None)
    if (
        recommendation is None
        or recommendation.recommendation is not Recommendation.PROMOTE_CHALLENGER
        or recommendation.recommendation_fingerprint != request.recommendation_fingerprint
    ):
        raise ActivationNotEligibleError("Promotion recommendation fingerprint differs.")
    if any(item.mandatory and item.status is not GateStatus.PASS for item in evaluation.gate_evaluations):
        raise ActivationNotEligibleError("A mandatory promotion gate is not PASS.")
    candidate = evaluation.candidate
    if (
        candidate.model_artifact_id != request.challenger.model_artifact_id
        or candidate.model_artifact_fingerprint != request.challenger.model_artifact_fingerprint
        or candidate.calibration_artifact_set_id != request.challenger.calibration_artifact_set_id
        or candidate.calibration_artifact_set_fingerprint != request.challenger.calibration_artifact_set_fingerprint
    ):
        raise ActivationNotEligibleError("Approved challenger artifacts differ from the request.")
    if (
        run.command.champion_model_artifact_id != request.current_champion.model_artifact_id
        or run.command.champion_model_artifact_fingerprint != request.current_champion.model_artifact_fingerprint
    ):
        raise ActivationNotEligibleError("Comparison champion differs from the request.")


def verify_runtime_artifact(reference, model_repository, calibration_repository, policy):
    artifact = model_repository.load_model_artifact(reference.model_artifact_id)
    calibration = calibration_repository.load_calibration_artifact_set(reference.calibration_artifact_set_id)
    if artifact is None or artifact.artifact_fingerprint != reference.model_artifact_fingerprint:
        raise ActivationNotEligibleError("Model artifact is missing or differs.")
    if artifact.preprocessing.preprocessing_fingerprint != reference.preprocessing_fingerprint:
        raise ActivationNotEligibleError("Preprocessing fingerprint differs.")
    if calibration is None or calibration.artifact_set_fingerprint != reference.calibration_artifact_set_fingerprint:
        raise ActivationNotEligibleError("Calibration artifact is missing or differs.")
    if calibration.command.source_model_artifact_id != artifact.artifact_id:
        raise ActivationNotEligibleError("Calibration is not linked to the model artifact.")
    if (
        artifact.feature_schema_version != reference.feature_schema_version
        or artifact.feature_schema_fingerprint != reference.feature_schema_fingerprint
        or artifact.target_schema_version != reference.target_contract_version
        or calibration.command.runtime_compatibility_version != reference.runtime_compatibility_version
        or reference.probability_contract_version != policy.required_probability_contract_version
        or reference.runtime_compatibility_version != policy.required_runtime_compatibility_version
    ):
        raise ActivationNotEligibleError("Runtime schema or probability compatibility differs.")
    failures = (
        *verify_artifact_fingerprint(model_repository, artifact.artifact_id),
        *verify_estimator_fingerprints(model_repository, artifact.artifact_id),
        *verify_calibration_artifact_fingerprint(calibration_repository, calibration.artifact_set_id),
        *verify_target_artifact_fingerprints(calibration_repository, calibration.artifact_set_id),
    )
    if failures:
        raise ActivationNotEligibleError("Artifact integrity verification failed.")
    return artifact, calibration
