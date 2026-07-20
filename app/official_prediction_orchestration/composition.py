from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from app.database import Database
from app.publication_quality_gate import (
    DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY,
    OfficialPublicationQualityGate,
    OfficialQualityGatePolicy,
    SQLiteQualityGateEvaluationRepository,
)

from .assembler import OfficialPredictionCandidateAssembler
from .fingerprint import OfficialCandidateFingerprint
from .ports import AtomicOfficialPredictionPublisher, OfficialPublicationStateReader
from .repositories import (
    SQLiteOfficialPublicationStateReader,
    SQLiteOrchestrationHistoryRepository,
)
from .service import OfficialPredictionOrchestrationService

if TYPE_CHECKING:
    from app.official_prediction_publication import (
        OfficialPredictionDestination,
        OfficialPredictionMessagePolicy,
        OfficialPredictionPublicFactsProvider,
        TelegramPredictionSender,
    )


def build_official_prediction_orchestration_service(
    database: Database,
    publisher: AtomicOfficialPredictionPublisher | None = None,
    *,
    publication_states: OfficialPublicationStateReader | None = None,
    policy: OfficialQualityGatePolicy = DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY,
    telegram: TelegramPredictionSender | None = None,
    public_facts: OfficialPredictionPublicFactsProvider | None = None,
    destination: OfficialPredictionDestination | None = None,
    clock: Callable[[], datetime] | None = None,
    message_policy: OfficialPredictionMessagePolicy | None = None,
) -> OfficialPredictionOrchestrationService:
    """Construct the callable production boundary without starting or scheduling it."""
    concrete_dependencies = (telegram, public_facts, destination, clock)
    if publisher is not None and any(item is not None for item in concrete_dependencies):
        raise ValueError(
            "Supply either an atomic publisher or concrete publication dependencies."
        )
    if publisher is None:
        if any(item is None for item in concrete_dependencies):
            raise ValueError(
                "Concrete publication requires Telegram, public facts, destination, and clock."
            )
        from app.official_prediction_publication import (
            DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY,
            build_official_prediction_publisher_adapter,
        )

        assert telegram is not None
        assert public_facts is not None
        assert destination is not None
        assert clock is not None
        publisher = build_official_prediction_publisher_adapter(
            database=database,
            telegram=telegram,
            public_facts=public_facts,
            destination=destination,
            clock=clock,
            policy=(
                message_policy
                if message_policy is not None
                else DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY
            ),
        )
    assert publisher is not None
    return OfficialPredictionOrchestrationService(
        assembler=OfficialPredictionCandidateAssembler(),
        fingerprint=OfficialCandidateFingerprint(),
        gate=OfficialPublicationQualityGate(policy),
        gate_evaluations=SQLiteQualityGateEvaluationRepository(database),
        history=SQLiteOrchestrationHistoryRepository(database, migrate=False),
        publication_states=(
            publication_states
            if publication_states is not None
            else SQLiteOfficialPublicationStateReader(database)
        ),
        publisher=publisher,
    )
