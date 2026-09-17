"""Typed failures for controlled historical match imports."""


class HistoricalDataImportError(Exception):
    """Base exception for the historical import boundary."""


class HistoricalDatasetValidationError(HistoricalDataImportError, ValueError):
    """The supplied dataset cannot be normalized safely."""


class HistoricalImportConflictError(HistoricalDataImportError):
    """Immutable stored history conflicts with the supplied import."""


class HistoricalImportPersistenceError(HistoricalDataImportError):
    """The atomic append transaction could not be completed."""
