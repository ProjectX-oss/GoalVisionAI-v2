"""Explicit composition; importing or starting never trains a model."""

from app.database import Database
from app.historical_dataset_split import SQLiteHistoricalDatasetSplitRepository
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository

from .policy import (
    DEFAULT_MODEL_TRAINING_POLICY, DEFAULT_PREPROCESSING_POLICY, ModelTrainingPolicy,
    PreprocessingPolicy,
)
from .repository import SQLiteHistoricalModelTrainingRepository
from .trainer import HistoricalModelTrainer


def build_historical_model_training_service(
    database: Database,
    *,
    preprocessing_policy: PreprocessingPolicy = DEFAULT_PREPROCESSING_POLICY,
    model_policy: ModelTrainingPolicy = DEFAULT_MODEL_TRAINING_POLICY,
    migrate: bool = True,
) -> HistoricalModelTrainer:
    training = SQLiteHistoricalTrainingDatasetRepository(database, migrate=migrate)
    splits = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    models = SQLiteHistoricalModelTrainingRepository(database, migrate=False)
    return HistoricalModelTrainer(training, splits, models, preprocessing_policy, model_policy)
