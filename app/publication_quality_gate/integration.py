from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .engine import OfficialPublicationQualityGate
from .models import OfficialPublicationCandidate, OfficialQualityGateEvaluation
from .repository import QualityGateEvaluationRepository


@runtime_checkable
class ApprovedOfficialPredictionPublisher(Protocol):
    """Existing/future atomic publisher; it retains ownership of claims/retries."""

    async def publish(self, candidate: OfficialPublicationCandidate) -> object: ...


@dataclass(frozen=True, slots=True)
class EligibilityBoundaryOutcome:
    evaluation: OfficialQualityGateEvaluation | None
    publication_attempted: bool
    publication_result: object | None
    fail_closed_reason: str | None = None


class OfficialPublicationEligibilityBoundary:
    """Persists eligibility before handing approved facts to the atomic publisher."""

    def __init__(
        self,
        gate: OfficialPublicationQualityGate,
        evaluations: QualityGateEvaluationRepository,
        publisher: ApprovedOfficialPredictionPublisher,
    ) -> None:
        self._gate = gate
        self._evaluations = evaluations
        self._publisher = publisher

    async def process(
        self,
        candidate: OfficialPublicationCandidate,
    ) -> EligibilityBoundaryOutcome:
        try:
            evaluation = self._gate.evaluate(candidate)
            evaluation = self._evaluations.append(evaluation)
        except Exception as exc:
            return EligibilityBoundaryOutcome(
                evaluation=None,
                publication_attempted=False,
                publication_result=None,
                fail_closed_reason=type(exc).__name__,
            )
        if not evaluation.automatic_publication_eligible:
            return EligibilityBoundaryOutcome(
                evaluation=evaluation,
                publication_attempted=False,
                publication_result=None,
            )
        result = await self._publisher.publish(candidate)
        return EligibilityBoundaryOutcome(
            evaluation=evaluation,
            publication_attempted=True,
            publication_result=result,
        )
