"""Persisted-artifact inference and exactly-once calibration."""

from app.historical_model_training import predict_raw_probabilities
from app.historical_probability_calibration.artifact import apply_calibration
from app.historical_probability_calibration.models import ValidationPrediction
from app.historical_probability_calibration.policy import DEFAULT_HISTORICAL_CALIBRATION_POLICY
from app.historical_dataset_split import Partition

from .fingerprint import sha256_fingerprint
from .models import ModelRole, ShadowInference
from .probability_contract import verify_probability_contract


def infer(role, artifact, calibration, snapshot, *, namespace=""):
    raw_prediction = predict_raw_probabilities(
        artifact, snapshot.ordered_feature_values, snapshot.missingness_mask,
        feature_schema_version=snapshot.feature_schema_version,
        feature_schema_fingerprint=snapshot.feature_schema_fingerprint,
        ordered_feature_names=snapshot.ordered_feature_names,
    )
    raw = raw_prediction.raw_probabilities
    verify_probability_contract(raw)
    raw_fp = sha256_fingerprint({
        "role": role, "artifact": artifact.artifact_fingerprint,
        "input": snapshot.input_snapshot_fingerprint,
        "probabilities": tuple((item.target.value, item.probability) for item in raw.ordered_probabilities),
    })
    holder = ValidationPrediction(
        training_example_id=snapshot.model_input_vector_id,
        example_fingerprint=snapshot.input_snapshot_fingerprint,
        artifact_id=artifact.artifact_id, artifact_fingerprint=artifact.artifact_fingerprint,
        training_run_id=artifact.training_run_id, split_id=artifact.source_split_id,
        fold_id=artifact.fold_id, partition=Partition.VALIDATION,
        raw_probabilities=raw, calibrated_probabilities=None, raw_prediction_fingerprint=raw_fp,
    )
    calibrated_holder = apply_calibration(
        holder, calibration.target_artifacts, DEFAULT_HISTORICAL_CALIBRATION_POLICY,
    )
    calibrated = calibrated_holder.calibrated_probabilities
    verify_probability_contract(calibrated)
    calibrated_fp = sha256_fingerprint({
        "raw": raw_fp, "calibration": calibration.artifact_set_fingerprint,
        "probabilities": tuple((item.target.value, item.probability) for item in calibrated.ordered_probabilities),
        "reconciliation": calibrated_holder.reconciliation_snapshot,
        "monotonicity": calibrated_holder.monotonicity_adjustment_snapshot,
    })
    role = ModelRole(role)
    return ShadowInference(
        inference_id=f"shadow-inference-{sha256_fingerprint((namespace, role, calibrated_fp))}",
        model_role=role, model_artifact_id=artifact.artifact_id,
        model_artifact_fingerprint=artifact.artifact_fingerprint,
        calibration_artifact_set_id=calibration.artifact_set_id,
        calibration_artifact_set_fingerprint=calibration.artifact_set_fingerprint,
        raw_probabilities=raw, calibrated_probabilities=calibrated,
        raw_inference_fingerprint=raw_fp, calibrated_inference_fingerprint=calibrated_fp,
        preprocessing_fingerprint=artifact.preprocessing.preprocessing_fingerprint,
        reconciliation_snapshot=calibrated_holder.reconciliation_snapshot,
        monotonicity_snapshot=calibrated_holder.monotonicity_adjustment_snapshot,
    )
