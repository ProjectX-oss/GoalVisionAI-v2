from datetime import datetime
from typing import Protocol, runtime_checkable

from .models import (
    ApprovedOfficialPredictionPublication,
    OfficialPredictionOrchestrationRecord,
    OfficialPredictionPublicationResult,
    PublicationStateRecord,
)


@runtime_checkable
class OfficialPublicationStateReader(Protocol):
    def get(
        self,
        prediction_id: str,
        match_id: str,
        evaluated_at: datetime,
    ) -> PublicationStateRecord: ...


@runtime_checkable
class AtomicOfficialPredictionPublisher(Protocol):
    """Existing atomic publisher retains all claim and Telegram-send ownership."""

    @property
    def enabled(self) -> bool: ...

    async def publish(
        self,
        approved: ApprovedOfficialPredictionPublication,
    ) -> OfficialPredictionPublicationResult: ...


@runtime_checkable
class OrchestrationHistoryRepository(Protocol):
    def append(
        self,
        record: OfficialPredictionOrchestrationRecord,
    ) -> OfficialPredictionOrchestrationRecord: ...

    def get(self, orchestration_id: str) -> OfficialPredictionOrchestrationRecord | None: ...

    def latest_for_fingerprint(
        self,
        prediction_id: str,
        candidate_fingerprint: str,
        dry_run: bool,
    ) -> OfficialPredictionOrchestrationRecord | None: ...

    def history_for_prediction(
        self,
        prediction_id: str,
    ) -> tuple[OfficialPredictionOrchestrationRecord, ...]: ...
