from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.quality_gate import (
    ProbabilitySource,
    PublicationCandidate,
    QualityGateCheckResult,
    QualityGateContext,
    QualityGateStatus,
    RejectionReason,
    ReviewReason,
)
from app.results import ResolvedPredictionResult, ResolutionStatus


class ShadowEvaluationStage(str, Enum):
    INITIAL_CANDIDATE = "INITIAL_CANDIDATE"
    PRE_PUBLICATION = "PRE_PUBLICATION"
    FINAL_PRE_KICKOFF = "FINAL_PRE_KICKOFF"


class ShadowEvaluationOutcome(str, Enum):
    RECORDED = "RECORDED"
    EXISTING = "EXISTING"
    ERROR = "ERROR"
    DISABLED = "DISABLED"
    INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True, slots=True)
class ShadowEvaluationRequest:
    shadow_evaluation_id: str
    stage: ShadowEvaluationStage
    candidate: PublicationCandidate
    context: QualityGateContext
    policy_version: str
    actually_published: bool
    actual_publication_timestamp: datetime | None
    actual_offered_odds: Decimal | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.shadow_evaluation_id.strip():
            raise ValueError("Shadow evaluation ID must not be empty.")
        if not self.policy_version.strip():
            raise ValueError("Shadow policy version must not be empty.")
        _require_aware(self.created_at, "Created timestamp")
        if self.actual_publication_timestamp is not None:
            _require_aware(
                self.actual_publication_timestamp,
                "Publication timestamp",
            )
        if self.actually_published != (
            self.actual_publication_timestamp is not None
        ):
            raise ValueError(
                "Published shadows require exactly one publication timestamp."
            )
        if self.actual_offered_odds is not None and (
            not self.actual_offered_odds.is_finite()
            or self.actual_offered_odds <= Decimal("1")
        ):
            raise ValueError("Actual publication odds must exceed one.")
        if self.actual_offered_odds is not None and not self.actually_published:
            raise ValueError("Publication odds require an actual publication.")


@dataclass(frozen=True, slots=True)
class ShadowEvaluationRecord:
    shadow_evaluation_id: str
    prediction_id: str
    fixture_id: int
    product_scope: str
    stage: ShadowEvaluationStage
    candidate_snapshot: PublicationCandidate
    context_snapshot: QualityGateContext
    policy_version: str
    evaluation_timestamp: datetime
    gate_status: QualityGateStatus
    ordered_check_results: tuple[QualityGateCheckResult, ...]
    rejection_reasons: tuple[RejectionReason, ...]
    review_reasons: tuple[ReviewReason, ...]
    evaluated_probability: Decimal | None
    probability_source: ProbabilitySource | None
    calculated_expected_value: Decimal | None
    market_disagreement: Decimal | None
    actually_published: bool
    actual_publication_timestamp: datetime | None
    actual_offered_odds: Decimal | None
    settlement_outcome: ResolutionStatus | None
    eventual_profit_loss_units: Decimal | None
    settled_at: datetime | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.shadow_evaluation_id.strip() or not self.prediction_id.strip():
            raise ValueError("Shadow and prediction IDs must not be empty.")
        if (
            self.fixture_id <= 0
            or not self.product_scope.strip()
            or not self.policy_version.strip()
        ):
            raise ValueError("Shadow fixture and product scope must be valid.")
        _require_aware(self.evaluation_timestamp, "Evaluation timestamp")
        _require_aware(self.created_at, "Created timestamp")
        if (
            self.prediction_id != self.candidate_snapshot.prediction_id
            or self.fixture_id != self.candidate_snapshot.fixture_id
            or self.product_scope != self.candidate_snapshot.product_scope
            or self.evaluation_timestamp
            != self.context_snapshot.evaluation_timestamp
        ):
            raise ValueError("Shadow audit identity does not match its snapshots.")
        checks = tuple(item.check for item in self.ordered_check_results)
        if not checks or len(set(checks)) != len(checks):
            raise ValueError("Shadow audit checks must be complete and unique.")
        expected_status = (
            QualityGateStatus.REJECTED
            if self.rejection_reasons
            else (
                QualityGateStatus.REVIEW_REQUIRED
                if self.review_reasons
                else QualityGateStatus.APPROVED
            )
        )
        if self.gate_status is not expected_status:
            raise ValueError("Shadow gate status conflicts with its reasons.")
        if self.actually_published != (
            self.actual_publication_timestamp is not None
        ):
            raise ValueError("Shadow publication facts are inconsistent.")
        if self.actual_offered_odds is not None and not self.actually_published:
            raise ValueError("Publication odds require an actual publication.")
        if self.actual_offered_odds is not None and (
            not self.actual_offered_odds.is_finite()
            or self.actual_offered_odds <= Decimal("1")
        ):
            raise ValueError("Actual publication odds must exceed one.")
        for value in (
            self.evaluated_probability,
            self.calculated_expected_value,
            self.market_disagreement,
        ):
            if value is not None and not value.is_finite():
                raise ValueError("Shadow decision decimals must be finite.")
        if self.settlement_outcome is not None and self.settlement_outcome not in {
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        }:
            raise ValueError("Shadow settlement must be terminal.")
        settlement_fields = (
            self.settlement_outcome,
            self.eventual_profit_loss_units,
            self.settled_at,
        )
        if any(value is not None for value in settlement_fields) and not all(
            value is not None for value in settlement_fields
        ):
            raise ValueError("Shadow settlement facts must be complete.")
        if self.settled_at is not None:
            _require_aware(self.settled_at, "Settlement timestamp")
        if self.eventual_profit_loss_units is not None and (
            not self.eventual_profit_loss_units.is_finite()
        ):
            raise ValueError("Profit/loss units must be finite.")


