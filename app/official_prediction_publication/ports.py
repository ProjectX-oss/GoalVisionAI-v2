from datetime import datetime
from typing import Protocol, runtime_checkable

from app.official_prediction_orchestration import (
    ApprovedOfficialPredictionPublication,
)
from app.results import PublishedPredictionReference

from .models import (
    OfficialPredictionPublicationPayload,
    OfficialPredictionPublicFacts,
    PredictionPublicationClaim,
    PredictionPublicationEvent,
    PredictionPublicationEventStatus,
    PredictionPublicationFailureReason,
)


@runtime_checkable
class OfficialPredictionPublicFactsProvider(Protocol):
    def get(
        self,
        approved: ApprovedOfficialPredictionPublication,
    ) -> OfficialPredictionPublicFacts | None: ...


@runtime_checkable
class TelegramPredictionSender(Protocol):
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = None,
    ) -> int | None: ...


@runtime_checkable
class PublishedPredictionWriter(Protocol):
    def save_published(
        self,
        prediction: PublishedPredictionReference,
    ) -> PublishedPredictionReference: ...


@runtime_checkable
class AtomicPredictionPublicationRepository(Protocol):
    def latest(
        self,
        prediction_id: str,
        destination_scope: str,
    ) -> PredictionPublicationEvent | None: ...

    def begin_attempt(
        self,
        payload: OfficialPredictionPublicationPayload,
        attempted_at: datetime,
    ) -> PredictionPublicationClaim: ...

    def append_terminal(
        self,
        attempt_reference: str,
        status: PredictionPublicationEventStatus,
        occurred_at: datetime,
        *,
        telegram_message_id: int | None = None,
        failure_reason: PredictionPublicationFailureReason | None = None,
    ) -> PredictionPublicationEvent: ...
