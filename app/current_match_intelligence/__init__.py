"""Deterministic, provider-backed current pre-match intelligence."""

from .features import FEATURE_ORDER, future_feature_vector
from .lab import RealMatchLabIntelligenceBridge
from .models import (
    FUTURE_FEATURE_CONTRACT,
    SCHEMA_VERSION,
    CurrentMatchIntelligenceSnapshot,
    DataClass,
    EnrichmentResult,
    FieldProvenance,
    FreshnessStatus,
    FutureFeatureVector,
    IntelligenceField,
)
from .policy import IntelligenceBudgetPolicy, IntelligenceFreshnessPolicy
from .provider import ApiFootballCurrentMatchProvider, CurrentMatchProvider
from .repository import SQLiteCurrentMatchIntelligenceRepository
from .service import CurrentMatchIntelligenceService, enrich_discovery_result

__all__ = (
    "ApiFootballCurrentMatchProvider", "CurrentMatchIntelligenceService",
    "CurrentMatchIntelligenceSnapshot", "CurrentMatchProvider", "DataClass",
    "EnrichmentResult", "FEATURE_ORDER", "FUTURE_FEATURE_CONTRACT",
    "FieldProvenance", "FreshnessStatus", "FutureFeatureVector",
    "IntelligenceBudgetPolicy", "IntelligenceField",
    "IntelligenceFreshnessPolicy", "RealMatchLabIntelligenceBridge",
    "SCHEMA_VERSION", "SQLiteCurrentMatchIntelligenceRepository",
    "enrich_discovery_result", "future_feature_vector",
)
