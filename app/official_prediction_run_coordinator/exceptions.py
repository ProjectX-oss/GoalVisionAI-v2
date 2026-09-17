class OfficialPredictionRunCoordinatorError(RuntimeError):
    """Base failure for the Official batch execution boundary."""


class OfficialPredictionRunValidationError(
    OfficialPredictionRunCoordinatorError,
    ValueError,
):
    """Caller-supplied batch execution facts are invalid."""


class OfficialPredictionRunPersistenceError(OfficialPredictionRunCoordinatorError):
    """Append-only run history could not be read or written safely."""


class IncompleteOfficialPredictionRun(OfficialPredictionRunCoordinatorError):
    """A prior run started but has no certain terminal audit event."""
