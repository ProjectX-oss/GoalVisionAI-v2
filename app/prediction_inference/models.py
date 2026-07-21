from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ports import PredictionModelAdapter


class PredictionTarget(str, Enum):
    HOME_WIN = "HOME_WIN"
    DRAW = "DRAW"
    AWAY_WIN = "AWAY_WIN"
    OVER_1_5 = "OVER_1_5"
    UNDER_1_5 = "UNDER_1_5"
    OVER_2_5 = "OVER_2_5"
    UNDER_2_5 = "UNDER_2_5"
    OVER_3_5 = "OVER_3_5"
    UNDER_3_5 = "UNDER_3_5"
    BTTS_YES = "BTTS_YES"
    BTTS_NO = "BTTS_NO"


OFFICIAL_TARGET_ORDER = (
    PredictionTarget.HOME_WIN,
    PredictionTarget.DRAW,
    PredictionTarget.AWAY_WIN,
    PredictionTarget.OVER_1_5,
    PredictionTarget.UNDER_1_5,
    PredictionTarget.OVER_2_5,
    PredictionTarget.UNDER_2_5,
    PredictionTarget.OVER_3_5,
    PredictionTarget.UNDER_3_5,
    PredictionTarget.BTTS_YES,
    PredictionTarget.BTTS_NO,
)


class MissingValueSupport(str, Enum):
    NONE = "NONE"
    OPTIONAL_FEATURES = "OPTIONAL_FEATURES"


class InferenceGenerationStatus(str, Enum):
    GENERATED = "GENERATED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    REJECTED_INVALID_INPUT = "REJECTED_INVALID_INPUT"
    REJECTED_INCOMPATIBLE_MODEL = "REJECTED_INCOMPATIBLE_MODEL"
    REJECTED_INVALID_OUTPUT = "REJECTED_INVALID_OUTPUT"
    MODEL_EXECUTION_FAILED = "MODEL_EXECUTION_FAILED"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class ModelAdapterOutput:
    target: PredictionTarget | str
    value: object


@dataclass(frozen=True, slots=True)
class RawProbability:
    target: PredictionTarget
    probability: Decimal


@dataclass(frozen=True, slots=True)
class RawProbabilitySet:
    ordered_probabilities: tuple[RawProbability, ...]

    def probability_for(self, target: PredictionTarget) -> Decimal:
        for item in self.ordered_probabilities:
            if item.target is target:
                return item.probability
        raise KeyError(target.value)


@dataclass(frozen=True, slots=True)
class ProbabilityValidationCheck:
    code: str
    passed: bool
    observed_value: Decimal | None
    tolerance: Decimal | None


@dataclass(frozen=True, slots=True)
class InferenceValidationSummary:
    policy_version: str
    target_count: int
    ordered_checks: tuple[ProbabilityValidationCheck, ...]


@dataclass(frozen=True, slots=True)
class PredictionInferenceResult:
    inference_id: str
    model_input_id: str
    match_id: str
    source_snapshot_id: str
    source_feature_set_id: str
    model_artifact_id: str
    model_name: str
    model_version: str
    model_family: str
    input_schema_name: str
    input_schema_version: str
    compatibility_version: str
    policy_version: str
    inference_timestamp: datetime
    created_timestamp: datetime
    raw_probabilities: RawProbabilitySet
    validation_summary: InferenceValidationSummary
    model_input_fingerprint: str
    inference_fingerprint: str


@dataclass(frozen=True, slots=True)
class InferenceGenerationOutcome:
    inference_id: str | None
    model_input_id: str
    match_id: str
    model_artifact_id: str
    model_version: str
    inference_fingerprint: str | None
    final_status: InferenceGenerationStatus
    ordered_reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    raw_probability_set: RawProbabilitySet | None
    inference_timestamp: datetime
    policy_version: str


@dataclass(frozen=True, slots=True)
class RegisteredPredictionModel:
    model_artifact_id: str
    model_name: str
    model_version: str
    model_family: str
    input_schema_name: str
    input_schema_version: str
    compatibility_version: str
    supported_targets: tuple[PredictionTarget, ...]
    missing_value_support: MissingValueSupport
    adapter: "PredictionModelAdapter"


@dataclass(frozen=True, slots=True)
class PersistedModelInputIdentity:
    model_input_id: str
    feature_set_id: str
    snapshot_id: str
    match_id: str
    schema_name: str
    schema_version: str
    compatibility_version: str
    feature_fingerprint: str
    source_snapshot_fingerprint: str
    source_feature_fingerprint: str
    model_input_fingerprint: str
    effective_timestamp: datetime


@dataclass(frozen=True, slots=True)
class RawInferenceCalibrationInput:
    inference_id: str
    target: PredictionTarget
    raw_probability: Decimal
    model_artifact_id: str
    model_name: str
    model_version: str
    inference_timestamp: datetime
    inference_fingerprint: str