@dataclass(frozen=True, slots=True)
class ShadowEvaluationError:
    shadow_evaluation_id: str
    prediction_id: str
    stage: ShadowEvaluationStage
    policy_version: str
    error_type: str
    safe_message: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.error_type.strip() or not self.safe_message.strip():
            raise ValueError("Shadow errors require safe typed details.")
        _require_aware(self.occurred_at, "Error timestamp")


@dataclass(frozen=True, slots=True)
class ShadowEvaluationResult:
    outcome: ShadowEvaluationOutcome
    record: ShadowEvaluationRecord | None = None
    error: ShadowEvaluationError | None = None
    unavailable_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ShadowSettlementFacts:
    outcome: ResolutionStatus
    profit_loss_units: Decimal
    settled_at: datetime

    def __post_init__(self) -> None:
        if self.outcome not in {
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        }:
            raise ValueError("Settlement enrichment requires a terminal outcome.")
        if not self.profit_loss_units.is_finite():
            raise ValueError("Profit/loss units must be finite.")
        _require_aware(self.settled_at, "Settlement timestamp")

    @classmethod
    def from_authoritative_result(
        cls,
        result: ResolvedPredictionResult,
        profit_loss_units: Decimal,
    ) -> "ShadowSettlementFacts":
        if not result.is_terminal or result.resolved_at is None:
            raise ValueError("Authoritative settlement must be terminal.")
        return cls(
            outcome=result.status,
            profit_loss_units=profit_loss_units,
            settled_at=result.resolved_at,
        )


@dataclass(frozen=True, slots=True)
class ShadowReasonStatistics:
    reason: str
    count: int


@dataclass(frozen=True, slots=True)
class ShadowPerformanceStatistics:
    total_records: int
    settled_count: int
    won_count: int
    lost_count: int
    void_count: int
    profit_loss_units: Decimal
    roi: Decimal | None
    hit_rate: Decimal | None
    hypothetical: bool


@dataclass(frozen=True, slots=True)
class ShadowGateStatusStatistics:
    gate_status: QualityGateStatus
    performance: ShadowPerformanceStatistics


@dataclass(frozen=True, slots=True)
class ShadowComparisonReport:
    policy_version: str
    start_at: datetime
    end_at: datetime
    total_shadow_evaluations: int
    approved_count: int
    review_required_count: int
    rejected_count: int
    actually_published_count: int
    unpublished_count: int
    settlement_coverage_count: int
    by_gate_status: tuple[ShadowGateStatusStatistics, ...]
    hypothetical_approved_only: ShadowPerformanceStatistics
    hypothetical_approved_and_review: ShadowPerformanceStatistics
    actual_published_result: ShadowPerformanceStatistics
    rejection_reasons: tuple[ShadowReasonStatistics, ...]
    review_reasons: tuple[ShadowReasonStatistics, ...]
    error_count: int
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class ShadowAdaptation:
    request: ShadowEvaluationRequest | None
    unavailable_fields: tuple[str, ...]


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
