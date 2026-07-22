"""Historical VALIDATION-only probability calibration fitting service."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from decimal import Decimal

from app.prediction_inference import OFFICIAL_TARGET_ORDER

from .artifact import apply_calibration
from .exceptions import (
    CalibrationConflictError, CalibrationConvergenceError, CalibrationFitError,
    CalibrationPersistenceError, CalibrationRequestValidationError,
    InsufficientClassSupportError, InvalidCalibratedProbabilityError,
    PartitionSafetyError, RawPredictionError, SchemaCompatibilityError,
    SourceArtifactError, SourceSplitError, SourceTrainingRunError,
)
from .fingerprint import canonical_json, sha256_fingerprint
from .fitters import derived_target_artifacts, fit_target_calibrators
from .metrics import calculate_calibration_metrics, calibration_parameter_metrics
from .models import (
    CalibrationArtifactSet, CalibrationOutcome, CalibrationStatus,
    HistoricalCalibrationCommand, PreparedCalibrationRun,
)
from .policy import DEFAULT_HISTORICAL_CALIBRATION_POLICY, HistoricalCalibrationPolicy
from .prediction_loader import load_validation_predictions
from .validation import normalize_calibration_command


class HistoricalProbabilityCalibrationService:
    def __init__(self, model_repository, split_repository, training_repository, calibration_repository,
                 policy=DEFAULT_HISTORICAL_CALIBRATION_POLICY):
        self._models = model_repository
        self._splits = split_repository
        self._training = training_repository
        self._calibrations = calibration_repository
        self._policy = policy

    def fit(self, command: HistoricalCalibrationCommand) -> CalibrationOutcome:
        try:
            normalized = normalize_calibration_command(command)
            if normalized.calibration_policy_version != self._policy.version:
                raise CalibrationRequestValidationError("Injected calibration policy version differs.")
        except (CalibrationRequestValidationError, ValueError) as exc:
            return _rejected(command, CalibrationStatus.REJECTED_INVALID_REQUEST, ("INVALID_CALIBRATION_REQUEST", str(exc)))
        request_fingerprint = sha256_fingerprint({"command": normalized, "support_policy": self._policy})
        existing = self._calibrations.find_by_request_id(normalized.calibration_request_id)
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                return _rejected(command, CalibrationStatus.CONFLICT, ("CALIBRATION_REQUEST_ID_CONFLICT",), request_fingerprint)
            return _outcome(existing, CalibrationStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_CALIBRATION_RUN_EXISTS",))
        try:
            run, artifact, split, fold, loaded = load_validation_predictions(
                normalized, self._models, self._splits, self._training,
            )
        except SourceTrainingRunError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_SOURCE_TRAINING_RUN, ("SOURCE_TRAINING_RUN_REJECTED", str(exc)), request_fingerprint)
        except SourceArtifactError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_SOURCE_ARTIFACT, ("SOURCE_ARTIFACT_REJECTED", str(exc)), request_fingerprint)
        except SourceSplitError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_SOURCE_SPLIT, ("SOURCE_SPLIT_REJECTED", str(exc)), request_fingerprint)
        except PartitionSafetyError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_PARTITION_SAFETY, ("PARTITION_SAFETY_REJECTED", str(exc)), request_fingerprint)
        except SchemaCompatibilityError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_SCHEMA_COMPATIBILITY, ("SCHEMA_COMPATIBILITY_REJECTED", str(exc)), request_fingerprint)
        except RawPredictionError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_RAW_PREDICTIONS, ("RAW_PREDICTION_REPRODUCTION_REJECTED", str(exc)), request_fingerprint)
        if len(loaded) < self._policy.minimum_validation_examples:
            return _rejected(command, CalibrationStatus.REJECTED_INSUFFICIENT_EXAMPLES, ("INSUFFICIENT_VALIDATION_EXAMPLES",), request_fingerprint)
        try:
            calibrators, fitted_artifacts = fit_target_calibrators(normalized, loaded, self._policy)
            target_artifacts = derived_target_artifacts(fitted_artifacts, normalized)
        except InsufficientClassSupportError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_INSUFFICIENT_CLASS_SUPPORT, ("INSUFFICIENT_CALIBRATION_CLASS_SUPPORT", str(exc)), request_fingerprint)
        except CalibrationConvergenceError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_CONVERGENCE, ("CALIBRATION_DID_NOT_CONVERGE", str(exc)), request_fingerprint)
        except CalibrationFitError as exc:
            return _rejected(command, CalibrationStatus.REJECTED_CALIBRATION_FIT, ("CALIBRATION_FIT_REJECTED", str(exc)), request_fingerprint)
        try:
            predictions = tuple(apply_calibration(prediction, fitted_artifacts, self._policy) for _, prediction in loaded)
        except (InvalidCalibratedProbabilityError, ValueError) as exc:
            return _rejected(command, CalibrationStatus.REJECTED_INVALID_CALIBRATED_PROBABILITIES, ("INVALID_CALIBRATED_PROBABILITIES", str(exc)), request_fingerprint)
        paired = tuple((example, prediction) for (example, _), prediction in zip(loaded, predictions))
        metrics, bins, aggregate_raw, aggregate_calibrated = calculate_calibration_metrics(paired, self._policy.reliability_bin_count)
        metrics += calibration_parameter_metrics(target_artifacts, len(metrics))
        monotonicity_summary = _adjustment_summary(predictions, "monotonicity_adjustment_snapshot")
        reconciliation_summary = _adjustment_summary(predictions, "reconciliation_snapshot")
        reconciliation_fingerprint = sha256_fingerprint({
            "class_order": ("HOME_WIN", "DRAW", "AWAY_WIN"),
            "method": normalized.reconciliation_policy_version,
            "tolerance": self._policy.reconciliation_tolerance,
            "summary": reconciliation_summary,
        })
        monotonicity_fingerprint = sha256_fingerprint({
            "targets": ("OVER_1_5", "OVER_2_5", "OVER_3_5"),
            "method": normalized.monotonicity_policy_version,
            "tolerance": self._policy.monotonicity_tolerance,
            "summary": monotonicity_summary,
        })
        calibration_run_id = f"historical-calibration-run-{request_fingerprint}"
        compatibility = canonical_json({
            "target_schema_version": normalized.target_schema_version,
            "canonical_target_order": tuple(item.value for item in OFFICIAL_TARGET_ORDER),
            "runtime_compatibility_version": normalized.runtime_compatibility_version,
            "artifact_format_version": normalized.artifact_format_version,
            "clamp_policy_version": normalized.clamp_policy_version,
            "monotonicity_policy_version": normalized.monotonicity_policy_version,
            "reconciliation_policy_version": normalized.reconciliation_policy_version,
            "source_model_artifact_id": artifact.artifact_id,
            "reconciliation_fingerprint": reconciliation_fingerprint,
            "monotonicity_fingerprint": monotonicity_fingerprint,
        })
        provenance = canonical_json({
            "validation_examples": tuple((example.training_example_id, example.example_fingerprint) for example, _ in loaded),
            "raw_prediction_fingerprints": tuple(item.raw_prediction_fingerprint for item in predictions),
            "validation_row_count": len(predictions), "calibration_timestamp": normalized.calibration_timestamp,
            "code_metadata_version": normalized.code_metadata_version,
            "dependency_metadata_version": normalized.dependency_metadata_version,
            "environment_metadata_version": normalized.environment_metadata_version,
        })
        artifact_set_fingerprint = sha256_fingerprint({
            "request_fingerprint": request_fingerprint,
            "target_artifact_fingerprints": tuple(item.target_artifact_fingerprint for item in target_artifacts),
            "reconciliation_fingerprint": reconciliation_fingerprint,
            "monotonicity_fingerprint": monotonicity_fingerprint,
            "compatibility": compatibility, "aggregate_metrics": (aggregate_raw, aggregate_calibrated),
            "validation_prediction_fingerprints": tuple(item.raw_prediction_fingerprint for item in predictions),
            "artifact_format_version": normalized.artifact_format_version,
        })
        artifact_set = CalibrationArtifactSet(
            artifact_set_id=f"historical-calibration-artifact-set-{artifact_set_fingerprint}",
            artifact_set_fingerprint=artifact_set_fingerprint,
            calibration_run_id=calibration_run_id, request_fingerprint=request_fingerprint,
            command=normalized, target_artifacts=target_artifacts,
            reconciliation_fingerprint=reconciliation_fingerprint,
            monotonicity_fingerprint=monotonicity_fingerprint,
            compatibility_snapshot=compatibility, provenance_snapshot=provenance,
        )
        calibration_run_fingerprint = sha256_fingerprint({
            "request_fingerprint": request_fingerprint,
            "artifact_set_fingerprint": artifact_set_fingerprint,
            "outcome": "CALIBRATION_FITTED",
            "validation_examples": tuple((item.training_example_id, item.example_fingerprint) for item in predictions),
            "policy_versions": (normalized.calibration_policy_version, normalized.runtime_compatibility_version),
        })
        snapshot = canonical_json({
            "command": asdict(normalized), "request_fingerprint": request_fingerprint,
            "calibration_run_fingerprint": calibration_run_fingerprint,
            "artifact_set_fingerprint": artifact_set_fingerprint,
            "aggregate_raw_metrics": aggregate_raw,
            "aggregate_calibrated_metrics": aggregate_calibrated,
            "monotonicity_summary": monotonicity_summary,
            "reconciliation_summary": reconciliation_summary,
        })
        prepared = PreparedCalibrationRun(
            calibration_run_id=calibration_run_id, command=normalized,
            request_fingerprint=request_fingerprint, calibration_run_fingerprint=calibration_run_fingerprint,
            artifact_set=artifact_set, predictions=predictions, metrics=metrics,
            reliability_bins=bins, aggregate_raw_metrics=aggregate_raw,
            aggregate_calibrated_metrics=aggregate_calibrated,
            monotonicity_summary=monotonicity_summary,
            reconciliation_summary=reconciliation_summary,
            deterministic_run_snapshot=snapshot,
        )
        try:
            duplicate = self._calibrations.find_by_calibration_run_fingerprint(calibration_run_fingerprint)
            if duplicate is not None:
                return _outcome(duplicate, CalibrationStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_CALIBRATION_RUN_EXISTS",))
            self._calibrations.append_calibration_run(prepared)
        except CalibrationConflictError:
            return _rejected(command, CalibrationStatus.CONFLICT, ("IMMUTABLE_CALIBRATION_CONFLICT",), request_fingerprint)
        except CalibrationPersistenceError as exc:
            return _rejected(command, CalibrationStatus.PERSISTENCE_FAILURE, ("ATOMIC_CALIBRATION_PERSISTENCE_FAILURE", str(exc)), request_fingerprint)
        return _outcome(prepared, CalibrationStatus.CALIBRATION_FITTED, ("CALIBRATION_ARTIFACT_SET_PERSISTED",))


def fit_historical_probability_calibration(service, command):
    return service.fit(command)


def _adjustment_summary(predictions, attribute):
    values = tuple(json.loads(getattr(item, attribute)) for item in predictions)
    maximums = tuple(Decimal(str(item.get("maximum_adjustment", "0"))) for item in values)
    means = tuple(Decimal(str(item.get("mean_adjustment", item.get("maximum_adjustment", "0")))) for item in values)
    return (
        ("affected_example_count", sum(bool(item.get("affected", maximum > 0)) for item, maximum in zip(values, maximums))),
        ("maximum_adjustment", max(maximums, default=Decimal(0))),
        ("mean_adjustment", sum(means, Decimal(0)) / len(means) if means else Decimal(0)),
    )


def _outcome(run, status, reasons):
    return CalibrationOutcome(
        status=status, calibration_run_id=run.calibration_run_id,
        calibration_artifact_set_id=run.artifact_set.artifact_set_id,
        calibration_request_id=run.command.calibration_request_id,
        request_fingerprint=run.request_fingerprint,
        calibration_run_fingerprint=run.calibration_run_fingerprint,
        artifact_set_fingerprint=run.artifact_set.artifact_set_fingerprint,
        source_training_run_id=run.command.source_training_run_id,
        source_artifact_id=run.command.source_model_artifact_id,
        split_id=run.command.source_split_id, fold_id=run.command.fold_id,
        validation_row_count=len(run.predictions), fitted_target_count=7, derived_target_count=4,
        ordered_target_identities=tuple(item.value for item in OFFICIAL_TARGET_ORDER),
        aggregate_raw_metrics=run.aggregate_raw_metrics,
        aggregate_calibrated_metrics=run.aggregate_calibrated_metrics,
        monotonicity_adjustment_summary=run.monotonicity_summary,
        reconciliation_summary=run.reconciliation_summary,
        ordered_reason_codes=reasons,
        policy_versions=(("calibration", run.command.calibration_policy_version), ("runtime", run.command.runtime_compatibility_version)),
        calibration_timestamp=run.command.calibration_timestamp,
    )


def _rejected(command, status, reasons, fingerprint=None):
    return CalibrationOutcome(
        status=status, calibration_run_id=None, calibration_artifact_set_id=None,
        calibration_request_id=getattr(command, "calibration_request_id", ""), request_fingerprint=fingerprint,
        calibration_run_fingerprint=None, artifact_set_fingerprint=None,
        source_training_run_id=getattr(command, "source_training_run_id", ""),
        source_artifact_id=getattr(command, "source_model_artifact_id", ""),
        split_id=getattr(command, "source_split_id", ""), fold_id=getattr(command, "fold_id", ""),
        validation_row_count=0, fitted_target_count=0, derived_target_count=0,
        ordered_target_identities=(), aggregate_raw_metrics=(), aggregate_calibrated_metrics=(),
        monotonicity_adjustment_summary=(), reconciliation_summary=(), ordered_reason_codes=reasons,
        policy_versions=(), calibration_timestamp=getattr(command, "calibration_timestamp", None) or None,
    )
