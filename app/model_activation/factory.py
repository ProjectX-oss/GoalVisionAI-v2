"""Explicit composition; no startup or runtime wiring."""

from app.historical_model_training import SQLiteHistoricalModelTrainingRepository
from app.historical_probability_calibration import SQLiteHistoricalProbabilityCalibrationRepository
from app.model_comparison_promotion import SQLiteModelComparisonRepository
from app.shadow_evaluation import SQLiteShadowEvaluationRepository

from .policy import DEFAULT_MODEL_ACTIVATION_POLICY
from .repository import SQLiteModelActivationRepository
from .resolver import RuntimeChampionResolver
from .service import ModelActivationService


def build_model_activation_service(database, *, policy=DEFAULT_MODEL_ACTIVATION_POLICY, migrate=True):
    repository = SQLiteModelActivationRepository(database, migrate=migrate)
    return ModelActivationService(
        repository, SQLiteModelComparisonRepository(database, migrate=False),
        SQLiteShadowEvaluationRepository(database, migrate=False),
        SQLiteHistoricalModelTrainingRepository(database, migrate=False),
        SQLiteHistoricalProbabilityCalibrationRepository(database, migrate=False),
        policy,
    )


def build_runtime_champion_resolver(database, *, policy=DEFAULT_MODEL_ACTIVATION_POLICY, migrate=True):
    return RuntimeChampionResolver(
        SQLiteModelActivationRepository(database, migrate=migrate),
        SQLiteHistoricalModelTrainingRepository(database, migrate=False),
        SQLiteHistoricalProbabilityCalibrationRepository(database, migrate=False),
        policy,
    )
