"""Typed controlled-activation failures."""


class ModelActivationError(Exception):
    pass


class ActivationValidationError(ModelActivationError, ValueError):
    pass


class ActivationNotEligibleError(ModelActivationError, ValueError):
    pass


class ActivationConflictError(ModelActivationError):
    pass


class ActivationStalePlanError(ModelActivationError):
    pass


class ChampionStateInvalidError(ModelActivationError):
    pass


class ActivationPersistenceError(ModelActivationError):
    pass
