class PredictionInferenceError(Exception):
    """Base error for raw prediction inference."""


class InferenceInputValidationError(PredictionInferenceError, ValueError):
    def __init__(self, reason_code: str, explanation: str) -> None:
        super().__init__(explanation)
        self.reason_code = reason_code
        self.explanation = explanation


class IncompatibleModelError(PredictionInferenceError, ValueError):
    def __init__(self, reason_code: str, explanation: str) -> None:
        super().__init__(explanation)
        self.reason_code = reason_code
        self.explanation = explanation


class InvalidModelOutputError(PredictionInferenceError, ValueError):
    def __init__(self, reason_code: str, explanation: str) -> None:
        super().__init__(explanation)
        self.reason_code = reason_code
        self.explanation = explanation


class ModelAdapterExecutionError(PredictionInferenceError):
    """An adapter-declared operational inference failure."""


class ModelAdapterCompatibilityError(PredictionInferenceError):
    """An adapter explicitly rejects the supplied model-input contract."""


class ModelRegistryError(PredictionInferenceError, ValueError):
    """Model registration or explicit selection is invalid."""


class InferenceConflictError(PredictionInferenceError):
    """Immutable inference persistence conflicts with stored content."""


class InferencePersistenceError(PredictionInferenceError):
    """Inference persistence could not be read or appended safely."""
