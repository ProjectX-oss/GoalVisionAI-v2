"""Explicit composition without startup execution."""

from app.database import Database

from .builder import HistoricalTrainingDatasetBuilder
from .policy import DEFAULT_HISTORICAL_TRAINING_POLICY, HistoricalTrainingDatasetPolicy
from .repository import SQLiteHistoricalTrainingDatasetRepository, SQLiteHistoricalTrainingSourceRepository


def build_historical_training_dataset_service(
    database: Database,
    *,
    policy: HistoricalTrainingDatasetPolicy = DEFAULT_HISTORICAL_TRAINING_POLICY,
    migrate: bool = True,
) -> HistoricalTrainingDatasetBuilder:
    source = SQLiteHistoricalTrainingSourceRepository(database, migrate=migrate)
    repository = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
    return HistoricalTrainingDatasetBuilder(source, repository, policy)
