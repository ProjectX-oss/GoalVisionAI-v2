from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.quality_gate import QualityGateStatus


ZERO = Decimal("0")
ONE = Decimal("1")


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")


def _finite(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{label} must be a finite Decimal.")


class RiskProductScope(str, Enum):
    OFFICIAL = "OFFICIAL"
    LIVE = "LIVE"
    HIGH_RISK = "HIGH_RISK"
    COMBO = "COMBO"
    AUTOTRADER = "AUTOTRADER"


class RiskAssessmentDecision(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REDUCED_STAKE = "REDUCED_STAKE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INELIGIBLE = "INELIGIBLE"


class RiskAssessmentPhase(str, Enum):
    PRE_PUBLICATION_GATE = "PRE_PUBLICATION_GATE"
    POST_PUBLICATION_GATE = "POST_PUBLICATION_GATE"


class StakeBand(str, Enum):
    NONE = "NONE"
    MINIMUM = "MINIMUM"
    STANDARD = "STANDARD"
    MAXIMUM = "MAXIMUM"


class StakeStars(int, Enum):
    ONE = 1
    TWO = 2
    THREE = 3


class DrawdownState(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    DEFENSIVE = "DEFENSIVE"
    HALTED = "HALTED"


class LossStreakState(str, Enum):
    NORMAL = "NORMAL"
    MINIMUM_CAP = "MINIMUM_CAP"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ExposureType(str, Enum):
    SINGLE_PREDICTION = "SINGLE_PREDICTION"
    DAILY_TOTAL = "DAILY_TOTAL"
    COMPETITION_TOTAL = "COMPETITION_TOTAL"
    FIXTURE_TOTAL = "FIXTURE_TOTAL"
    TEAM_TOTAL = "TEAM_TOTAL"
    MARKET_TOTAL = "MARKET_TOTAL"
    CORRELATED_GROUP_TOTAL = "CORRELATED_GROUP_TOTAL"
    UNSETTLED_TOTAL = "UNSETTLED_TOTAL"
    PRODUCT_TOTAL = "PRODUCT_TOTAL"


class CorrelationGroupKind(str, Enum):
    SAME_FIXTURE = "SAME_FIXTURE"
    SAME_TEAM = "SAME_TEAM"
    SAME_MARKET_FAMILY = "SAME_MARKET_FAMILY"
    DEPENDENT_OUTCOMES = "DEPENDENT_OUTCOMES"
    MANUAL = "MANUAL"


class RiskReason(str, Enum):
    INVALID_BANKROLL = "INVALID_BANKROLL"
    PRODUCT_SCOPE_MISMATCH = "PRODUCT_SCOPE_MISMATCH"
    QUALITY_GATE_REJECTED = "QUALITY_GATE_REJECTED"
    QUALITY_GATE_REVIEW_REQUIRED = "QUALITY_GATE_REVIEW_REQUIRED"
    INVALID_PROBABILITY = "INVALID_PROBABILITY"
    INVALID_ODDS = "INVALID_ODDS"
    EXPECTED_VALUE_TOO_LOW = "EXPECTED_VALUE_TOO_LOW"
    CALIBRATION_SAMPLE_TOO_SMALL = "CALIBRATION_SAMPLE_TOO_SMALL"
    MODEL_SAMPLE_TOO_SMALL = "MODEL_SAMPLE_TOO_SMALL"
    UNCERTAINTY_TOO_HIGH = "UNCERTAINTY_TOO_HIGH"
    DRAWDOWN_CAUTION = "DRAWDOWN_CAUTION"
    DRAWDOWN_DEFENSIVE = "DRAWDOWN_DEFENSIVE"
    DRAWDOWN_HALTED = "DRAWDOWN_HALTED"
    LOSS_STREAK_REDUCTION = "LOSS_STREAK_REDUCTION"
    LOSS_STREAK_HALTED = "LOSS_STREAK_HALTED"
    SINGLE_STAKE_LIMIT = "SINGLE_STAKE_LIMIT"
    DAILY_EXPOSURE_LIMIT = "DAILY_EXPOSURE_LIMIT"
    COMPETITION_EXPOSURE_LIMIT = "COMPETITION_EXPOSURE_LIMIT"
    FIXTURE_EXPOSURE_LIMIT = "FIXTURE_EXPOSURE_LIMIT"
    TEAM_EXPOSURE_LIMIT = "TEAM_EXPOSURE_LIMIT"
    MARKET_EXPOSURE_LIMIT = "MARKET_EXPOSURE_LIMIT"
    CORRELATED_EXPOSURE_LIMIT = "CORRELATED_EXPOSURE_LIMIT"
    UNSETTLED_EXPOSURE_LIMIT = "UNSETTLED_EXPOSURE_LIMIT"
    REQUESTED_STAKE_REDUCED = "REQUESTED_STAKE_REDUCED"
    STAKE_BELOW_MINIMUM = "STAKE_BELOW_MINIMUM"
    NO_HISTORICAL_BANKROLL_SNAPSHOT = "NO_HISTORICAL_BANKROLL_SNAPSHOT"
    COMBO_EXCEPTION_NOT_ELIGIBLE = "COMBO_EXCEPTION_NOT_ELIGIBLE"
    UNSUPPORTED_PRODUCT_POLICY = "UNSUPPORTED_PRODUCT_POLICY"


class RiskWarning(str, Enum):
    INITIAL_THRESHOLDS_NOT_STATISTICALLY_OPTIMIZED = (
        "INITIAL_THRESHOLDS_NOT_STATISTICALLY_OPTIMIZED"
    )
    SMALL_EVALUATION_SAMPLE = "SMALL_EVALUATION_SAMPLE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    HISTORICAL_RECOMMENDATION_ONLY = "HISTORICAL_RECOMMENDATION_ONLY"


@dataclass(frozen=True, slots=True)
class CorrelationGroup:
    group_id: str
    kind: CorrelationGroupKind
    description: str

    def __post_init__(self) -> None:
        if not self.group_id.strip() or not self.description.strip():
            raise ValueError("Correlation groups require stable identity and description.")


@dataclass(frozen=True, slots=True)
class BankrollStateSnapshot:
    product_scope: RiskProductScope
    currency: str
    opening_bankroll: Decimal
    current_bankroll: Decimal
    peak_bankroll: Decimal
    current_drawdown_amount: Decimal
    current_drawdown_percentage: Decimal
    consecutive_wins: int
    consecutive_losses: int
    settled_bet_count: int
    unsettled_exposure: Decimal
    snapshot_timestamp: datetime
    authoritative_source_reference: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.opening_bankroll, "Opening bankroll"),
            (self.current_bankroll, "Current bankroll"),
            (self.peak_bankroll, "Peak bankroll"),
            (self.current_drawdown_amount, "Drawdown amount"),
            (self.current_drawdown_percentage, "Drawdown percentage"),
            (self.unsettled_exposure, "Unsettled exposure"),
        ):
            _finite(value, label)
        if any(
            value < 0
            for value in (
                self.current_drawdown_amount,
                self.current_drawdown_percentage,
                self.unsettled_exposure,
            )
        ):
            raise ValueError("Drawdown and unsettled exposure must not be negative.")
        if self.peak_bankroll < self.current_bankroll:
            raise ValueError("Peak bankroll must not be below current bankroll.")
        expected_amount = self.peak_bankroll - self.current_bankroll
        if self.current_drawdown_amount != expected_amount:
            raise ValueError("Drawdown amount must equal peak minus current bankroll.")
        expected_percentage = (
            expected_amount / self.peak_bankroll if self.peak_bankroll else ZERO
        )
        if self.current_drawdown_percentage != expected_percentage:
            raise ValueError("Drawdown percentage conflicts with bankroll values.")
        if min(
            self.consecutive_wins,
            self.consecutive_losses,
            self.settled_bet_count,
        ) < 0:
            raise ValueError("Bankroll counters must not be negative.")
        if not self.currency.strip() or not self.authoritative_source_reference.strip():
            raise ValueError("Bankroll currency and source reference are required.")
        _aware(self.snapshot_timestamp, "Bankroll snapshot timestamp")


@dataclass(frozen=True, slots=True)
class ExposurePosition:
    exposure_type: ExposureType
    scope_key: str
    current_amount: Decimal
    currency: str
    source_timestamp: datetime

    def __post_init__(self) -> None:
        _finite(self.current_amount, "Current exposure")
        if self.current_amount < 0:
            raise ValueError("Current exposure must not be negative.")
        if not self.scope_key.strip() or not self.currency.strip():
            raise ValueError("Exposure scope and currency are required.")
        _aware(self.source_timestamp, "Exposure source timestamp")


@dataclass(frozen=True, slots=True)
class ExposureSnapshot:
    product_scope: RiskProductScope
    positions: tuple[ExposurePosition, ...]
    snapshot_timestamp: datetime
    authoritative_source_reference: str

    def __post_init__(self) -> None:
        _aware(self.snapshot_timestamp, "Exposure snapshot timestamp")
        if not self.authoritative_source_reference.strip():
            raise ValueError("Exposure snapshot source is required.")
        identities = tuple(
            (item.exposure_type, item.scope_key) for item in self.positions
        )
        if len(set(identities)) != len(identities):
            raise ValueError("Exposure positions must have unique identities.")
        if any(item.source_timestamp > self.snapshot_timestamp for item in self.positions):
            raise ValueError("Exposure positions cannot be newer than their snapshot.")

    def amount_for(self, exposure_type: ExposureType, scope_key: str) -> Decimal:
        return next(
            (
                item.current_amount
                for item in self.positions
                if item.exposure_type is exposure_type and item.scope_key == scope_key
            ),
            ZERO,
        )


@dataclass(frozen=True, slots=True)
class ExposureLimit:
    exposure_type: ExposureType
    maximum_percentage: Decimal
    reason: RiskReason

    def __post_init__(self) -> None:
        _finite(self.maximum_percentage, "Exposure limit percentage")
        if not ZERO < self.maximum_percentage <= ONE:
            raise ValueError("Exposure limit percentage must be in (0, 1].")


@dataclass(frozen=True, slots=True)
class ExposureAssessment:
    exposure_type: ExposureType
    scope_key: str
    current_amount: Decimal
    proposed_amount: Decimal
    limit_amount: Decimal
    currency: str
    percentage_of_bankroll: Decimal
    source_timestamp: datetime
    remaining_capacity: Decimal
    limiting: bool
    reason: RiskReason


@dataclass(frozen=True, slots=True)
class RiskAssessmentRequest:
    prediction_id: str
    fixture_id: int
    competition: str
    market: str
    selection: str
    product_scope: RiskProductScope
    prediction_timestamp: datetime
    kickoff: datetime
    accepted_probability: Decimal
    offered_odds: Decimal
    expected_value: Decimal
    quality_gate_status: QualityGateStatus | None
    model_confidence: Decimal | None
    uncertainty: Decimal | None
    calibration_sample_size: int
    model_sample_size: int
    correlation_group_ids: tuple[str, ...]
    requested_stake: Decimal | None
    candidate_policy_version: str
    calibrated_probability_available: bool
    team_ids: tuple[str, ...] = ()
    market_family: str | None = None
    assessment_phase: RiskAssessmentPhase = RiskAssessmentPhase.POST_PUBLICATION_GATE

    def __post_init__(self) -> None:
        for value in (
            self.prediction_id,
            self.competition,
            self.market,
            self.selection,
            self.candidate_policy_version,
        ):
            if not value.strip():
                raise ValueError("Risk request identity values must not be empty.")
        if self.fixture_id <= 0:
            raise ValueError("Risk request fixture ID must be positive.")
        _aware(self.prediction_timestamp, "Prediction timestamp")
        _aware(self.kickoff, "Kickoff timestamp")
        if self.prediction_timestamp > self.kickoff:
            raise ValueError("Prediction timestamp must not be after kickoff.")
        for value, label in (
            (self.accepted_probability, "Accepted probability"),
            (self.offered_odds, "Offered odds"),
            (self.expected_value, "Expected value"),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{label} must be a Decimal.")
        for value, label in (
            (self.model_confidence, "Model confidence"),
            (self.uncertainty, "Uncertainty"),
            (self.requested_stake, "Requested stake"),
        ):
            if value is not None and not isinstance(value, Decimal):
                raise TypeError(f"{label} must be a Decimal when supplied.")
        if self.calibration_sample_size < 0 or self.model_sample_size < 0:
            raise ValueError("Sample sizes must not be negative.")
        if len(set(self.correlation_group_ids)) != len(self.correlation_group_ids):
            raise ValueError("Correlation group IDs must be unique.")
        if not isinstance(self.assessment_phase, RiskAssessmentPhase):
            raise ValueError("Risk assessment phase is unsupported.")
        if (
            self.assessment_phase is RiskAssessmentPhase.PRE_PUBLICATION_GATE
            and self.quality_gate_status is not None
        ):
            raise ValueError(
                "Pre-publication-gate risk assessment cannot claim a gate status."
            )


@dataclass(frozen=True, slots=True)
class RiskAssessmentContext:
    bankroll: BankrollStateSnapshot
    exposure: ExposureSnapshot
    correlation_groups: tuple[CorrelationGroup, ...]
    assessed_at: datetime

    def __post_init__(self) -> None:
        _aware(self.assessed_at, "Assessment timestamp")
        if self.bankroll.snapshot_timestamp > self.assessed_at:
            raise ValueError("Bankroll snapshot cannot come from the future.")
        if self.exposure.snapshot_timestamp > self.assessed_at:
            raise ValueError("Exposure snapshot cannot come from the future.")


@dataclass(frozen=True, slots=True)
class StakeRecommendation:
    band: StakeBand
    unquantized_stake: Decimal
    final_stake: Decimal
    internal_stake_percentage: Decimal
    public_stars: StakeStars | None
    currency: str
    currency_quantum: Decimal


@dataclass(frozen=True, slots=True)
class RiskAuditRecord:
    assessment_id: str
    prediction_id: str
    product_scope: RiskProductScope
    policy_version: str
    bankroll_snapshot: BankrollStateSnapshot
    exposure_snapshot: ExposureSnapshot
    quality_gate_status: QualityGateStatus | None
    base_stake: Decimal
    reductions: tuple[tuple[RiskReason, Decimal, Decimal], ...]
    recommendation: StakeRecommendation | None
    final_decision: RiskAssessmentDecision
    ordered_reasons: tuple[RiskReason, ...]
    ordered_warnings: tuple[RiskWarning, ...]
    drawdown_state: DrawdownState
    loss_streak_state: LossStreakState
    limiting_exposure: ExposureAssessment | None
    exposure_assessments: tuple[ExposureAssessment, ...]
    assessed_at: datetime
    assessment_phase: RiskAssessmentPhase = RiskAssessmentPhase.POST_PUBLICATION_GATE


@dataclass(frozen=True, slots=True)
class PublicStakeRecommendation:
    prediction_id: str
    decision: RiskAssessmentDecision
    stake_band: StakeBand
    stake_amount: Decimal
    currency: str
    public_stars: StakeStars
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComboExceptionAssessment:
    eligible: bool
    selection_count: int
    combined_odds: Decimal
    separate_exposure_required: bool
    reason: RiskReason | None


@dataclass(frozen=True, slots=True)
class ShadowRiskRecommendation:
    available: bool
    shadow_evaluation_id: str
    policy_version: str
    audit: RiskAuditRecord | None
    reason: RiskReason | None


class RiskManagementError(RuntimeError):
    pass


class UnsupportedRiskProductPolicy(RiskManagementError):
    pass
