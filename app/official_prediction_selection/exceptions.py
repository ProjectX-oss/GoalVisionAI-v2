"""Selection-domain validation and persistence errors."""

from .models import SelectionReason


class OfficialPredictionSelectionError(Exception):
    """Base package error."""


class InvalidSelectionRequestError(OfficialPredictionSelectionError, ValueError):
    def __init__(self, reason: SelectionReason, explanation: str) -> None:
        super().__init__(explanation)
        self.reason = reason
        self.explanation = explanation


class SelectionProvenanceError(OfficialPredictionSelectionError, ValueError):
    def __init__(self, reason: SelectionReason, explanation: str) -> None:
        super().__init__(explanation)
        self.reason = reason
        self.explanation = explanation


class SelectionScopeError(OfficialPredictionSelectionError, ValueError):
    def __init__(self, reason: SelectionReason, explanation: str) -> None:
        super().__init__(explanation)
        self.reason = reason
        self.explanation = explanation


class SelectionConflictError(OfficialPredictionSelectionError):
    """An immutable request or fingerprint conflicts with stored history."""


class SelectionPersistenceError(OfficialPredictionSelectionError):
    """Selection history could not be read or atomically appended."""


class SelectionMappingError(OfficialPredictionSelectionError, ValueError):
    """Only successful selected decisions can cross the risk handoff."""
