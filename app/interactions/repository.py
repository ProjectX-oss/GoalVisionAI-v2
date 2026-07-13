from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.explanations import PredictionExplanation


@dataclass(frozen=True, slots=True)
class StoredAssessmentExplanation:
    assessment_id: str
    explanation: PredictionExplanation | None
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None:
            raise ValueError("Assessment expiry must be timezone-aware.")


class AssessmentExplanationLookup(Protocol):
    def get(
        self,
        assessment_id: str,
    ) -> StoredAssessmentExplanation | None:
        """Return stored explanation data without recalculating it."""
        ...


class InMemoryAssessmentExplanationRepository:
    """Small repository implementation for tests and future composition."""

    def __init__(self) -> None:
        self._records: dict[str, StoredAssessmentExplanation] = {}

    def save(self, record: StoredAssessmentExplanation) -> None:
        self._records[record.assessment_id] = record

    def get(
        self,
        assessment_id: str,
    ) -> StoredAssessmentExplanation | None:
        return self._records.get(assessment_id)
