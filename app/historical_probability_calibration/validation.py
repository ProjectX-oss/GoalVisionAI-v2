"""Fail-closed calibration command and output validation."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from app.historical_dataset_split import Partition
from app.historical_model_training import TARGET_SCHEMA_VERSION
from app.historical_model_training.feature_contracts import SUPPORTED_TRAINING_FEATURE_CONTRACTS
from app.historical_training_dataset import LABEL_SCHEMA_VERSION
from app.prediction_inference import OFFICIAL_TARGET_ORDER, RawProbabilitySet

from .exceptions import CalibrationRequestValidationError, InvalidCalibratedProbabilityError
from .models import HistoricalCalibrationCommand, NormalizedCalibrationCommand
from .policy import (
    ARTIFACT_FORMAT_VERSION, CALIBRATION_POLICY_VERSION, CLAMP_POLICY_VERSION,
    METADATA_VERSION, MONOTONICITY_POLICY_VERSION, RECONCILIATION_POLICY_VERSION,
    RUNTIME_COMPATIBILITY_VERSION, CalibrationMethod, TargetMethodOverride,
)


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_BASE_TARGETS = {"HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "OVER_2_5", "OVER_3_5", "BTTS_YES"}


def normalize_calibration_command(command: HistoricalCalibrationCommand) -> NormalizedCalibrationCommand:
    if not isinstance(command, HistoricalCalibrationCommand):
        raise CalibrationRequestValidationError("A typed HistoricalCalibrationCommand is required.")
    for name in ("calibration_request_id", "source_training_run_id", "source_model_artifact_id", "source_split_id", "fold_id"):
        if not isinstance(getattr(command, name), str) or not _ID.fullmatch(getattr(command, name)):
            raise CalibrationRequestValidationError(f"Invalid {name}.")
    for name in ("source_training_run_fingerprint", "source_model_artifact_fingerprint", "source_split_fingerprint", "fold_fingerprint"):
        if not isinstance(getattr(command, name), str) or not _SHA.fullmatch(getattr(command, name)):
            raise CalibrationRequestValidationError(f"Invalid {name}.")
    if not isinstance(command.calibration_run_name, str) or not command.calibration_run_name.strip():
        raise CalibrationRequestValidationError("Calibration run name is required.")
    try:
        partition = command.calibration_partition if isinstance(command.calibration_partition, Partition) else Partition(command.calibration_partition)
    except (TypeError, ValueError) as exc:
        raise CalibrationRequestValidationError("Unsupported calibration partition.") from exc
    if partition is not Partition.VALIDATION:
        raise CalibrationRequestValidationError("Calibration fitting is restricted to VALIDATION; TRAIN and TEST are forbidden.")
    expected = (
        (command.label_schema_version, LABEL_SCHEMA_VERSION),
        (command.target_schema_version, TARGET_SCHEMA_VERSION),
        (command.artifact_format_version, ARTIFACT_FORMAT_VERSION),
        (command.runtime_compatibility_version, RUNTIME_COMPATIBILITY_VERSION),
        (command.clamp_policy_version, CLAMP_POLICY_VERSION),
        (command.monotonicity_policy_version, MONOTONICITY_POLICY_VERSION),
        (command.reconciliation_policy_version, RECONCILIATION_POLICY_VERSION),
        (command.calibration_policy_version, CALIBRATION_POLICY_VERSION),
        (command.metadata_version, METADATA_VERSION),
    )
    if any(actual != supported for actual, supported in expected):
        raise CalibrationRequestValidationError("Unsupported schema, artifact, compatibility, or policy version.")
    if not any(
        item.schema_version == command.feature_schema_version
        and item.schema_fingerprint == command.feature_schema_fingerprint
        for item in SUPPORTED_TRAINING_FEATURE_CONTRACTS
    ):
        raise CalibrationRequestValidationError("Unsupported feature schema declaration.")
    methods = tuple(_method(item) for item in (command.match_result_method, command.totals_method, command.btts_method))
    if not isinstance(command.target_method_overrides, tuple) or any(not isinstance(item, TargetMethodOverride) for item in command.target_method_overrides):
        raise CalibrationRequestValidationError("Target method overrides must be typed and immutable.")
    overrides = tuple(command.target_method_overrides)
    if len({item.target_identity for item in overrides}) != len(overrides):
        raise CalibrationRequestValidationError("Target method overrides must be unique.")
    if any(item.target_identity not in _BASE_TARGETS or not isinstance(item.method, CalibrationMethod) for item in overrides):
        raise CalibrationRequestValidationError("Target override is unsupported or attempts to fit a derived complement.")
    timestamp = _utc(command.calibration_timestamp)
    metadata = (command.code_metadata_version, command.dependency_metadata_version, command.environment_metadata_version)
    if any(not isinstance(item, str) or not item.strip() or len(item) > 200 for item in metadata):
        raise CalibrationRequestValidationError("Execution metadata is malformed.")
    return NormalizedCalibrationCommand(
        calibration_request_id=command.calibration_request_id,
        calibration_run_name=" ".join(command.calibration_run_name.split()),
        source_training_run_id=command.source_training_run_id,
        source_training_run_fingerprint=command.source_training_run_fingerprint,
        source_model_artifact_id=command.source_model_artifact_id,
        source_model_artifact_fingerprint=command.source_model_artifact_fingerprint,
        source_split_id=command.source_split_id, source_split_fingerprint=command.source_split_fingerprint,
        fold_id=command.fold_id, fold_fingerprint=command.fold_fingerprint,
        calibration_partition=partition, feature_schema_version=command.feature_schema_version,
        feature_schema_fingerprint=command.feature_schema_fingerprint,
        label_schema_version=command.label_schema_version, target_schema_version=command.target_schema_version,
        artifact_format_version=command.artifact_format_version,
        runtime_compatibility_version=command.runtime_compatibility_version,
        match_result_method=methods[0], totals_method=methods[1], btts_method=methods[2],
        target_method_overrides=overrides, clamp_policy_version=command.clamp_policy_version,
        monotonicity_policy_version=command.monotonicity_policy_version,
        reconciliation_policy_version=command.reconciliation_policy_version,
        calibration_policy_version=command.calibration_policy_version,
        calibration_timestamp=timestamp, code_metadata_version=command.code_metadata_version,
        dependency_metadata_version=command.dependency_metadata_version,
        environment_metadata_version=command.environment_metadata_version,
        metadata_version=command.metadata_version,
    )


def validate_calibrated_probabilities(probabilities: RawProbabilitySet, minimum=Decimal("0.001"), maximum=Decimal("0.999"), tolerance=Decimal("0.000001")):
    if tuple(item.target for item in probabilities.ordered_probabilities) != tuple(OFFICIAL_TARGET_ORDER):
        raise InvalidCalibratedProbabilityError("Canonical 11-target order is required.")
    values = {item.target.value: item.probability for item in probabilities.ordered_probabilities}
    if any(not value.is_finite() or value < minimum or value > maximum for value in values.values()):
        raise InvalidCalibratedProbabilityError("Calibrated probability is outside the explicit clamp range.")
    if abs(values["HOME_WIN"] + values["DRAW"] + values["AWAY_WIN"] - 1) > tolerance:
        raise InvalidCalibratedProbabilityError("Calibrated match-result probabilities are incoherent.")
    for left, right in (("OVER_1_5", "UNDER_1_5"), ("OVER_2_5", "UNDER_2_5"), ("OVER_3_5", "UNDER_3_5"), ("BTTS_YES", "BTTS_NO")):
        if abs(values[left] + values[right] - 1) > tolerance:
            raise InvalidCalibratedProbabilityError("Calibrated complements are incoherent.")
    if values["OVER_3_5"] > values["OVER_2_5"] + tolerance or values["OVER_2_5"] > values["OVER_1_5"] + tolerance:
        raise InvalidCalibratedProbabilityError("Calibrated totals are not monotonic.")


def _method(value):
    try:
        return value if isinstance(value, CalibrationMethod) else CalibrationMethod(value)
    except (TypeError, ValueError) as exc:
        raise CalibrationRequestValidationError("Unsupported calibration method.") from exc


def _utc(value):
    if isinstance(value, str):
        if not value.strip():
            raise CalibrationRequestValidationError("Explicit calibration timestamp is required.")
        try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc: raise CalibrationRequestValidationError("Calibration timestamp is malformed.") from exc
    elif isinstance(value, datetime): parsed = value
    else: raise CalibrationRequestValidationError("Calibration timestamp is malformed.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CalibrationRequestValidationError("Calibration timestamp must be timezone-aware.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
