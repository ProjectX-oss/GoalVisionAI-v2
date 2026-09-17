"""Explicit composition with no startup execution or external access."""

from app.database import Database
from app.historical_dataset_split import SQLiteHistoricalDatasetSplitRepository
from app.historical_model_training import SQLiteHistoricalModelTrainingRepository
from app.historical_probability_calibration import (
    SQLiteHistoricalProbabilityCalibrationRepository,
)
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository

from .policy import DEFAULT_HISTORICAL_BACKTEST_POLICY
from .repository import SQLiteHistoricalBacktestingRepository
from .service import HistoricalBacktestingService
from .settlement import SQLiteHistoricalFinalScoreReader


def build_historical_backtesting_service(
    database: Database, *, policy=DEFAULT_HISTORICAL_BACKTEST_POLICY, migrate=True,
):
    training = SQLiteHistoricalTrainingDatasetRepository(database, migrate=migrate)
    splits = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    models = SQLiteHistoricalModelTrainingRepository(database, migrate=False)
    calibrations = SQLiteHistoricalProbabilityCalibrationRepository(database, migrate=False)
    backtests = SQLiteHistoricalBacktestingRepository(database, migrate=False)
    scores = SQLiteHistoricalFinalScoreReader(database)
    return HistoricalBacktestingService(
        training, splits, models, calibrations, backtests, scores, policy
    )
