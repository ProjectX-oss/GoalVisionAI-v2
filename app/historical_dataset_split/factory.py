"""Explicit composition without startup execution."""

from app.database import Database
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository

from .builder import HistoricalDatasetSplitter
from .policy import DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY, HistoricalDatasetSplitPolicy
from .repository import SQLiteHistoricalDatasetSplitRepository


def build_historical_dataset_split_service(
    database: Database,
    *,
    policy: HistoricalDatasetSplitPolicy = DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY,
    migrate: bool = True,
) -> HistoricalDatasetSplitter:
    training = SQLiteHistoricalTrainingDatasetRepository(database, migrate=migrate)
    splits = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    return HistoricalDatasetSplitter(training, splits, policy)
