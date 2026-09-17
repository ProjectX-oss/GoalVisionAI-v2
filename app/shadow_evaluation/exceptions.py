"""Typed fail-closed shadow-evaluation failures."""


class ShadowEvaluationError(Exception):
    """Base error for the isolated shadow boundary."""


class ShadowValidationError(ShadowEvaluationError, ValueError):
    pass


class ShadowApprovalError(ShadowEvaluationError, ValueError):
    pass


class ShadowSourceError(ShadowEvaluationError, ValueError):
    pass


class ShadowProbabilityContractError(ShadowEvaluationError, ValueError):
    pass


class ShadowConflictError(ShadowEvaluationError):
    pass


class ShadowPersistenceError(ShadowEvaluationError):
    pass


class ShadowSettlementError(ShadowEvaluationError, ValueError):
    pass
