class CalibratedMarketProbabilityError(Exception):
    """Base calibrated-market-probability error."""


class CalibrationRegistryError(CalibratedMarketProbabilityError, ValueError):
    pass


class InvalidInferenceError(CalibratedMarketProbabilityError, ValueError):
    def __init__(self, code: str, explanation: str) -> None:
        super().__init__(explanation)
        self.code = code
        self.explanation = explanation


class IncompleteCalibrationSetError(CalibratedMarketProbabilityError, ValueError):
    pass


class IncompatibleCalibrationError(CalibratedMarketProbabilityError, ValueError):
    pass


class InvalidCalibratedOutputError(CalibratedMarketProbabilityError, ValueError):
    def __init__(self, code: str, explanation: str) -> None:
        super().__init__(explanation)
        self.code = code
        self.explanation = explanation


class CalibrationExecutionError(CalibratedMarketProbabilityError):
    pass


class CalibratedAssemblyConflictError(CalibratedMarketProbabilityError):
    pass


class CalibratedAssemblyPersistenceError(CalibratedMarketProbabilityError):
    pass
