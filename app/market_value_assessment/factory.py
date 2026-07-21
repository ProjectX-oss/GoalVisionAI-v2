"""Explicit production composition boundary."""

from .market_mapping import MarketMappingRegistry
from .policy import MarketValueAssessmentPolicy
from .ports import MarketValueRepository
from .service import MarketValueAssessmentService


def build_market_value_assessment_service(
    odds_repository: MarketValueRepository,
    value_assessment_repository: MarketValueRepository,
    market_mapping_registry: MarketMappingRegistry,
    policy: MarketValueAssessmentPolicy,
) -> MarketValueAssessmentService:
    """Build the service without activating providers or performing work."""

    if odds_repository is not value_assessment_repository:
        raise ValueError(
            "Atomic v1 persistence requires one shared repository transaction boundary."
        )
    if market_mapping_registry.version != policy.mapping_version:
        raise ValueError("Mapping and policy versions differ.")
    return MarketValueAssessmentService(
        value_assessment_repository,
        market_mapping_registry,
        policy,
    )
