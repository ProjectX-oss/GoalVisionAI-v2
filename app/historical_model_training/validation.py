"""Fail-closed command, feature, label, and probability validation."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from decimal import Decimal

from app.historical_dataset_split import Partition
from app.historical_training_dataset import (
    FEATURE_SCHEMA_VERSION, HISTORICAL_TRAINING_FEATURES_V1, LABEL_ORDER,
    LABEL_SCHEMA_VERSION, HistoricalTrainingExample,
)
from app.prediction_inference.models import OFFICIAL_TARGET_ORDER, RawProbabilitySet

from .exceptions import FeatureSchemaError, InvalidProbabilityError, LabelSchemaError, TrainingRequestValidationError
from .fingerprint import sha256_fingerprint
from .models import HistoricalModelTrainingCommand, NormalizedTrainingCommand
from .policy import (
    ARTIFACT_FORMAT_VERSION, METADATA_VERSION, MODEL_FAMILY, MODEL_POLICY_VERSION,
    PREPROCESSING_POLICY_VERSION, TARGET_SCHEMA_VERSION, ClassWeightPolicy,
    MissingValuePolicy, ScalingPolicy,
)


FEATURE_NAMES = tuple(item.name for item in HISTORICAL_TRAINING_FEATURES_V1)
FEATURE_SCHEMA_FINGERPRINT = sha256_fingerprint({
    "schema_version": FEATURE_SCHEMA_VERSION,
    "features": tuple((item.index, item.name, item.data_type.value) for item in HISTORICAL_TRAINING_FEATURES_V1),
})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


def normalize_training_command(command: HistoricalModelTrainingCommand) -> NormalizedTrainingCommand:
    if not isinstance(command, HistoricalModelTrainingCommand):
        raise TrainingRequestValidationError("A typed HistoricalModelTrainingCommand is required.")
    for name in ("training_request_id", "source_split_id", "fold_id"):
        value = getattr(command, name)
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise TrainingRequestValidationError(f"Invalid {name}.")
    if not isinstance(command.training_run_name, str) or not command.training_run_name.strip():
        raise TrainingRequestValidationError("Training run name is required.")
    partition = _enum(Partition, command.training_partition, "training partition")
    if partition is not Partition.TRAIN:
        raise TrainingRequestValidationError("Only TRAIN may be selected for fitting; TEST access is forbidden.")
    if command.feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise TrainingRequestValidationError("Unsupported feature schema version.")
    if command.label_schema_version != LABEL_SCHEMA_VERSION:
        raise TrainingRequestValidationError("Unsupported label schema version.")
    if command.target_schema_version != TARGET_SCHEMA_VERSION:
        raise TrainingRequestValidationError("Unsupported target schema version.")
    if command.preprocessing_policy_version != PREPROCESSING_POLICY_VERSION:
        raise TrainingRequestValidationError("Unsupported preprocessing policy version.")
    if command.model_policy_version != MODEL_POLICY_VERSION or command.model_family != MODEL_FAMILY:
        raise TrainingRequestValidationError("Unsupported model policy or family.")
    if command.artifact_format_version != ARTIFACT_FORMAT_VERSION or command.metadata_version != METADATA_VERSION:
        raise TrainingRequestValidationError("Unsupported artifact or metadata version.")
    if not command.ordered_feature_names or not command.feature_schema_fingerprint:
        raise TrainingRequestValidationError("Feature names and schema fingerprint must be explicit.")
    names = command.ordered_feature_names
    fingerprint = command.feature_schema_fingerprint
    if names != FEATURE_NAMES or len(names) != 145 or fingerprint != FEATURE_SCHEMA_FINGERPRINT:
        raise TrainingRequestValidationError("The exact 145-position feature contract is required.")
    from .models import EstimatorConfiguration
    if not isinstance(command.estimator, EstimatorConfiguration):
        raise TrainingRequestValidationError("A typed EstimatorConfiguration is required.")
    if not isinstance(command.estimator.random_seed, int) or isinstance(command.estimator.random_seed, bool):
        raise TrainingRequestValidationError("Random seed must be an explicit integer.")
    if command.estimator.class_weight_policy is not ClassWeightPolicy.NONE:
        raise TrainingRequestValidationError("Unsupported class-weight policy.")
    if command.estimator.maximum_iterations < 1 or command.estimator.convergence_tolerance <= 0:
        raise TrainingRequestValidationError("Invalid convergence hyperparameters.")
    if command.estimator.learning_rate <= 0 or command.estimator.regularization < 0:
        raise TrainingRequestValidationError("Invalid estimator hyperparameters.")
    missing = _enum(MissingValuePolicy, command.missing_value_policy, "missing-value policy")
    scaling = _enum(ScalingPolicy, command.scaling_policy, "scaling policy")
    timestamp = _utc(command.training_timestamp)
    for field in (command.code_version, command.environment_metadata_version, command.dependency_metadata_version):
        if not isinstance(field, str) or not field.strip() or len(field) > 200:
            raise TrainingRequestValidationError("Malformed execution metadata.")
    return NormalizedTrainingCommand(
        training_request_id=command.training_request_id,
        training_run_name=" ".join(command.training_run_name.split()),
        source_split_id=command.source_split_id,
        source_split_fingerprint=_sha(command.source_split_fingerprint, "source split fingerprint"),
        fold_id=command.fold_id, fold_fingerprint=_sha(command.fold_fingerprint, "fold fingerprint"),
        training_partition=partition, evaluate_validation=bool(command.evaluate_validation),
        feature_schema_version=command.feature_schema_version, feature_schema_fingerprint=fingerprint,
        ordered_feature_names=names, label_schema_version=command.label_schema_version,
        target_schema_version=command.target_schema_version,
        preprocessing_policy_version=command.preprocessing_policy_version,
        model_policy_version=command.model_policy_version,
        artifact_format_version=command.artifact_format_version, model_family=command.model_family,
        estimator=command.estimator, missing_value_policy=missing, scaling_policy=scaling,
        append_missingness_indicators=bool(command.append_missingness_indicators),
        training_timestamp=timestamp, code_version=command.code_version,
        environment_metadata_version=command.environment_metadata_version,
        dependency_metadata_version=command.dependency_metadata_version,
        metadata_version=command.metadata_version,
    )


def validate_example(example: HistoricalTrainingExample) -> None:
    if example.feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise FeatureSchemaError("Feature schema mismatch.")
    if len(example.ordered_feature_vector) != 145 or len(example.missingness_mask) != 145:
        raise FeatureSchemaError("Feature vector and mask must contain exactly 145 positions.")
    for index, (value, missing) in enumerate(zip(example.ordered_feature_vector, example.missingness_mask)):
        if missing != (value is None):
            raise FeatureSchemaError(f"Missingness mask mismatch at feature {index}.")
        if value is not None:
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise FeatureSchemaError(f"Malformed feature at position {index}.") from exc
            if not math.isfinite(number):
                raise FeatureSchemaError(f"Non-finite feature at position {index}.")
    if not example.completeness_score.is_finite() or not Decimal(0) <= example.completeness_score <= Decimal(1):
        raise FeatureSchemaError("Completeness score is invalid.")
    if example.label_schema_version != LABEL_SCHEMA_VERSION:
        raise LabelSchemaError("Label schema mismatch.")
    if tuple(name for name, _ in example.labels) != LABEL_ORDER:
        raise LabelSchemaError("Label order mismatch.")
    if any(value not in (0, 1) for _, value in example.labels):
        raise LabelSchemaError("Labels must be binary.")
    labels = dict(example.labels)
    if labels["HOME_WIN"] + labels["DRAW"] + labels["AWAY_WIN"] != 1:
        raise LabelSchemaError("Match-result labels are incoherent.")
    for over, under in (("OVER_1_5", "UNDER_1_5"), ("OVER_2_5", "UNDER_2_5"), ("OVER_3_5", "UNDER_3_5"), ("BTTS_YES", "BTTS_NO")):
        if labels[over] + labels[under] != 1:
            raise LabelSchemaError("Complementary labels are incoherent.")
    if not labels["OVER_3_5"] <= labels["OVER_2_5"] <= labels["OVER_1_5"]:
        raise LabelSchemaError("Totals labels are not monotonic.")


def validate_raw_probabilities(probabilities: RawProbabilitySet, tolerance: Decimal = Decimal("0.000001")) -> None:
    expected = tuple(OFFICIAL_TARGET_ORDER)
    if tuple(item.target for item in probabilities.ordered_probabilities) != expected:
        raise InvalidProbabilityError("Canonical 11-target order is required.")
    values = {item.target.value: item.probability for item in probabilities.ordered_probabilities}
    if any(not value.is_finite() or value < 0 or value > 1 for value in values.values()):
        raise InvalidProbabilityError("Every raw probability must be finite and in [0, 1].")
    if abs(values["HOME_WIN"] + values["DRAW"] + values["AWAY_WIN"] - 1) > tolerance:
        raise InvalidProbabilityError("Match-result probabilities do not sum to one.")
    for first, second in (("OVER_1_5", "UNDER_1_5"), ("OVER_2_5", "UNDER_2_5"), ("OVER_3_5", "UNDER_3_5"), ("BTTS_YES", "BTTS_NO")):
        if abs(values[first] + values[second] - 1) > tolerance:
            raise InvalidProbabilityError("Complementary probabilities do not sum to one.")
    if values["OVER_3_5"] > values["OVER_2_5"] + tolerance or values["OVER_2_5"] > values["OVER_1_5"] + tolerance:
        raise InvalidProbabilityError("Totals probabilities are not monotonic.")


def _utc(value: datetime | str) -> str:
    if isinstance(value, str):
        if not value.strip():
            raise TrainingRequestValidationError("Explicit training timestamp is required.")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TrainingRequestValidationError("Training timestamp is malformed.") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise TrainingRequestValidationError("Training timestamp is malformed.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrainingRequestValidationError("Training timestamp must be timezone-aware.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise TrainingRequestValidationError(f"Invalid {name}.")
    return value


def _enum(kind, value, name):
    try:
        return value if isinstance(value, kind) else kind(value)
    except (TypeError, ValueError) as exc:
        raise TrainingRequestValidationError(f"Unsupported {name}.") from exc
