class OfficialPredictionPipelineError(RuntimeError):
    """Base error for the manual Official prediction pipeline."""


class PipelineValidationError(OfficialPredictionPipelineError):
    def __init__(self, status: str, reasons: tuple[str, ...], explanations: tuple[str, ...]):
        super().__init__(explanations[0] if explanations else status)
        self.status = status
        self.reasons = reasons
        self.explanations = explanations


class PipelineConflictError(OfficialPredictionPipelineError):
    pass


class PipelinePersistenceError(OfficialPredictionPipelineError):
    pass
