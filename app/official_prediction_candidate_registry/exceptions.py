class OfficialPredictionCandidateRegistryError(Exception):
    """Base error for the Official candidate registry boundary."""


class CandidateRegistrationValidationError(
    OfficialPredictionCandidateRegistryError,
    ValueError,
):
    def __init__(
        self,
        reason_codes: tuple[str, ...],
        explanations: tuple[str, ...],
    ) -> None:
        super().__init__("; ".join(explanations))
        self.reason_codes = reason_codes
        self.explanations = explanations


class CandidateScopeValidationError(CandidateRegistrationValidationError):
    """Registration targets a product outside the Official boundary."""


class CandidateRegistryPersistenceError(OfficialPredictionCandidateRegistryError):
    """Durable registry state could not be read or appended safely."""


class CandidateRegistryConflictError(OfficialPredictionCandidateRegistryError):
    """Persisted registry history conflicts with the requested transition."""
