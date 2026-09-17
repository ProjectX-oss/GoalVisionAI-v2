from app.database import Database

from .builder import DeterministicModelInputBuilder
from .fingerprint import ModelInputFingerprint
from .policy import (
    DEFAULT_MODEL_INPUT_BUILDER_POLICY,
    ModelInputBuilderPolicy,
)
from .repository import SQLiteModelInputRepository
from .schema import build_model_input_schema
from .service import PredictionModelInputBuilderService
from .validation import ModelInputValidator


def build_model_input_builder(
    database: Database,
    *,
    policy: ModelInputBuilderPolicy = DEFAULT_MODEL_INPUT_BUILDER_POLICY,
) -> PredictionModelInputBuilderService:
    """Compose the builder without loading or invoking any prediction model."""
    repository = SQLiteModelInputRepository(database)
    schema = build_model_input_schema(policy)
    return PredictionModelInputBuilderService(
        repository,
        DeterministicModelInputBuilder(
            schema,
            policy,
            ModelInputValidator(),
            ModelInputFingerprint(),
        ),
    )
