"""Non-activating adapter to existing runtime calibration artifact types."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from app.calibration import CalibrationFittingPolicy, CalibrationObservation, IsotonicFittingConfig, PlattFittingConfig
from app.calibrated_market_probabilities import CalibrationArtifact
from app.prediction_inference import OFFICIAL_TARGET_ORDER, PredictionTarget
from app.probability_calibration import CalibrationMethod as RuntimeMethod, ProbabilityCalibrationConfig

from .exceptions import SchemaCompatibilityError
from .policy import ARTIFACT_FORMAT_VERSION, RUNTIME_COMPATIBILITY_VERSION, CalibrationMethod


def to_runtime_calibration_artifacts(artifact_set, predictions, training_repository):
    command = artifact_set.command
    if artifact_set.artifact_set_id != f"historical-calibration-artifact-set-{artifact_set.artifact_set_fingerprint}":
        raise SchemaCompatibilityError("Historical calibration artifact-set identity or fingerprint is invalid.")
    if command.artifact_format_version != ARTIFACT_FORMAT_VERSION or command.runtime_compatibility_version != RUNTIME_COMPATIBILITY_VERSION:
        raise SchemaCompatibilityError("Historical calibration artifact version is unsupported by the runtime adapter.")
    if tuple(item.target_identity for item in artifact_set.target_artifacts) != tuple(item.value for item in OFFICIAL_TARGET_ORDER):
        raise SchemaCompatibilityError("Historical calibration target order is incompatible.")
    timestamp = datetime.fromisoformat(command.calibration_timestamp.replace("Z", "+00:00"))
    result = []
    for target_artifact in artifact_set.target_artifacts:
        target = PredictionTarget(target_artifact.target_identity)
        method = {
            CalibrationMethod.IDENTITY_V1: RuntimeMethod.IDENTITY,
            CalibrationMethod.PLATT_SCALING_V1: RuntimeMethod.PLATT,
            CalibrationMethod.ISOTONIC_REGRESSION_V1: RuntimeMethod.ISOTONIC,
        }[target_artifact.method]
        source_parameters = target_artifact
        if target_artifact.derivation_snapshot != "{}":
            source_name = json.loads(target_artifact.derivation_snapshot)["complement_source_target"]
            source_parameters = next(item for item in artifact_set.target_artifacts if item.target_identity == source_name)
        serialized = json.loads(source_parameters.fitted_parameters_snapshot)
        parameters = serialized.get("parameters", {})
        fitting = CalibrationFittingPolicy(
            global_minimum=1, market_minimum=1, competition_minimum=1,
            competition_market_minimum=1, odds_band_minimum=1,
            minimum_positive=1, minimum_negative=1,
        )
        config = ProbabilityCalibrationConfig(
            method=method, calibration_version=command.runtime_compatibility_version,
            fitting_policy=fitting,
            platt=PlattFittingConfig(
                epsilon=Decimal(parameters.get("clipping_epsilon", "0.000001")),
                regularization=Decimal(parameters.get("regularization", "0.001")),
            ),
            isotonic=IsotonicFittingConfig(output_epsilon=Decimal(parameters.get("output_epsilon") or "0.001")),
        )
        observations = []
        for order, prediction in enumerate(predictions):
            example = training_repository.load_training_example(prediction.training_example_id)
            kickoff = datetime.fromisoformat(example.kickoff_utc.replace("Z", "+00:00"))
            raw = prediction.raw_probabilities.probability_for(target)
            observations.append(CalibrationObservation(
                observation_id=f"{example.training_example_id}:{target.value}", fixture_id=order + 1,
                competition=example.competition, market=target.value, selection=target.value,
                prediction_timestamp=kickoff, outcome_timestamp=kickoff, raw_probability=raw,
                binary_outcome=dict(example.labels)[target.value], model_version=command.source_model_artifact_id,
            ))
        result.append(CalibrationArtifact(
            artifact_id=f"{artifact_set.artifact_set_id}:{target.value}", target=target, method=method,
            calibration_model_version=command.source_model_artifact_id,
            source_model_artifact_id=command.source_model_artifact_id,
            compatible_source_model_versions=(command.source_model_artifact_id,),
            input_probability_schema="goalvision_raw_probability", input_probability_schema_version="v1",
            calibration_policy_version=command.runtime_compatibility_version, config=config,
            historical_data=tuple(observations), active=False, training_data_cutoff=max((item.outcome_timestamp for item in observations), default=None),
            fitted_timestamp=timestamp, quality_metadata_reference=target_artifact.target_artifact_fingerprint,
            compatibility_metadata=(("historical_artifact_set_fingerprint", artifact_set.artifact_set_fingerprint),
                                    ("target_artifact_fingerprint", target_artifact.target_artifact_fingerprint)),
        ))
    return tuple(result)
