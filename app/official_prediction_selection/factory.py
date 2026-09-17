"""Explicit production composition for Official prediction selection."""

from app.market_value_assessment import MarketMappingRegistry

from .policy import (
    OfficialPredictionRankingPolicy,
    OfficialPredictionSelectionPolicy,
)
from .ports import (
    OfficialPredictionSelectionRepository,
    PersistedMarketValueAssessmentReader,
    PublicationStateProtection,
)
from .service import OfficialPredictionSelectionService


def build_official_prediction_selection_service(
    selection_repository: OfficialPredictionSelectionRepository,
    selection_policy: OfficialPredictionSelectionPolicy,
    ranking_policy: OfficialPredictionRankingPolicy,
    publication_state_protection: PublicationStateProtection,
    value_assessment_repository: PersistedMarketValueAssessmentReader | None = None,
    market_mapping_registry: MarketMappingRegistry | None = None,
) -> OfficialPredictionSelectionService:
    """Build the side-effect-free service with explicit durable dependencies."""

    assessment_reader = (
        value_assessment_repository
        if value_assessment_repository is not None
        else selection_repository
    )
    return OfficialPredictionSelectionService(
        repository=selection_repository,
        assessments=assessment_reader,
        publication_states=publication_state_protection,
        mappings=market_mapping_registry or MarketMappingRegistry(),
        selection_policy=selection_policy,
        ranking_policy=ranking_policy,
    )
