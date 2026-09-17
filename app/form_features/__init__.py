from .config import FORM_FEATURE_INGESTION_ENABLED, FormFeatureIngestionConfig
from .ingestion import HistoricalMatchIngestionService
from .integrations import (
    FormBacktestingAdapter,
    FormQualityGateAdapter,
    FormQualityGateEvidence,
    FormShadowFactsProvider,
)
from .models import *
from .normalization import decimal_or_none, normalize_identifier, normalize_source, normalize_text
from .providers import (
    ExistingFootballHistoricalAdapter,
    HistoricalMatchProvider,
    HistoricalMatchProviderBatch,
    NullHistoricalMatchProvider,
    StaticHistoricalMatchProvider,
)
from .repository import SQLiteFormFeatureRepository
from .runtime import FormFeatureRuntime, build_form_feature_runtime
from .snapshot import FormSnapshotBuilder

__all__ = [name for name in globals() if not name.startswith("_")]
