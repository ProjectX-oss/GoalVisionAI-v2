from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.calibration import CalibrationObservation
from app.prediction_inference import PredictionTarget
from app.probability_calibration import CalibrationMethod, ProbabilityCalibrationConfig


class CalibratedAssemblyStatus(str, Enum):
    GENERATED = "GENERATED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    REJECTED_INVALID_INFERENCE = "REJECTED_INVALID_INFERENCE"
    REJECTED_INCOMPLETE_CALIBRATION_SET = "REJECTED_INCOMPLETE_CALIBRATION_SET"
    REJECTED_INCOMPATIBLE_CALIBRATION = "REJECTED_INCOMPATIBLE_CALIBRATION"
    REJECTED_INVALID_CALIBRATED_OUTPUT = "REJECTED_INVALID_CALIBRATED_OUTPUT"
    CALIBRATION_EXECUTION_FAILED = "CALIBRATION_EXECUTION_FAILED"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class CalibrationArtifact:
    artifact_id: str
    target: PredictionTarget
    method: CalibrationMethod
    calibration_model_version: str
    source_model_artifact_id: str
    compatible_source_model_versions: tuple[str, ...]
    input_probability_schema: str
    input_probability_schema_version: str
    calibration_policy_version: str
    config: ProbabilityCalibrationConfig
    historical_data: tuple[CalibrationObservation, ...]
    active: bool
    training_data_cutoff: datetime | None = None
    fitted_timestamp: datetime | None = None
    quality_metadata_reference: str | None = None
    compatibility_metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CalibrationTargetMapping:
    target: PredictionTarget
    calibration_artifact_id: str


@dataclass(frozen=True, slots=True)
class CalibrationSetDefinition:
    calibration_set_id: str
    set_name: str
    set_version: str
    source_model_artifact_id: str
    compatible_source_model_versions: tuple[str, ...]
    ordered_target_mappings: tuple[CalibrationTargetMapping, ...]
    policy_version: str
    active: bool
    created_timestamp: datetime
    effective_timestamp: datetime
    calibration_set_fingerprint: str


@dataclass(frozen=True, slots=True)
class ResolvedCalibrationPlan:
    calibration_set_id: str | None
    calibration_set_fingerprint: str
    ordered_artifacts: tuple[CalibrationArtifact, ...]
    set_definition: CalibrationSetDefinition | None


@dataclass(frozen=True, slots=True)
class CalibratedTargetResult:
    target: PredictionTarget
    raw_probability: Decimal
    calibrated_probability: Decimal
    calibration_artifact_id: str
    calibration_method: CalibrationMethod
    calibration_model_version: str
    calibration_policy_version: str
    calibration_report_fingerprint: str
    quality_metadata_reference: str | None
    clamping_indicator: bool | None
    diagnostics: tuple[str, ...]
    target_result_fingerprint: str


@dataclass(frozen=True, slots=True)
class CalibratedValidationCheck:
    code: str
    passed: bool
    observed_value: Decimal
    tolerance: Decimal


@dataclass(frozen=True, slots=True)
class CalibratedValidationSummary:
    policy_version: str
    target_count: int
    ordered_checks: tuple[CalibratedValidationCheck, ...]


@dataclass(frozen=True, slots=True)
class CalibratedMarketProbabilityAssembly:
    calibrated_assembly_id: str
    inference_id: str
    model_input_id: str
    match_id: str
    source_snapshot_id: str
    source_feature_set_id: str
    source_model_artifact_id: str
    source_model_name: str
    source_model_version: str
    raw_inference_fingerprint: str
    calibration_set_id: str | None
    calibration_set_fingerprint: str
    assembly_policy_version: str
    calibration_effective_timestamp: datetime
    created_timestamp: datetime
    ordered_target_results: tuple[CalibratedTargetResult, ...]
    validation_summary: CalibratedValidationSummary
    calibrated_assembly_fingerprint: str


@dataclass(frozen=True, slots=True)
class CalibratedAssemblyOutcome:
    calibrated_assembly_id: str | None
    inference_id: str
    match_id: str
    source_model_artifact_id: str
    source_model_version: str
    calibration_set_id: str | None
    calibrated_assembly_fingerprint: str | None
    final_status: CalibratedAssemblyStatus
    ordered_reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    ordered_calibrated_target_results: tuple[CalibratedTargetResult, ...]
    calibration_effective_timestamp: datetime
    assembly_policy_version: str


@dataclass(frozen=True, slots=True)
class FutureMarketProbabilityInput:
    calibrated_assembly_id: str
    inference_id: str
    match_id: str
    source_model_artifact_id: str
    source_model_version: str
    calibration_set_id: str | None
    raw_inference_fingerprint: str
    calibrated_assembly_fingerprint: str
    ordered_targets: tuple[CalibratedTargetResult, ...]
