from datetime import datetime
from typing import Protocol, runtime_checkable

from .models import (
    CandidateLifecycleEvent,
    CandidatePublicationGuardState,
    CandidateVersionRegistration,
    OfficialCandidateAssemblyContext,
    OfficialPredictionCandidateVersion,
    PreparedOfficialPredictionCandidate,
)


@runtime_checkable
class OfficialCandidatePublicationGuard(Protocol):
    def state(
        self,
        prediction_id: str,
        match_id: str,
        evaluated_at: datetime,
    ) -> CandidatePublicationGuardState: ...


@runtime_checkable
class OfficialPredictionCandidateRepository(Protocol):
    def register_candidate_version(
        self,
        candidate: PreparedOfficialPredictionCandidate,
    ) -> CandidateVersionRegistration: ...

    def find_by_content_fingerprint(
        self,
        content_fingerprint: str,
    ) -> OfficialPredictionCandidateVersion | None: ...

    def find_active_ready_by_logical_identity(
        self,
        logical_identity_fingerprint: str,
    ) -> OfficialPredictionCandidateVersion | None: ...

    def find_candidate_by_id(
        self,
        registry_candidate_id: str,
    ) -> OfficialPredictionCandidateVersion | None: ...

    def list_candidate_versions(
        self,
        logical_identity_fingerprint: str,
    ) -> tuple[OfficialPredictionCandidateVersion, ...]: ...

    def append_lifecycle_event(
        self,
        event: CandidateLifecycleEvent,
    ) -> CandidateLifecycleEvent: ...

    def withdraw_candidate(
        self,
        registry_candidate_id: str,
        reason_code: str,
        event_timestamp: datetime,
    ) -> CandidateLifecycleEvent: ...

    def invalidate_candidate(
        self,
        registry_candidate_id: str,
        reason_code: str,
        event_timestamp: datetime,
    ) -> CandidateLifecycleEvent: ...

    def discover_ready_candidates(
        self,
        evaluated_at: datetime,
        normalized_filters: tuple[tuple[str, str], ...] = (),
    ) -> tuple[OfficialPredictionCandidateVersion, ...]: ...


@runtime_checkable
class OfficialCandidateAssemblyContextProvider(Protocol):
    """Reads existing immutable orchestration dependencies without calculating them."""

    def load(
        self,
        candidate: OfficialPredictionCandidateVersion,
        evaluated_at: datetime,
    ) -> OfficialCandidateAssemblyContext: ...
