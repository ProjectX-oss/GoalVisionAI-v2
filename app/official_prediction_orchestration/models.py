from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.probability_calibration import ProbabilityCalibrationReport
from app.publication_quality_gate import (
    ConfidenceLevel,
    ExposureDecision,
    FactStatus,
    LineupStatus,
    MarketAvailability,
    ModelHealthStatus,
    OfficialPublicationCandidate,
    OfficialQualityGateEvaluation,
)
from app.quality_gate import QualityGateStatus
from app.risk_management import RiskAssessmentDecision, RiskProductScope


class PublicationDeliveryState(str, Enum):
    NEVER_ATTEMPTED = "NEVER_ATTEMPTED"
    CLAIMED = "CLAIMED"
    ATTEMPTING = "ATTEMPTING"
    PUBLISHED = "PUBLISHED"
    CONFIRMED_FAILED_RETRYABLE = "CONFIRMED_FAILED_RETRYABLE"
    INDETERMINATE_FAILURE = "INDETERMINATE_FAILURE"


class OrchestrationStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    APPROVED_NOT_PUBLISHED = "APPROVED_NOT_PUBLISHED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DUPLICATE_BLOCKED = "DUPLICATE_BLOCKED"
    RETRYABLE_PUBLICATION_FAILURE = "RETRYABLE_PUBLICATION_FAILURE"
    INDETERMINATE_PUBLICATION_FAILURE = "INDETERMINATE_PUBLICATION_FAILURE"
    ASSEMBLY_FAILED = "ASSEMBLY_FAILED"


class AssemblyReason(str, Enum):
    INVALID_PREDICTION_IDENTITY = "INVALID_PREDICTION_IDENTITY"
    INVALID_MATCH_IDENTITY = "INVALID_MATCH_IDENTITY"
    INVALID_MODEL_VERSION = "INVALID_MODEL_VERSION"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_PROBABILITY = "INVALID_PROBABILITY"
    INVALID_ODDS = "INVALID_ODDS"
    INVALID_EXPECTED_VALUE = "INVALID_EXPECTED_VALUE"
    UNSUPPORTED_MARKET_FACTS = "UNSUPPORTED_MARKET_FACTS"
    NO_VALID_CALIBRATION_RECORD = "NO_VALID_CALIBRATION_RECORD"
    CALIBRATION_MODEL_VERSION_MISMATCH = "CALIBRATION_MODEL_VERSION_MISMATCH"
    CALIBRATION_RAW_PROBABILITY_MISMATCH = "CALIBRATION_RAW_PROBABILITY_MISMATCH"
    NO_VALID_MODEL_HEALTH_RECORD = "NO_VALID_MODEL_HEALTH_RECORD"
    MODEL_HEALTH_VERSION_MISMATCH = "MODEL_HEALTH_VERSION_MISMATCH"
    NO_VALID_RISK_EVALUATION = "NO_VALID_RISK_EVALUATION"
    RISK_IDENTITY_MISMATCH = "RISK_IDENTITY_MISMATCH"
    NO_VALID_EXPOSURE_EVALUATION = "NO_VALID_EXPOSURE_EVALUATION"
    EXPOSURE_IDENTITY_MISMATCH = "EXPOSURE_IDENTITY_MISMATCH"
    BANKROLL_FACTS_MISSING = "BANKROLL_FACTS_MISSING"
    WRONG_BANKROLL_SCOPE = "WRONG_BANKROLL_SCOPE"
    PUBLICATION_STATE_MISSING = "PUBLICATION_STATE_MISSING"
    PUBLICATION_IDENTITY_MISMATCH = "PUBLICATION_IDENTITY_MISMATCH"
    QUALITY_GATE_EVALUATION_FAILED = "QUALITY_GATE_EVALUATION_FAILED"
    QUALITY_GATE_PERSISTENCE_FAILED = "QUALITY_GATE_PERSISTENCE_FAILED"
    ORCHESTRATION_PERSISTENCE_FAILED = "ORCHESTRATION_PERSISTENCE_FAILED"
    PUBLISHER_CONFIRMED_FAILURE = "PUBLISHER_CONFIRMED_FAILURE"
    PUBLISHER_INDETERMINATE_FAILURE = "PUBLISHER_INDETERMINATE_FAILURE"
    PUBLISHER_DUPLICATE_BLOCKED = "PUBLISHER_DUPLICATE_BLOCKED"
    DRY_RUN = "DRY_RUN"
    PUBLISHER_DISABLED = "PUBLISHER_DISABLED"


class PublisherResultStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    DUPLICATE_BLOCKED = "DUPLICATE_BLOCKED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    INDETERMINATE_FAILURE = "INDETERMINATE_FAILURE"


@dataclass(frozen=True, slots=True)
class OfficialPredictionFacts:
    prediction_id: str
    match_id: str
    model_version: str
    market: str
    selection: str
    market_line: Decimal | None
    raw_probability: Decimal
    decimal_odds: Decimal
    odds_timestamp: datetime
    expected_value: Decimal
    confidence: ConfidenceLevel
    prediction_timestamp: datetime
    kickoff_timestamp: datetime
    core_data_timestamp: datetime
    supporting_data_status: FactStatus
    market_availability: MarketAvailability
    lineup_status: LineupStatus
    injury_status: FactStatus


@dataclass(frozen=True, slots=True)
class ModelHealthRecord:
    record_id: str
    model_version: str
    status: ModelHealthStatus
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class RiskEvaluationRecord:
    evaluation_id: str
    prediction_id: str
    match_id: str
    model_version: str
    market: str
    selection: str
    market_line: Decimal | None
    bankroll_scope: RiskProductScope
    decision: RiskAssessmentDecision
    evaluated_at: datetime


@dataclass(frozen=True, slots=True)
class ExposureEvaluationRecord:
    evaluation_id: str
    prediction_id: str
    match_id: str
    model_version: str
    market: str
    selection: str
    market_line: Decimal | None
    bankroll_scope: RiskProductScope
    decision: ExposureDecision
    evaluated_at: datetime


@dataclass(frozen=True, slots=True)
class BankrollScopeRecord:
    reference_id: str
    product_scope: RiskProductScope
    snapshot_timestamp: datetime


@dataclass(frozen=True, slots=True)
class PublicationStateRecord:
    prediction_id: str
    match_id: str
    state: PublicationDeliveryState
    observed_at: datetime
    attempt_reference: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialCandidateAssemblyRequest:
    prediction: OfficialPredictionFacts
    calibration_records: tuple[ProbabilityCalibrationReport, ...]
    model_health_records: tuple[ModelHealthRecord, ...]
    risk_evaluations: tuple[RiskEvaluationRecord, ...]
    exposure_evaluations: tuple[ExposureEvaluationRecord, ...]
    bankroll: BankrollScopeRecord | None
    evaluation_timestamp: datetime
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class OfficialCandidateAssembly:
    prediction_id: str
    match_id: str
    gate_candidate: OfficialPublicationCandidate
    calibration_run_id: str
    calibration_method: str
    calibration_timestamp: datetime
    risk_evaluation_id: str
    risk_evaluated_at: datetime
    exposure_evaluation_id: str
    exposure_evaluated_at: datetime
    bankroll_reference_id: str
    bankroll_snapshot_timestamp: datetime
    publication_state: PublicationDeliveryState
    publication_attempt_reference: str | None
    verified_expected_value: Decimal
    normalized_input: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class OfficialPredictionPublicationResult:
    status: PublisherResultStatus
    attempt_reference: str | None
    ordered_reason_codes: tuple[str, ...] = ()
    internal_explanations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ApprovedOfficialPredictionPublication:
    """Persisted approval evidence supplied to the atomic publisher adapter."""

    orchestration_id: str
    assembly: OfficialCandidateAssembly
    candidate_fingerprint: str
    quality_gate_evaluation: OfficialQualityGateEvaluation
    approval_status: QualityGateStatus
    evaluated_at: datetime
    dry_run: bool


@dataclass(frozen=True, slots=True)
class OfficialPredictionOrchestrationOutcome:
    orchestration_id: str
    prediction_id: str
    candidate_fingerprint: str | None
    quality_gate_evaluation_id: str | None
    final_status: OrchestrationStatus
    ordered_reason_codes: tuple[str, ...]
    internal_explanations: tuple[str, ...]
    publication_attempt_reference: str | None
    evaluated_timestamp: datetime
    dry_run: bool
    policy_version: str
    model_version: str


@dataclass(frozen=True, slots=True)
class OfficialPredictionOrchestrationRecord:
    outcome: OfficialPredictionOrchestrationOutcome
    normalized_input: tuple[tuple[str, str], ...]
    created_timestamp: datetime
