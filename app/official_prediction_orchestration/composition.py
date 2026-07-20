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


def build_official_prediction_orchestration_service(
    database: Database,
    publisher: AtomicOfficialPredictionPublisher,
    *,
    publication_states: OfficialPublicationStateReader | None = None,
    policy: OfficialQualityGatePolicy = DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY,
) -> OfficialPredictionOrchestrationService:
    """Construct the callable production boundary without starting or scheduling it."""
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
