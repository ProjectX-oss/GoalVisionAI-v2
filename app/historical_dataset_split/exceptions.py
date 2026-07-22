"""Typed failures for immutable historical dataset splitting."""


class HistoricalDatasetSplitError(Exception):
    """Base split-domain error."""


class SplitRequestValidationError(HistoricalDatasetSplitError):
    """The immutable split command is invalid or unsupported."""


class SourceDatasetVerificationError(HistoricalDatasetSplitError):
    """The source dataset failed independent integrity verification."""


class SplitChronologyError(HistoricalDatasetSplitError):
    """A fold violates chronology, grouping, or exclusivity."""


class SplitPartitionSizeError(HistoricalDatasetSplitError):
    """A required partition is smaller than its explicit minimum."""


class DatasetSplitConflictError(HistoricalDatasetSplitError):
    """An immutable request identity already represents different content."""


class DatasetSplitPersistenceError(HistoricalDatasetSplitError):
    """The atomic split persistence transaction failed."""
