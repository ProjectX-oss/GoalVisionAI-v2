"""Deterministic historical model-training foundation."""

from .artifact import predict_raw_probabilities
from .factory import build_historical_model_training_service
from .inspection import (
    compare_reproduced_predictions, inspect_model_artifact, inspect_target_estimator,
    reproduce_training_metrics, summarize_training_run, verify_artifact_fingerprint,
    verify_estimator_fingerprints, verify_feature_compatibility,
    verify_preprocessing_train_only, verify_probability_contract,
    verify_training_partition_only,
)
from .models import (
    ArtifactPrediction, ArtifactTarget, EstimatorConfiguration, HistoricalModelTrainingCommand,
    ModelArtifact, TrainingOutcome, TrainingStatus,
)
from .policy import (
    ARTIFACT_FORMAT_VERSION, DEFAULT_MODEL_TRAINING_POLICY, DEFAULT_PREPROCESSING_POLICY,
    MODEL_FAMILY, MODEL_POLICY_VERSION, PREPROCESSING_POLICY_VERSION,
    TARGET_SCHEMA_VERSION, AllMissingFeaturePolicy, ClassWeightPolicy,
    MissingValuePolicy, ModelTrainingPolicy, PreprocessingPolicy, ScalingPolicy,
    ZeroVariancePolicy,
)
from .repository import SQLiteHistoricalModelTrainingRepository
from .trainer import HistoricalModelTrainer, train_historical_model
from .validation import FEATURE_NAMES, FEATURE_SCHEMA_FINGERPRINT

__all__ = [
    "ARTIFACT_FORMAT_VERSION", "ArtifactPrediction", "ArtifactTarget",
    "AllMissingFeaturePolicy", "ClassWeightPolicy", "DEFAULT_MODEL_TRAINING_POLICY",
    "DEFAULT_PREPROCESSING_POLICY", "EstimatorConfiguration", "FEATURE_NAMES",
    "FEATURE_SCHEMA_FINGERPRINT", "HistoricalModelTrainer", "HistoricalModelTrainingCommand",
    "MODEL_FAMILY", "MODEL_POLICY_VERSION", "MissingValuePolicy", "ModelArtifact",
    "ModelTrainingPolicy", "PREPROCESSING_POLICY_VERSION", "PreprocessingPolicy",
    "SQLiteHistoricalModelTrainingRepository", "ScalingPolicy", "TARGET_SCHEMA_VERSION",
    "TrainingOutcome", "TrainingStatus", "ZeroVariancePolicy",
    "build_historical_model_training_service", "compare_reproduced_predictions",
    "inspect_model_artifact", "inspect_target_estimator", "predict_raw_probabilities",
    "reproduce_training_metrics", "summarize_training_run", "train_historical_model",
    "verify_artifact_fingerprint", "verify_estimator_fingerprints",
    "verify_feature_compatibility", "verify_preprocessing_train_only",
    "verify_probability_contract", "verify_training_partition_only",
]
