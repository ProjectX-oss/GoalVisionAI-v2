"""Explicit versioned model-training policy."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


MODEL_FAMILY = "MULTI_TARGET_LOGISTIC_REGRESSION_V1"
MODEL_POLICY_VERSION = "historical_model_training_policy_v1"
PREPROCESSING_POLICY_VERSION = "historical_model_preprocessing_v1"
TARGET_SCHEMA_VERSION = "historical_raw_market_targets_v1"
ARTIFACT_FORMAT_VERSION = "goalvision_safe_model_artifact_v1"
METADATA_VERSION = "v1"


class MissingValuePolicy(str, Enum):
    DETERMINISTIC_MEDIAN_IMPUTATION_V1 = "DETERMINISTIC_MEDIAN_IMPUTATION_V1"
    REJECT_ANY_MISSING_V1 = "REJECT_ANY_MISSING_V1"


class ScalingPolicy(str, Enum):
    STANDARD_SCALING_V1 = "STANDARD_SCALING_V1"


class AllMissingFeaturePolicy(str, Enum):
    REJECT = "REJECT"
    CONSTANT_ZERO = "CONSTANT_ZERO"


class ZeroVariancePolicy(str, Enum):
    UNIT_SCALE = "UNIT_SCALE"


class ClassWeightPolicy(str, Enum):
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class PreprocessingPolicy:
    version: str = PREPROCESSING_POLICY_VERSION
    missing_value_policy: MissingValuePolicy = MissingValuePolicy.DETERMINISTIC_MEDIAN_IMPUTATION_V1
    scaling_policy: ScalingPolicy = ScalingPolicy.STANDARD_SCALING_V1
    all_missing_feature_policy: AllMissingFeaturePolicy = AllMissingFeaturePolicy.REJECT
    zero_variance_policy: ZeroVariancePolicy = ZeroVariancePolicy.UNIT_SCALE
    append_missingness_indicators: bool = False


@dataclass(frozen=True, slots=True)
class ModelTrainingPolicy:
    version: str = MODEL_POLICY_VERSION
    model_family: str = MODEL_FAMILY
    solver: str = "DETERMINISTIC_BATCH_GRADIENT_DESCENT_V1"
    regularization: Decimal = Decimal("0.001")
    learning_rate: Decimal = Decimal("0.05")
    maximum_iterations: int = 1000
    convergence_tolerance: Decimal = Decimal("0.0001")
    probability_tolerance: Decimal = Decimal("0.000001")
    classification_threshold: Decimal = Decimal("0.5")
    class_weight_policy: ClassWeightPolicy = ClassWeightPolicy.NONE
    minimum_training_examples: int = 4

    def __post_init__(self) -> None:
        if self.model_family != MODEL_FAMILY:
            raise ValueError("Unsupported model family.")
        if self.solver != "DETERMINISTIC_BATCH_GRADIENT_DESCENT_V1":
            raise ValueError("Unsupported solver.")
        if self.regularization < 0 or self.learning_rate <= 0:
            raise ValueError("Invalid regularization or learning rate.")
        if self.maximum_iterations < 1 or self.convergence_tolerance <= 0:
            raise ValueError("Invalid convergence configuration.")
        if self.minimum_training_examples < 1:
            raise ValueError("Minimum training examples must be positive.")


DEFAULT_PREPROCESSING_POLICY = PreprocessingPolicy()
DEFAULT_MODEL_TRAINING_POLICY = ModelTrainingPolicy()
