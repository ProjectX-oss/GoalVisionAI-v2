"""Immutable domain models for Official selection-to-candidate preparation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.official_prediction_candidate_registry import (
    CandidateLifecycleState,
    CandidateRegistrationStatus,
    OfficialPredictionCandidateRegistrationCommand,
    OfficialPredictionCandidateVersion,
    OfficialPredictionReasoningFact,
)
from app.official_prediction_orchestration import (
    BankrollScopeRecord,
    ExposureEvaluationRecord,
    RiskEvaluationRecord,
)
from app.official_prediction_selection import (
    OfficialSelectionDecision,
    OfficialSelectionRiskInput,
)
from app.publication_quality_gate import (
    ConfidenceLevel,
    FactStatus,
    LineupStatus,
    MarketAvailability,
)
from app.risk_management import (
    BankrollStateSnapshot,
    CorrelationGroup,
    ExposureSnapshot,
    RiskAssessmentContext,
    RiskAssessmentDecision,
    RiskAssessmentRequest,
    RiskAuditRecord,
    RiskProductScope,
    StakeRecommendation,
)


class CandidatePreparationStatus(str, Enum):
    CANDIDATE_REGISTERED = "CANDIDATE_REGISTERED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    NO_REGISTRATION_INELIGIBLE = "NO_REGISTRATION_INELIGIBLE"
    NO_REGISTRATION_REVIEW_REQUIRED = "NO_REGISTRATION_REVIEW_REQUIRED"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_PROVENANCE = "REJECTED_PROVENANCE"
    REJECTED_SCOPE = "REJECTED_SCOPE"
    REJECTED_INVALID_RISK_RESULT = "REJECTED_INVALID_RISK_RESULT"
    RISK_EXECUTION_FAILED = "RISK_EXECUTION_FAILED"
    CANDIDATE_REGISTRATION_REJECTED = "CANDIDATE_REGISTRATION_REJECTED"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class CandidatePreparationReason(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    NO_SELECTED_DECISION = "NO_SELECTED_DECISION"
    SELECTION_NOT_SELECTED = "SELECTION_NOT_SELECTED"
    SELECTION_FINGERPRINT_INVALID = "SELECTION_FINGERPRINT_INVALID"
    ASSESSMENT_FINGERPRINT_INVALID = "ASSESSMENT_FINGERPRINT_INVALID"
    PROVENANCE_INCOMPLETE = "PROVENANCE_INCOMPLETE"
    PERSISTED_SELECTION_MISMATCH = "PERSISTED_SELECTION_MISMATCH"
    PERSISTED_ASSESSMENT_MISMATCH = "PERSISTED_ASSESSMENT_MISMATCH"
    MATCH_MISMATCH = "MATCH_MISMATCH"
    KICKOFF_MISMATCH = "KICKOFF_MISMATCH"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    NON_OFFICIAL_SCOPE = "NON_OFFICIAL_SCOPE"
    UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"
    INVALID_BANKROLL = "INVALID_BANKROLL"
    INVALID_EXPOSURE = "INVALID_EXPOSURE"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    CORRECT_SCORE_FORBIDDEN = "CORRECT_SCORE_FORBIDDEN"
    LIVE_MARKET_FORBIDDEN = "LIVE_MARKET_FORBIDDEN"
    COMBO_MARKET_FORBIDDEN = "COMBO_MARKET_FORBIDDEN"
    ODDS_BELOW_OFFICIAL_MINIMUM = "ODDS_BELOW_OFFICIAL_MINIMUM"
    EV_BELOW_OFFICIAL_MINIMUM = "EV_BELOW_OFFICIAL_MINIMUM"
    SELECTION_NOT_ACTIONABLE = "SELECTION_NOT_ACTIONABLE"
    SELECTION_NOT_FRESH = "SELECTION_NOT_FRESH"
    POLICY_INCOMPATIBLE = "POLICY_INCOMPATIBLE"
    INVALID_METADATA = "INVALID_METADATA"
    REQUEST_IDENTITY_CONFLICT = "REQUEST_IDENTITY_CONFLICT"
    RISK_EXECUTION_FAILED = "RISK_EXECUTION_FAILED"
    RISK_RESULT_MALFORMED = "RISK_RESULT_MALFORMED"
    RISK_INELIGIBLE = "RISK_INELIGIBLE"
    RISK_REVIEW_REQUIRED = "RISK_REVIEW_REQUIRED"
    CANDIDATE_REGISTERED = "CANDIDATE_REGISTERED"
    CANDIDATE_IDEMPOTENT = "CANDIDATE_IDEMPOTENT"
    CANDIDATE_SUPERSEDED_PREVIOUS = "CANDIDATE_SUPERSEDED_PREVIOUS"
    CANDIDATE_REJECTED = "CANDIDATE_REJECTED"
    CANDIDATE_SCOPE_REJECTED = "CANDIDATE_SCOPE_REJECTED"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    REGISTRY_CONFLICT = "REGISTRY_CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    QUALITY_GATE_HANDOFF_INVALID = "QUALITY_GATE_HANDOFF_INVALID"


@dataclass(frozen=True, slots=True)
class OfficialBankrollPreparationContext:
    snapshot_identity: str
    fingerprint: str
    match_id: str
    kickoff_timestamp: datetime
    available_bankroll: Decimal
    reserved_exposure: Decimal
    state: BankrollStateSnapshot


@dataclass(frozen=True, slots=True)
class OfficialExposurePreparationContext:
    snapshot_identity: str
    fingerprint: str
    match_id: str
    kickoff_timestamp: datetime
    snapshot: ExposureSnapshot


@dataclass(frozen=True, slots=True)
class OfficialCandidateRegistrationFacts:
    fixture_id: int
    source_event_id: str
    odds_source_id: str
    competition_id: str | None
    competition_name: str
    home_team_id: str | None
    home_team_name: str
    away_team_id: str | None
    away_team_name: str
    raw_model_probability: Decimal
    core_match_data_timestamp: datetime
    lineup_status: LineupStatus
    lineup_data_timestamp: datetime | None
    injury_suspension_status: FactStatus
    injury_suspension_data_timestamp: datetime | None
    confidence_level: ConfidenceLevel
    public_reasoning_facts: tuple[OfficialPredictionReasoningFact, ...]
    source_data_version: str
    supporting_data_status: FactStatus
    market_availability: MarketAvailability
    model_confidence: Decimal | None
    uncertainty: Decimal | None
    calibration_sample_size: int
    model_sample_size: int
    correlation_groups: tuple[CorrelationGroup, ...] = ()
    team_ids: tuple[str, ...] = ()
    market_family: str | None = None
    model_name: str | None = None
    calibration_artifact_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OfficialCandidatePreparationCommand:
    integration_request_identity: str
    selection: OfficialSelectionDecision | None
    bankroll: OfficialBankrollPreparationContext
    exposure: OfficialExposurePreparationContext
    candidate_facts: OfficialCandidateRegistrationFacts
    risk_assessment_timestamp: datetime | None
    candidate_preparation_timestamp: datetime | None
    bankroll_scope: RiskProductScope | str
    destination_scope: RiskProductScope | str
    integration_policy_version: str
    metadata_version: str = "v1"
    source_run_identity: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedOfficialRiskHandoff:
    selection: OfficialSelectionRiskInput
    request: RiskAssessmentRequest
    context: RiskAssessmentContext
    bankroll_snapshot_identity: str
    bankroll_fingerprint: str
    available_bankroll: Decimal
    reserved_exposure: Decimal
    exposure_snapshot_identity: str
    exposure_fingerprint: str
    handoff_fingerprint: str


@dataclass(frozen=True, slots=True)
class PreparedOfficialCandidateRegistration:
    command: OfficialPredictionCandidateRegistrationCommand
    candidate_mapping_fingerprint: str


@dataclass(frozen=True, slots=True)
class OfficialCandidatePreparationRiskSnapshot:
    risk_snapshot_id: str
    integration_execution_id: str
    risk_handoff_fingerprint: str
    risk_fingerprint: str
    audit: RiskAuditRecord
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class OfficialCandidatePreparationExecution:
    integration_execution_id: str
    integration_request_identity: str
    preparation_request_fingerprint: str
    integration_fingerprint: str
    selection_decision_id: str
    selected_value_assessment_id: str
    match_id: str
    kickoff_timestamp: datetime
    risk_assessment_timestamp: datetime
    candidate_preparation_timestamp: datetime
    bankroll_snapshot_identity: str
    bankroll_fingerprint: str
    exposure_snapshot_identity: str
    exposure_fingerprint: str
    risk_handoff_fingerprint: str | None
    risk_outcome: RiskAssessmentDecision | None
    risk_assessment_id: str | None
    risk_fingerprint: str | None
    candidate_mapping_fingerprint: str | None
    candidate_registry_outcome: CandidateRegistrationStatus | None
    registry_candidate_id: str | None
    candidate_version: int | None
    candidate_fingerprint: str | None
    previous_candidate_id: str | None
    final_status: CandidatePreparationStatus
    integration_policy_version: str
    ordered_reason_codes: tuple[CandidatePreparationReason, ...]
    explanations: tuple[str, ...]
    deterministic_execution_summary: tuple[tuple[str, str], ...]
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class PreparationExecutionWithRiskSnapshot:
    execution: OfficialCandidatePreparationExecution
    risk_snapshot: OfficialCandidatePreparationRiskSnapshot | None


@dataclass(frozen=True, slots=True)
class OfficialCandidatePreparationOutcome:
    integration_execution_id: str | None
    integration_request_identity: str
    selection_decision_id: str | None
    selected_value_assessment_id: str | None
    match_id: str | None
    kickoff_timestamp: datetime | None
    risk_assessment_id: str | None
    risk_outcome: RiskAssessmentDecision | None
    stake_recommendation: StakeRecommendation | None
    registry_candidate_id: str | None
    candidate_version: int | None
    candidate_registry_outcome: CandidateRegistrationStatus | None
    final_status: CandidatePreparationStatus
    ordered_reason_codes: tuple[CandidatePreparationReason, ...]
    explanations: tuple[str, ...]
    integration_fingerprint: str | None
    candidate_fingerprint: str | None
    risk_assessment_timestamp: datetime | None
    candidate_preparation_timestamp: datetime | None
    integration_policy_version: str
    execution: OfficialCandidatePreparationExecution | None = None


@dataclass(frozen=True, slots=True)
class OfficialCandidateQualityGateHandoff:
    candidate: OfficialPredictionCandidateVersion
    lifecycle_state: CandidateLifecycleState
    execution: OfficialCandidatePreparationExecution
    risk_snapshot: OfficialCandidatePreparationRiskSnapshot
    risk_evaluation: RiskEvaluationRecord
    exposure_evaluation: ExposureEvaluationRecord
    bankroll: BankrollScopeRecord
