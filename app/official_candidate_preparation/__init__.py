"""Official selection-to-risk and candidate preparation integration."""

from .exceptions import (
    CandidatePreparationConflictError,
    CandidatePreparationMappingError,
    CandidatePreparationPersistenceError,
    CandidatePreparationProvenanceError,
    CandidatePreparationScopeError,
    CandidatePreparationValidationError,
    OfficialCandidatePreparationError,
)
from .factory import build_official_candidate_preparation_service
from .fingerprint import (
    bankroll_context_fingerprint,
    candidate_facts_fingerprint,
    exposure_context_fingerprint,
    preparation_request_fingerprint,
)
from .models import (
    CandidatePreparationReason,
    CandidatePreparationStatus,
    OfficialBankrollPreparationContext,
    OfficialCandidatePreparationCommand,
    OfficialCandidatePreparationExecution,
    OfficialCandidatePreparationOutcome,
    OfficialCandidatePreparationRiskSnapshot,
    OfficialCandidateQualityGateHandoff,
    OfficialCandidateRegistrationFacts,
    OfficialExposurePreparationContext,
    PreparationExecutionWithRiskSnapshot,
    PreparedOfficialCandidateRegistration,
    PreparedOfficialRiskHandoff,
)
from .policy import (
    DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY,
    OfficialCandidatePreparationPolicy,
)
from .repository import SQLiteOfficialCandidatePreparationRepository
from .service import OfficialCandidatePreparationService


def prepare_official_candidate(
    service: OfficialCandidatePreparationService,
    command: OfficialCandidatePreparationCommand,
) -> OfficialCandidatePreparationOutcome:
    """Invoke the explicit production boundary without hidden dependencies."""

    return service.prepare_official_candidate(command)


__all__ = [
    "CandidatePreparationConflictError",
    "CandidatePreparationMappingError",
    "CandidatePreparationPersistenceError",
    "CandidatePreparationProvenanceError",
    "CandidatePreparationReason",
    "CandidatePreparationScopeError",
    "CandidatePreparationStatus",
    "CandidatePreparationValidationError",
    "DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY",
    "OfficialBankrollPreparationContext",
    "OfficialCandidatePreparationCommand",
    "OfficialCandidatePreparationError",
    "OfficialCandidatePreparationExecution",
    "OfficialCandidatePreparationOutcome",
    "OfficialCandidatePreparationPolicy",
    "OfficialCandidatePreparationRiskSnapshot",
    "OfficialCandidatePreparationService",
    "OfficialCandidateQualityGateHandoff",
    "OfficialCandidateRegistrationFacts",
    "OfficialExposurePreparationContext",
    "PreparationExecutionWithRiskSnapshot",
    "PreparedOfficialCandidateRegistration",
    "PreparedOfficialRiskHandoff",
    "SQLiteOfficialCandidatePreparationRepository",
    "bankroll_context_fingerprint",
    "build_official_candidate_preparation_service",
    "candidate_facts_fingerprint",
    "exposure_context_fingerprint",
    "preparation_request_fingerprint",
    "prepare_official_candidate",
]
