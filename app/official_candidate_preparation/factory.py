"""Production composition for Official candidate preparation."""

from .policy import OfficialCandidatePreparationPolicy
from .ports import (
    CandidateLifecycleReader,
    OfficialCandidatePreparationRepository,
    OfficialCandidateRegistryPort,
    OfficialRiskAssessmentPort,
    SelectionHistoryReader,
    ValueAssessmentHistoryReader,
)
from .service import OfficialCandidatePreparationService


def build_official_candidate_preparation_service(
    *,
    preparation_repository: OfficialCandidatePreparationRepository,
    selection_repository: SelectionHistoryReader,
    value_assessment_repository: ValueAssessmentHistoryReader,
    risk_service: OfficialRiskAssessmentPort,
    candidate_registry: OfficialCandidateRegistryPort,
    candidate_lifecycle: CandidateLifecycleReader,
    policy: OfficialCandidatePreparationPolicy,
) -> OfficialCandidatePreparationService:
    """Compose only explicitly supplied deterministic production boundaries."""

    return OfficialCandidatePreparationService(
        repository=preparation_repository,
        selections=selection_repository,
        assessments=value_assessment_repository,
        risk_service=risk_service,
        candidate_registry=candidate_registry,
        candidate_lifecycle=candidate_lifecycle,
        policy=policy,
    )
