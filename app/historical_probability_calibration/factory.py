"""Explicit composition without startup fitting or activation."""

from app.database import Database
from app.historical_dataset_split import SQLiteHistoricalDatasetSplitRepository
from app.historical_model_training import SQLiteHistoricalModelTrainingRepository
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository

from .policy import DEFAULT_HISTORICAL_CALIBRATION_POLICY
from .repository import SQLiteHistoricalProbabilityCalibrationRepository
from .service import HistoricalProbabilityCalibrationService


def build_historical_probability_calibration_service(database: Database, *, policy=DEFAULT_HISTORICAL_CALIBRATION_POLICY, migrate=True):
    models = SQLiteHistoricalModelTrainingRepository(database, migrate=migrate)
    splits = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    training = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
    calibrations = SQLiteHistoricalProbabilityCalibrationRepository(database, migrate=False)
    return HistoricalProbabilityCalibrationService(models, splits, training, calibrations, policy)
