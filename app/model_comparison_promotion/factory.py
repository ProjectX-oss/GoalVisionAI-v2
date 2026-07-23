"""Explicit composition with no startup, activation, fetching, or scheduling."""

from app.historical_backtesting import SQLiteHistoricalBacktestingRepository
from app.historical_model_training import SQLiteHistoricalModelTrainingRepository
from app.historical_probability_calibration import (
    SQLiteHistoricalProbabilityCalibrationRepository,
)

from .policy import DEFAULT_PROMOTION_POLICY
from .repository import SQLiteModelComparisonRepository
from .service import ModelComparisonPromotionService


def build_model_comparison_promotion_service(
    database, *, policy=DEFAULT_PROMOTION_POLICY, migrate=True
):
    models = SQLiteHistoricalModelTrainingRepository(database, migrate=migrate)
    calibrations = SQLiteHistoricalProbabilityCalibrationRepository(
        database, migrate=False
    )
    backtests = SQLiteHistoricalBacktestingRepository(database, migrate=False)
    comparisons = SQLiteModelComparisonRepository(database, migrate=False)
    return ModelComparisonPromotionService(
        models, calibrations, backtests, comparisons, policy
    )
