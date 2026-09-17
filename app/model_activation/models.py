"""Immutable activation, rollback, registry, and resolution contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class ActivationStatus(str, Enum):
    ACTIVATION_PLAN_PREPARED = "ACTIVATION_PLAN_PREPARED"
    ACTIVATION_EXECUTED = "ACTIVATION_EXECUTED"
    ACTIVATION_ALREADY_EXECUTED = "ACTIVATION_ALREADY_EXECUTED"
    ACTIVATION_NOT_ELIGIBLE = "ACTIVATION_NOT_ELIGIBLE"
    ACTIVATION_CONFLICT = "ACTIVATION_CONFLICT"
    ACTIVATION_STALE_PLAN = "ACTIVATION_STALE_PLAN"
    ACTIVATION_STATE_CHANGED = "ACTIVATION_STATE_CHANGED"
    ROLLBACK_PLAN_PREPARED = "ROLLBACK_PLAN_PREPARED"
    ROLLBACK_EXECUTED = "ROLLBACK_EXECUTED"
    ROLLBACK_ALREADY_EXECUTED = "ROLLBACK_ALREADY_EXECUTED"
    ROLLBACK_NOT_ELIGIBLE = "ROLLBACK_NOT_ELIGIBLE"
    ROLLBACK_CONFLICT = "ROLLBACK_CONFLICT"
    ROLLBACK_STALE_PLAN = "ROLLBACK_STALE_PLAN"
    CHAMPION_RESOLVED = "CHAMPION_RESOLVED"
    CHAMPION_STATE_INVALID = "CHAMPION_STATE_INVALID"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class GenerationReason(str, Enum):
    INITIAL_REGISTRATION = "INITIAL_REGISTRATION"
    APPROVED_ACTIVATION = "APPROVED_ACTIVATION"
    MANUAL_ROLLBACK = "MANUAL_ROLLBACK"


@dataclass(frozen=True, slots=True)
class RuntimeArtifactReference:
    model_artifact_id: str
    model_artifact_fingerprint: str
    preprocessing_fingerprint: str
    calibration_artifact_set_id: str
    calibration_artifact_set_fingerprint: str
    feature_schema_version: str
    feature_schema_fingerprint: str
    target_contract_version: str
    probability_contract_version: str
    runtime_compatibility_version: str


@dataclass(frozen=True, slots=True)
class ActivationRequest:
    activation_request_id: str
    activation_name: str
    model_scope: str
    current_champion_generation_id: str
    current_champion_generation_fingerprint: str
    current_champion: RuntimeArtifactReference
    challenger: RuntimeArtifactReference
    comparison_run_id: str
    comparison_run_fingerprint: str
    challenger_candidate_id: str
    recommendation_id: str
    recommendation_fingerprint: str
    evidence_cutoff_timestamp_utc: datetime | str
    requested_timestamp_utc: datetime | str
    activation_reason: str
    operator_identity: str
    warning_override_reason: str | None = None
    policy_version: str = "controlled-model-activation-policy-v1"
    metadata_version: str = "v1"


@dataclass(frozen=True, slots=True)
class ActivationValidation:
    validation_id: str
    category: str
    name: str
    status: ValidationStatus
    detail_snapshot: str
    validation_fingerprint: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class ActivationEvidence:
    settled_count: int
    observation_days: Decimal
    agreement_ratio: Decimal
    critical_disagreement_ratio: Decimal
    predictive_degradation: Decimal
    calibration_degradation: Decimal
    betting_performance_degradation: Decimal
    drawdown_deterioration: Decimal
    evidence_completeness: Decimal
    shadow_execution_ids: tuple[str, ...]
    shadow_execution_fingerprints: tuple[str, ...]
    shadow_settlement_fingerprints: tuple[str, ...]
    evidence_fingerprint: str


@dataclass(frozen=True, slots=True)
class ActivationPlan:
    activation_plan_id: str
    request: ActivationRequest
    request_fingerprint: str
    expected_registry_generation_number: int
    expected_registry_fingerprint: str
    validations: tuple[ActivationValidation, ...]
    evidence: ActivationEvidence
    policy_snapshot: str
    prepared_timestamp_utc: str
    activation_plan_fingerprint: str


@dataclass(frozen=True, slots=True)
class ChampionGeneration:
    champion_generation_id: str
    model_scope: str
    generation_number: int
    artifact: RuntimeArtifactReference
    activation_timestamp_utc: str
    activation_reason: GenerationReason
    activation_reason_detail: str
    source_recommendation_id: str | None
    source_recommendation_fingerprint: str | None
    source_shadow_evidence_fingerprint: str | None
    previous_champion_generation_id: str | None
    activation_plan_id: str | None
    rollback_plan_id: str | None
    generation_status: str
    generation_fingerprint: str


@dataclass(frozen=True, slots=True)
class ActivationExecutionCommand:
    activation_execution_request_id: str
    activation_plan_id: str
    activation_plan_fingerprint: str
    execution_timestamp_utc: datetime | str
    operator_identity: str


@dataclass(frozen=True, slots=True)
class RollbackRequest:
    rollback_request_id: str
    rollback_name: str
    model_scope: str
    current_champion_generation_id: str
    current_champion_generation_fingerprint: str
    target_champion_generation_id: str
    rollback_reason: str
    incident_reference: str
    operator_identity: str
    requested_timestamp_utc: datetime | str
    policy_version: str = "controlled-model-activation-policy-v1"
    metadata_version: str = "v1"


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    rollback_plan_id: str
    request: RollbackRequest
    request_fingerprint: str
    expected_registry_generation_number: int
    expected_registry_fingerprint: str
    target_generation: ChampionGeneration
    validations: tuple[ActivationValidation, ...]
    policy_snapshot: str
    prepared_timestamp_utc: str
    rollback_plan_fingerprint: str


@dataclass(frozen=True, slots=True)
class RollbackExecutionCommand:
    rollback_execution_request_id: str
    rollback_plan_id: str
    rollback_plan_fingerprint: str
    execution_timestamp_utc: datetime | str
    operator_identity: str


@dataclass(frozen=True, slots=True)
class ActivationOutcome:
    status: ActivationStatus
    model_scope: str
    plan_id: str | None
    plan_fingerprint: str | None
    champion_generation: ChampionGeneration | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChampionResolution:
    status: ActivationStatus
    model_scope: str
    champion_generation: ChampionGeneration | None
    reason_codes: tuple[str, ...]
