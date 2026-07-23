"""Production composition without startup or live wiring."""

from app.historical_model_training import SQLiteHistoricalModelTrainingRepository
from app.historical_probability_calibration import SQLiteHistoricalProbabilityCalibrationRepository
from app.model_comparison_promotion import SQLiteModelComparisonRepository

from .policy import DEFAULT_SHADOW_EVALUATION_POLICY
from .repository import SQLiteShadowEvaluationRepository
from .service import ShadowEvaluationService, ShadowSettlementService


def build_shadow_evaluation_service(database, input_source, *, policy=DEFAULT_SHADOW_EVALUATION_POLICY, migrate=True):
    repository = SQLiteShadowEvaluationRepository(database, migrate=migrate)
    return ShadowEvaluationService(
        repository, SQLiteModelComparisonRepository(database, migrate=False),
        SQLiteHistoricalModelTrainingRepository(database, migrate=False),
        SQLiteHistoricalProbabilityCalibrationRepository(database, migrate=False),
        input_source, policy,
    )


def build_shadow_settlement_service(database, *, policy=DEFAULT_SHADOW_EVALUATION_POLICY, migrate=True):
    return ShadowSettlementService(SQLiteShadowEvaluationRepository(database, migrate=migrate), policy)
