"""Immutable contracts for the manual Registered Candidate publication pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.official_prediction_candidate_registry import (
    CandidateLifecycleState,
    OfficialPredictionCandidateVersion,
)
from app.official_prediction_orchestration import OfficialCandidateAssemblyRequest
from app.risk_management import RiskAssessmentDecision, RiskProductScope, StakeRecommendation


class PipelineStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    DRY_RUN_COMPLETED = "DRY_RUN_COMPLETED"
    NO_PUBLICATION_QUALITY_GATE_REJECTED = "NO_PUBLICATION_QUALITY_GATE_REJECTED"
    NO_PUBLICATION_REVIEW_REQUIRED = "NO_PUBLICATION_REVIEW_REQUIRED"
    PUBLICATION_IN_PROGRESS = "PUBLICATION_IN_PROGRESS"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_CANDIDATE_STATE = "REJECTED_CANDIDATE_STATE"
    REJECTED_PROVENANCE = "REJECTED_PROVENANCE"
    REJECTED_SCOPE = "REJECTED_SCOPE"
    REJECTED_INVALID_GATE_RESULT = "REJECTED_INVALID_GATE_RESULT"
    QUALITY_GATE_EXECUTION_FAILED = "QUALITY_GATE_EXECUTION_FAILED"
    ORCHESTRATION_REJECTED = "ORCHESTRATION_REJECTED"
    ORCHESTRATION_FAILED = "ORCHESTRATION_FAILED"
    PUBLICATION_CLAIM_FAILED = "PUBLICATION_CLAIM_FAILED"
    PUBLICATION_SEND_FAILED = "PUBLICATION_SEND_FAILED"
    PUBLICATION_FINALIZATION_FAILED = "PUBLICATION_FINALIZATION_FAILED"
    ALREADY_PUBLISHED_CONFLICT = "ALREADY_PUBLISHED_CONFLICT"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class CandidateState(str, Enum):
    READY = "READY"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
    INVALIDATED = "INVALIDATED"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    INDETERMINATE = "INDETERMINATE"


class PipelinePublicationState(str, Enum):
    NOT_PUBLISHED = "NOT_PUBLISHED"
    PUBLISHED = "PUBLISHED"
    ACTIVE_CLAIM = "ACTIVE_CLAIM"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    INDETERMINATE = "INDETERMINATE"
    UNKNOWN = "UNKNOWN"


class PipelineStage(str, Enum):
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    CANDIDATE_STATE_VERIFICATION = "CANDIDATE_STATE_VERIFICATION"
    PUBLICATION_STATE_VERIFICATION = "PUBLICATION_STATE_VERIFICATION"
    QUALITY_GATE = "QUALITY_GATE"
    ORCHESTRATION = "ORCHESTRATION"
    MESSAGE_ASSEMBLY = "MESSAGE_ASSEMBLY"
    PUBLICATION_CLAIM = "PUBLICATION_CLAIM"
    TELEGRAM_SEND = "TELEGRAM_SEND"
    PUBLICATION_FINALIZATION = "PUBLICATION_FINALIZATION"


@dataclass(frozen=True, slots=True)
class CandidateStateVerification:
    state: CandidateState
    candidate: OfficialPredictionCandidateVersion | None
    is_current: bool
    terminal_publication: bool = False
    fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class PublicationStateVerification:
    state: PipelinePublicationState
    observed_at: datetime
    publication_event_id: str | None = None
    publication_fingerprint: str | None = None
    message_fingerprint: str | None = None
    claim_identity: str | None = None
    telegram_message_reference: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialPredictionPipelineCommand:
    candidate: OfficialPredictionCandidateVersion | None
    assembly_request: OfficialCandidateAssemblyRequest | None
    pipeline_request_identity: str
    candidate_id: str
    candidate_version: int
    candidate_fingerprint: str
    candidate_lifecycle_status: CandidateLifecycleState | str
    match_id: str
    kickoff_timestamp: datetime
    bankroll_scope: RiskProductScope | str
    destination_scope: RiskProductScope | str
    normalized_market: str
    normalized_selection: str
    normalized_line: Decimal | None
    preparation_execution_id: str
    selection_decision_id: str
    selected_value_assessment_id: str
    model_input_id: str
    inference_id: str
    calibrated_assembly_id: str
    calibration_set_id: str
    odds_snapshot_identity: str
    bookmaker_provider_identity: str
    odds_fingerprint: str
    calibrated_assembly_fingerprint: str
    selection_fingerprint: str
    value_assessment_fingerprint: str
    risk_fingerprint: str
    candidate_preparation_fingerprint: str
    bookmaker_odds: Decimal
    calibrated_probability: Decimal
    fair_odds: Decimal
    implied_probability: Decimal
    expected_value: Decimal
    value_classification: str
    freshness: str
    risk_outcome: RiskAssessmentDecision | str
    stake_recommendation: StakeRecommendation | None
    internal_stake_percentage: Decimal
    stake_amount: Decimal
    bankroll_snapshot_identity: str
    exposure_snapshot_identity: str
    quality_gate_evaluation_timestamp: datetime
    pipeline_execution_timestamp: datetime
    publication_effective_timestamp: datetime | None
    pipeline_policy_version: str
    metadata_version: str
    manual_run_identity: str | None = None
    dry_run: bool = False
    retry: bool = False
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PipelineStageEvent:
    stage_event_id: str
    pipeline_execution_id: str
    stage_order: int
    stage_name: PipelineStage
    stage_status: str
    referenced_domain_record_id: str | None
    referenced_fingerprint: str | None
    ordered_reason_codes: tuple[str, ...]
    deterministic_stage_snapshot: tuple[tuple[str, str], ...]
    created_timestamp: datetime


@dataclass(frozen=True, slots=True)
class OfficialPredictionPipelineOutcome:
    pipeline_execution_id: str | None
    pipeline_request_identity: str
    manual_run_identity: str | None
    candidate_id: str | None
    candidate_version: int | None
    candidate_fingerprint: str | None
    match_id: str | None
    kickoff_timestamp: datetime | None
    quality_gate_evaluation_id: str | None
    quality_gate_status: str | None
    quality_gate_fingerprint: str | None
    orchestration_id: str | None
    orchestration_status: str | None
    orchestration_fingerprint: str | None
    publication_event_id: str | None
    publication_status: str | None
    publication_fingerprint: str | None
    publication_claim_identity: str | None
    message_fingerprint: str | None
    telegram_message_reference: str | None
    final_status: PipelineStatus
    dry_run: bool
    retry: bool
    ordered_reason_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    request_fingerprint: str | None
    pipeline_fingerprint: str | None
    quality_gate_evaluation_timestamp: datetime | None
    pipeline_execution_timestamp: datetime | None
    publication_effective_timestamp: datetime | None
    pipeline_policy_version: str
    candidate_state_result: str | None = None
    publication_state_result: str | None = None
    deterministic_execution_snapshot: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PipelineExecutionWithStages:
    execution: OfficialPredictionPipelineOutcome
    stages: tuple[PipelineStageEvent, ...]


@dataclass(frozen=True, slots=True)
class ManualPipelineRunSummary:
    manual_run_identity: str | None
    selected_count: int
    published_count: int
    rejected_count: int
    retry_required_count: int
    failed_count: int
    outcomes: tuple[OfficialPredictionPipelineOutcome, ...]
