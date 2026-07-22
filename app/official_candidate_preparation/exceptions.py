"""Candidate-preparation validation and persistence errors."""

from .models import CandidatePreparationReason


class OfficialCandidatePreparationError(Exception):
    """Base candidate-preparation error."""


class CandidatePreparationValidationError(
    OfficialCandidatePreparationError, ValueError
):
    def __init__(self, reason: CandidatePreparationReason, explanation: str) -> None:
        super().__init__(explanation)
        self.reason = reason
        self.explanation = explanation


class CandidatePreparationProvenanceError(
    OfficialCandidatePreparationError, ValueError
):
    def __init__(self, reason: CandidatePreparationReason, explanation: str) -> None:
        super().__init__(explanation)
        self.reason = reason
        self.explanation = explanation


class CandidatePreparationScopeError(
    OfficialCandidatePreparationError, ValueError
):
    def __init__(self, reason: CandidatePreparationReason, explanation: str) -> None:
        super().__init__(explanation)
        self.reason = reason
        self.explanation = explanation


class CandidatePreparationConflictError(OfficialCandidatePreparationError):
    """An immutable request identity conflicts with existing history."""


class CandidatePreparationPersistenceError(OfficialCandidatePreparationError):
    """Candidate-preparation audit persistence failed."""


class CandidatePreparationMappingError(
    OfficialCandidatePreparationError, ValueError
):
    """A result cannot cross the requested downstream mapping boundary."""
