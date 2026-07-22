"""Typed failures for historical training dataset construction."""


class HistoricalTrainingDatasetError(Exception):
    """Base error for the historical training dataset boundary."""


class DatasetRequestValidationError(HistoricalTrainingDatasetError):
    """The immutable build command is invalid or unsupported."""


class SourceProvenanceError(HistoricalTrainingDatasetError):
    """Selected historical imports cannot prove complete immutable provenance."""


class DatasetBuildConflictError(HistoricalTrainingDatasetError):
    """An immutable request identity already represents different content."""


class DatasetPersistenceError(HistoricalTrainingDatasetError):
    """Atomic dataset persistence failed."""


class TemporalLeakageError(HistoricalTrainingDatasetError):
    """A source is not provably earlier than its target."""
