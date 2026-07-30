"""Deterministic, leakage-safe historical training dataset foundation."""

from .builder import HistoricalTrainingDatasetBuilder, build_historical_training_dataset
from .chronology import assert_source_precedes_target, verify_sources_strictly_prior
from .exceptions import (
    DatasetBuildConflictError, DatasetPersistenceError, DatasetRequestValidationError,
    HistoricalTrainingDatasetError, SourceProvenanceError, TemporalLeakageError,
)
from .factory import build_historical_training_dataset_service
from .feature_projection import HISTORICAL_TRAINING_FEATURES_V1, build_feature_definitions, project_features
from .live_feature_projection import FeatureCoverage, live_feature_coverage, project_live_features
from .inspection import (
    inspect_training_example, summarize_dataset, verify_dataset_fingerprints,
    verify_label_consistency, verify_no_temporal_leakage,
)
from .labels import LABEL_ORDER, generate_labels, validate_labels
from .models import (
    DatasetBuildCommand, DatasetBuildOutcome, DatasetBuildStatus, DatasetSummary,
    ExclusionReason, FeatureDataType, HistoricalFeatureDefinition, HistoricalSourceMatch,
    HistoricalTrainingExample, HistoricalTrainingExclusion, LeakageReason,
    PreparedDatasetBuild, TrainingExampleSource,
)
from .policy import (
    CUTOFF_POLICY, DATASET_POLICY_VERSION, DEFAULT_HISTORICAL_TRAINING_POLICY,
    FEATURE_SCHEMA_VERSION, LABEL_SCHEMA_VERSION, METADATA_VERSION,
    HistoricalTrainingDatasetPolicy, LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
)
from .repository import SQLiteHistoricalTrainingDatasetRepository, SQLiteHistoricalTrainingSourceRepository

__all__ = [
    "CUTOFF_POLICY", "DATASET_POLICY_VERSION", "DEFAULT_HISTORICAL_TRAINING_POLICY",
    "DatasetBuildCommand", "DatasetBuildConflictError", "DatasetBuildOutcome",
    "DatasetBuildStatus", "DatasetPersistenceError", "DatasetRequestValidationError",
    "DatasetSummary", "ExclusionReason", "FEATURE_SCHEMA_VERSION", "FeatureDataType",
    "HISTORICAL_TRAINING_FEATURES_V1", "HistoricalFeatureDefinition", "HistoricalSourceMatch",
    "HistoricalTrainingDatasetBuilder", "HistoricalTrainingDatasetError",
    "HistoricalTrainingDatasetPolicy", "HistoricalTrainingExample", "HistoricalTrainingExclusion",
    "LABEL_ORDER", "LABEL_SCHEMA_VERSION", "LeakageReason", "METADATA_VERSION",
    "LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY", "FeatureCoverage",
    "PreparedDatasetBuild", "SQLiteHistoricalTrainingDatasetRepository",
    "SQLiteHistoricalTrainingSourceRepository", "SourceProvenanceError", "TemporalLeakageError",
    "TrainingExampleSource", "assert_source_precedes_target", "build_feature_definitions",
    "build_historical_training_dataset", "build_historical_training_dataset_service",
    "generate_labels", "inspect_training_example", "live_feature_coverage",
    "project_features", "project_live_features", "summarize_dataset",
    "validate_labels", "verify_dataset_fingerprints", "verify_label_consistency",
    "verify_no_temporal_leakage", "verify_sources_strictly_prior",
]
