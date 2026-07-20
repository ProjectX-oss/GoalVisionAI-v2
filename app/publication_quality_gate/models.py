from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.quality_gate import QualityGateStatus
from app.risk_management import RiskAssessmentDecision, RiskProductScope


class ConfidenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    ELITE = "ELITE"


class FactStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class LineupStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MarketAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


class ModelHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    UNHEALTHY = "UNHEALTHY"


class ExposureDecision(str, Enum):
    CLEAR = "CLEAR"
    WARNING = "WARNING"
    HARD_BREACH = "HARD_BREACH"


class PublicationState(str, Enum):
    UNPUBLISHED = "UNPUBLISHED"
    FAILED = "FAILED"
    ATTEMPTING = "ATTEMPTING"
    CLAIMED = "CLAIMED"
    PUBLISHED = "PUBLISHED"


class SupportedMarket(str, Enum):
    MATCH_WINNER = "MATCH_WINNER"
    DOUBLE_CHANCE = "DOUBLE_CHANCE"
    TOTALS = "TOTALS"
    BTTS = "BTTS"


class FindingSeverity(str, Enum):
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class GateReason(str, Enum):
    INVALID_IDENTITY = "INVALID_IDENTITY"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    PREDICTION_AT_OR_AFTER_KICKOFF = "PREDICTION_AT_OR_AFTER_KICKOFF"
    CANDIDATE_EXPIRED = "CANDIDATE_EXPIRED"
    INVALID_RAW_PROBABILITY = "INVALID_RAW_PROBABILITY"
    CALIBRATED_PROBABILITY_MISSING = "CALIBRATED_PROBABILITY_MISSING"
    INVALID_CALIBRATED_PROBABILITY = "INVALID_CALIBRATED_PROBABILITY"
    INVALID_ODDS = "INVALID_ODDS"
    ODDS_BELOW_MINIMUM = "ODDS_BELOW_MINIMUM"
    ODDS_STALE = "ODDS_STALE"
    CORE_DATA_MISSING = "CORE_DATA_MISSING"
    CORE_DATA_STALE = "CORE_DATA_STALE"
    MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"
    MARKET_LIQUIDITY_LIMITED = "MARKET_LIQUIDITY_LIMITED"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    CORRECT_SCORE_FORBIDDEN = "CORRECT_SCORE_FORBIDDEN"
    INVALID_MARKET_LINE = "INVALID_MARKET_LINE"
    INVALID_SELECTION = "INVALID_SELECTION"
    INVALID_EXPECTED_VALUE = "INVALID_EXPECTED_VALUE"
    EXPECTED_VALUE_MISMATCH = "EXPECTED_VALUE_MISMATCH"
    EXPECTED_VALUE_TOO_LOW = "EXPECTED_VALUE_TOO_LOW"
    CONSERVATIVE_EXPECTED_VALUE = "CONSERVATIVE_EXPECTED_VALUE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MEDIUM_CONFIDENCE_WEAK_DATA = "MEDIUM_CONFIDENCE_WEAK_DATA"
    CALIBRATION_FACTS_MISSING = "CALIBRATION_FACTS_MISSING"
    CALIBRATION_MODEL_VERSION_MISMATCH = "CALIBRATION_MODEL_VERSION_MISMATCH"
    CALIBRATION_SAMPLE_INSUFFICIENT = "CALIBRATION_SAMPLE_INSUFFICIENT"
    CALIBRATION_METRICS_WARNING = "CALIBRATION_METRICS_WARNING"
    CALIBRATION_METRICS_DEGRADED = "CALIBRATION_METRICS_DEGRADED"
    CALIBRATION_METRICS_HARD_FAILURE = "CALIBRATION_METRICS_HARD_FAILURE"
    MODEL_HEALTH_VERSION_MISMATCH = "MODEL_HEALTH_VERSION_MISMATCH"
    MODEL_HEALTH_WARNING = "MODEL_HEALTH_WARNING"
    MODEL_UNHEALTHY = "MODEL_UNHEALTHY"
    LINEUP_CONFIRMATION_MISSING = "LINEUP_CONFIRMATION_MISSING"
    INJURY_DATA_INCOMPLETE = "INJURY_DATA_INCOMPLETE"
    RISK_INELIGIBLE = "RISK_INELIGIBLE"
    RISK_REVIEW_REQUIRED = "RISK_REVIEW_REQUIRED"
    WRONG_BANKROLL_SCOPE = "WRONG_BANKROLL_SCOPE"
    EXPOSURE_WARNING = "EXPOSURE_WARNING"
    EXPOSURE_HARD_BREACH = "EXPOSURE_HARD_BREACH"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    ACTIVE_PUBLICATION_ATTEMPT = "ACTIVE_PUBLICATION_ATTEMPT"


@dataclass(frozen=True, slots=True)
class CalibrationQualityFacts:
    brier_score: Decimal
    log_loss: Decimal
    expected_calibration_error: Decimal
    maximum_calibration_error: Decimal
    sample_size: int
    model_version: str


@dataclass(frozen=True, slots=True)
class ModelHealthFacts:
    status: ModelHealthStatus
    model_version: str
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class OfficialPublicationCandidate:
    """Fully prepared supplied facts; the gate performs no data acquisition."""

    prediction_id: str
    model_version: str
    market: str
    selection: str
    raw_probability: Decimal
    calibrated_probability: Decimal | None
    decimal_odds: Decimal
    expected_value: Decimal | None
    confidence: ConfidenceLevel
    prediction_timestamp: datetime
    kickoff_timestamp: datetime
    evaluation_timestamp: datetime
    odds_observed_at: datetime
    core_data_observed_at: datetime
    supporting_data_status: FactStatus
    market_availability: MarketAvailability
    calibration: CalibrationQualityFacts | None
    model_health: ModelHealthFacts
    risk_result: RiskAssessmentDecision
    exposure_result: ExposureDecision
    bankroll_scope: RiskProductScope
    publication_state: PublicationState
    lineup_status: LineupStatus = LineupStatus.MISSING
    injury_status: FactStatus = FactStatus.MISSING
    market_line: Decimal | None = None


@dataclass(frozen=True, slots=True)
class GateFinding:
    reason: GateReason
    severity: FindingSeverity
    explanation: str


@dataclass(frozen=True, slots=True)
class OfficialQualityGateEvaluation:
    evaluation_id: str
    prediction_id: str
    final_decision: QualityGateStatus
    ordered_reason_codes: tuple[GateReason, ...]
    internal_explanations: tuple[str, ...]
    findings: tuple[GateFinding, ...]
    policy_version: str
    model_version: str
    raw_probability: Decimal
    calibrated_probability: Decimal | None
    decimal_odds: Decimal
    supplied_expected_value: Decimal | None
    recomputed_expected_value: Decimal | None
    confidence: ConfidenceLevel
    prediction_timestamp: datetime
    kickoff_timestamp: datetime
    evaluated_at: datetime
    input_fingerprint: str
    normalized_input: tuple[tuple[str, str], ...]
    risk_result: RiskAssessmentDecision
    exposure_result: ExposureDecision

    @property
    def automatic_publication_eligible(self) -> bool:
        return self.final_decision is QualityGateStatus.APPROVED
