"""Composition helpers for the historical import boundary."""

from app.database import Database

from .importer import HistoricalMatchImporter
from .policy import DEFAULT_HISTORICAL_IMPORT_POLICY, HistoricalImportPolicy
from .repository import SQLiteHistoricalMatchRepository


def build_historical_match_importer(
    database: Database,
    *,
    migrate: bool = True,
    policy: HistoricalImportPolicy = DEFAULT_HISTORICAL_IMPORT_POLICY,
) -> HistoricalMatchImporter:
    return HistoricalMatchImporter(
        SQLiteHistoricalMatchRepository(database, migrate=migrate),
        policy,
    )
