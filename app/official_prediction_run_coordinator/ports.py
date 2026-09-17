from datetime import datetime
from typing import Protocol, runtime_checkable

from app.official_prediction_orchestration import (
    OfficialCandidateAssemblyRequest,
    OfficialPredictionOrchestrationOutcome,
)

from .models import (
    CandidateHistoricalState,
    OfficialPredictionCandidateReference,
    OfficialPredictionDiscoveryResult,
    OfficialPredictionRunClaim,
    OfficialPredictionRunItemResult,
    OfficialPredictionRunRequest,
    OfficialPredictionRunResult,
    OfficialPredictionRunStart,
)
from .policy import OfficialPredictionRunPolicy


@runtime_checkable
class PersistedOfficialPredictionCandidateSource(Protocol):
    """Read-only source of complete immutable persisted orchestration inputs."""

    def load_candidates(
        self,
        evaluated_at: datetime,
        normalized_filters: tuple[tuple[str, str], ...],
    ) -> tuple[OfficialPredictionCandidateReference, ...]: ...


@runtime_checkable
class OfficialCandidateHistoricalStateReader(Protocol):
    def get(
        self,
        candidate: OfficialPredictionCandidateReference,
        evaluated_at: datetime,
    ) -> CandidateHistoricalState: ...


@runtime_checkable
class OfficialPredictionCandidateDiscovery(Protocol):
    def discover(
        self,
        request: OfficialPredictionRunRequest,
        policy: OfficialPredictionRunPolicy,
    ) -> OfficialPredictionDiscoveryResult: ...


@runtime_checkable
class OfficialSinglePredictionOrchestrator(Protocol):
    async def prepare_and_publish_official_prediction(
        self,
        request: OfficialCandidateAssemblyRequest,
    ) -> OfficialPredictionOrchestrationOutcome: ...


@runtime_checkable
class OfficialPredictionRunRepository(Protocol):
    def begin_run(self, start: OfficialPredictionRunStart) -> OfficialPredictionRunClaim: ...

    def append_item(
        self,
        item: OfficialPredictionRunItemResult,
    ) -> OfficialPredictionRunItemResult: ...

    def finalize_run(
        self,
        result: OfficialPredictionRunResult,
    ) -> OfficialPredictionRunResult: ...

    def load_by_fingerprint(
        self,
        run_fingerprint: str,
    ) -> OfficialPredictionRunClaim | None: ...

    def load_complete_run(self, run_id: str) -> OfficialPredictionRunResult | None: ...
