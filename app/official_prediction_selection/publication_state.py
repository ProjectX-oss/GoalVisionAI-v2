"""Adapter over the existing read-only candidate publication guard."""

from datetime import datetime

from app.official_prediction_candidate_registry import (
    CandidatePublicationGuardState,
)
from app.official_prediction_candidate_registry.ports import (
    OfficialCandidatePublicationGuard,
)

from .models import PublicationProtectionState


class CandidatePublicationStateProtectionAdapter:
    """Reuse durable publication logic without claiming or changing history."""

    def __init__(self, guard: OfficialCandidatePublicationGuard) -> None:
        self._guard = guard

    def classify(
        self,
        logical_prediction_identity: str,
        match_id: str,
        evaluated_at: datetime,
    ) -> PublicationProtectionState:
        state = self._guard.state(
            logical_prediction_identity,
            match_id,
            evaluated_at,
        )
        return {
            CandidatePublicationGuardState.UNPUBLISHED: (
                PublicationProtectionState.NOT_PUBLISHED
            ),
            CandidatePublicationGuardState.PUBLISHED: (
                PublicationProtectionState.PUBLISHED
            ),
            CandidatePublicationGuardState.ACTIVE_CLAIM: (
                PublicationProtectionState.ACTIVE_CLAIM
            ),
            CandidatePublicationGuardState.INDETERMINATE: (
                PublicationProtectionState.INDETERMINATE
            ),
            CandidatePublicationGuardState.UNKNOWN: (
                PublicationProtectionState.UNKNOWN
            ),
        }[state]
