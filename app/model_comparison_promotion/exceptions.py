"""Typed failures for model comparison and recommendation."""


class ModelComparisonError(Exception):
    """Base class for comparison failures."""


class ComparisonValidationError(ModelComparisonError, ValueError):
    """The immutable request is malformed."""


class ComparisonConflictError(ModelComparisonError):
    """A request identity was reused with different immutable content."""


class ComparisonSourceError(ModelComparisonError):
    """A referenced immutable source cannot be trusted."""


class ComparisonPersistenceError(ModelComparisonError):
    """The complete comparison could not be persisted atomically."""
