from .engine import PredictionInferenceService
from .fingerprint import PredictionInferenceFingerprint
from .model_registry import PredictionModelRegistry
from .policy import PredictionInferencePolicy
from .ports import PredictionInferenceRepository
from .validation import PredictionInferenceInputValidator, RawProbabilityValidator


def build_prediction_inference_service(
    repository: PredictionInferenceRepository,
    registry: PredictionModelRegistry,
    policy: PredictionInferencePolicy,
) -> PredictionInferenceService:
    """Compose inference only from explicit dependencies; never loads a model."""
    if registry.policy != policy:
        raise ValueError("Registry and service inference policies must match.")
    return PredictionInferenceService(
        repository,
        registry,
        policy,
        PredictionInferenceInputValidator(),
        RawProbabilityValidator(),
        PredictionInferenceFingerprint(),
    )
