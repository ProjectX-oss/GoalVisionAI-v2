"""Deterministic, append-only historical match import foundation.

Importing this package performs no provider access, scheduling, database work,
prediction work, or Telegram activity.
"""

from .exceptions import (
    HistoricalDataImportError,
    HistoricalDatasetValidationError,
    HistoricalImportConflictError,
    HistoricalImportPersistenceError,
)
from .factory import build_historical_match_importer
from .importer import HistoricalMatchImporter
from .mapping import map_provider_dataset
from .models import (
    FullTimeResult,
    HistoricalDataset,
    HistoricalImportResult,
    HistoricalImportStatus,
    HistoricalLineupInput,
    HistoricalMatchInput,
    HistoricalTeamStatisticsInput,
    NormalizedHistoricalLineup,
    NormalizedHistoricalMatch,
    NormalizedHistoricalStatistics,
    PreparedHistoricalDataset,
    PreparedHistoricalMatch,
    StoredHistoricalLineup,
    StoredHistoricalMatch,
    StoredHistoricalStatistics,
    TeamSide,
)
from .normalization import (
    normalize_identity,
    normalize_text,
    normalize_utc,
    prepare_historical_dataset,
)
from .policy import (
    DEFAULT_HISTORICAL_IMPORT_POLICY,
    HISTORICAL_DATASET_SCHEMA,
    HistoricalImportPolicy,
)
from .ports import HistoricalImportRepository, HistoricalImportService
from .repository import SQLiteHistoricalMatchRepository

__all__ = [
    "DEFAULT_HISTORICAL_IMPORT_POLICY",
    "FullTimeResult",
    "HISTORICAL_DATASET_SCHEMA",
    "HistoricalDataImportError",
    "HistoricalDataset",
    "HistoricalDatasetValidationError",
    "HistoricalImportConflictError",
    "HistoricalImportPersistenceError",
    "HistoricalImportPolicy",
    "HistoricalImportResult",
    "HistoricalImportRepository",
    "HistoricalImportService",
    "HistoricalImportStatus",
    "HistoricalLineupInput",
    "HistoricalMatchImporter",
    "HistoricalMatchInput",
    "HistoricalTeamStatisticsInput",
    "NormalizedHistoricalLineup",
    "NormalizedHistoricalMatch",
    "NormalizedHistoricalStatistics",
    "PreparedHistoricalDataset",
    "PreparedHistoricalMatch",
    "SQLiteHistoricalMatchRepository",
    "StoredHistoricalLineup",
    "StoredHistoricalMatch",
    "StoredHistoricalStatistics",
    "TeamSide",
    "build_historical_match_importer",
    "map_provider_dataset",
    "normalize_identity",
    "normalize_text",
    "normalize_utc",
    "prepare_historical_dataset",
]
