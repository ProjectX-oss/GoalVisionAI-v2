from .models import AssemblyReason


class CandidateAssemblyError(ValueError):
    """Expected fail-closed inconsistency in supplied immutable facts."""

    def __init__(
        self,
        reasons: tuple[AssemblyReason, ...],
        explanations: tuple[str, ...],
    ) -> None:
        if not reasons or len(reasons) != len(explanations):
            raise ValueError("Assembly errors require aligned reasons and explanations.")
        self.reasons = reasons
        self.explanations = explanations
        super().__init__("; ".join(explanations))


class OfficialPublisherError(RuntimeError):
    def __init__(self, message: str, attempt_reference: str | None = None) -> None:
        self.attempt_reference = attempt_reference
        super().__init__(message)


class ConfirmedOfficialPublisherError(OfficialPublisherError):
    """Delivery definitely failed before a successful Telegram send."""


class IndeterminateOfficialPublisherError(OfficialPublisherError):
    """Delivery may have occurred; automatic retry is unsafe."""
