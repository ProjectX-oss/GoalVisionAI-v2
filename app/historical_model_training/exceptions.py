"""Typed failures for historical model training."""


class HistoricalModelTrainingError(Exception):
    """Base failure."""


class TrainingRequestValidationError(HistoricalModelTrainingError):
    """The immutable command is invalid."""


class SourceSplitError(HistoricalModelTrainingError):
    """The requested split or fold cannot be trusted."""


class PartitionSafetyError(HistoricalModelTrainingError):
    """Partition isolation or chronology failed."""


class FeatureSchemaError(HistoricalModelTrainingError):
    """A feature vector is incompatible or malformed."""


class LabelSchemaError(HistoricalModelTrainingError):
    """A target label is incompatible or malformed."""


class InsufficientExamplesError(HistoricalModelTrainingError):
    """There are too few fitting examples."""


class InsufficientClassSupportError(HistoricalModelTrainingError):
    """A required estimator class is absent."""


class PreprocessingError(HistoricalModelTrainingError):
    """Deterministic preprocessing failed."""


class EstimatorConvergenceError(HistoricalModelTrainingError):
    """An estimator did not satisfy the convergence policy."""


class InvalidProbabilityError(HistoricalModelTrainingError):
    """Raw outputs violate the canonical probability contract."""


class TrainingConflictError(HistoricalModelTrainingError):
    """An immutable request identity has different content."""


class TrainingPersistenceError(HistoricalModelTrainingError):
    """The atomic append failed."""
