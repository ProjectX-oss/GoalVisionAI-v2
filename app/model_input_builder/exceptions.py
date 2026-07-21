class ModelInputBuilderError(Exception):
    """Base error for deterministic model-input construction."""


class ModelInputValidationError(ModelInputBuilderError, ValueError):
    def __init__(self, reason_code: str, explanation: str) -> None:
        super().__init__(explanation)
        self.reason_code = reason_code
        self.explanation = explanation


class ModelInputConflictError(ModelInputBuilderError):
    """An immutable model-input identity conflicts with stored content."""


class ModelInputPersistenceError(ModelInputBuilderError):
    """Model-input history could not be read or appended safely."""
