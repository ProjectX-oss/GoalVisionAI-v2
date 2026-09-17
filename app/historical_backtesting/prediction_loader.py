"""Reproduce raw and calibrated TEST probabilities from persisted artifacts."""

from __future__ import annotations

from app.historical_dataset_split import Partition
from app.historical_model_training import predict_raw_probabilities
from app.historical_probability_calibration import (
    DEFAULT_HISTORICAL_CALIBRATION_POLICY,
    ValidationPrediction,
)
from app.historical_probability_calibration.artifact import apply_calibration
from app.historical_probability_calibration.validation import validate_calibrated_probabilities

from .fingerprint import sha256_fingerprint
from .models import BacktestPrediction
from .policy import PREDICTION_IMPLEMENTATION_VERSION


def reproduce_predictions(examples, artifact, calibration_set, *, run_namespace=""):
    result = []
    for order, example in enumerate(examples):
        raw = predict_raw_probabilities(
            artifact, example.ordered_feature_vector, example.missingness_mask,
            feature_schema_version=example.feature_schema_version,
            feature_schema_fingerprint=artifact.feature_schema_fingerprint,
            ordered_feature_names=artifact.ordered_feature_names,
        )
        raw_fingerprint = sha256_fingerprint(
            {
                "model_artifact_fingerprint": artifact.artifact_fingerprint,
                "example_fingerprint": example.example_fingerprint,
                "ordered_raw_probabilities": raw.raw_probabilities,
                "target_schema": artifact.target_schema_version,
                "implementation": PREDICTION_IMPLEMENTATION_VERSION,
            }
        )
        temporary = ValidationPrediction(
            training_example_id=example.training_example_id,
            example_fingerprint=example.example_fingerprint,
            artifact_id=artifact.artifact_id,
            artifact_fingerprint=artifact.artifact_fingerprint,
            training_run_id=artifact.training_run_id,
            split_id=artifact.source_split_id,
            fold_id=artifact.fold_id,
            partition=Partition.TEST,
            raw_probabilities=raw.raw_probabilities,
            calibrated_probabilities=None,
            raw_prediction_fingerprint=raw_fingerprint,
            deterministic_order=order,
        )
        calibrated = apply_calibration(
            temporary, calibration_set.target_artifacts,
            DEFAULT_HISTORICAL_CALIBRATION_POLICY,
        )
        validate_calibrated_probabilities(calibrated.calibrated_probabilities)
        calibrated_fingerprint = sha256_fingerprint(
            {
                "model_artifact_fingerprint": artifact.artifact_fingerprint,
                "calibration_artifact_set_fingerprint": calibration_set.artifact_set_fingerprint,
                "example_fingerprint": example.example_fingerprint,
                "ordered_raw_probabilities": raw.raw_probabilities,
                "ordered_calibrated_probabilities": calibrated.calibrated_probabilities,
                "target_schema": artifact.target_schema_version,
                "prediction_implementation_version": PREDICTION_IMPLEMENTATION_VERSION,
            }
        )
        row_id = f"historical-backtest-prediction-{sha256_fingerprint((run_namespace, example.example_fingerprint))}"
        result.append(
            BacktestPrediction(
                prediction_row_id=row_id,
                training_example_id=example.training_example_id,
                historical_match_id=example.historical_match_id,
                example_fingerprint=example.example_fingerprint,
                competition=example.competition,
                season=example.season,
                kickoff_utc=example.kickoff_utc,
                raw_probabilities=raw.raw_probabilities,
                calibrated_probabilities=calibrated.calibrated_probabilities,
                labels=example.labels,
                raw_prediction_fingerprint=raw_fingerprint,
                calibrated_prediction_fingerprint=calibrated_fingerprint,
                deterministic_order=order,
            )
        )
    return tuple(result)
