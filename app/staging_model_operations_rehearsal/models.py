"""Immutable contracts for the controlled staging rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


EVIDENCE_SCHEMA_VERSION = "goalvision-staging-model-operations-rehearsal-v1"
STAGING_SOURCE_LABEL = "CONTROLLED_SYNTHETIC_STAGING_SOURCE"


class ArtifactMode(str, Enum):
    REAL_ONLY = "real-only"


class InitialStagingState(str, Enum):
    STAGING_UNBOOTSTRAPPED = "STAGING_UNBOOTSTRAPPED"
    STAGING_CHAMPION_PRESENT = "STAGING_CHAMPION_PRESENT"
    STAGING_RECOVERY_REQUIRED = "STAGING_RECOVERY_REQUIRED"
    STAGING_INVALID = "STAGING_INVALID"


@dataclass(frozen=True, slots=True)
class StagingRehearsalCommand:
    source_database: str
    destination_directory: str
    environment: str
    scope: str
    timestamp: str
    source_commit: str
    audit_output_mode: str = "both"
    evidence_report_destination: str | None = None
    artifact_mode: ArtifactMode = ArtifactMode.REAL_ONLY


@dataclass(frozen=True, slots=True)
class SourceDatabaseEvidence:
    filename: str
    sha256_before: str
    sha256_after: str
    backup_sha256: str
    file_size: int
    schema_version: int
    foreign_key_violations: int


@dataclass(frozen=True, slots=True)
class ArtifactCandidate:
    model_artifact_id: str
    model_artifact_fingerprint: str
    training_run_id: str
    preprocessing_fingerprint: str
    estimator_fingerprint: str
    calibration_artifact_set_id: str | None
    calibration_artifact_set_fingerprint: str | None
    backtest_run_id: str | None
    comparison_run_id: str | None
    recommendation_id: str | None
    settled_shadow_count: int
    feature_schema_version: str | None
    probability_contract_version: str | None
    runtime_compatibility_version: str | None
    complete: bool
    audit_eligible: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArtifactInventory:
    candidates: tuple[ArtifactCandidate, ...]
    selected_candidate_id: str | None
    used_fixture_fallback: bool
    inventory_reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuditCapture:
    phase: str
    output_mode: str
    exit_code: int
    overall_status: str
    staging_readiness: str
    audit_fingerprint: str
    summary_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class StagingRehearsalOutcome:
    schema_version: str
    status: str
    source_commit: str
    timestamp: str
    environment: str
    scope: str
    source: SourceDatabaseEvidence
    artifact_inventory: ArtifactInventory
    artifact_mode: str
    fixture_fallback_used: bool
    real_artifact_chain_complete: bool
    real_artifact_chain_fingerprint: str
    selected_artifact_mode: str
    selected_artifact_references: tuple[tuple[str, str], ...]
    initial_state: str
    preflight_audits: tuple[AuditCapture, ...]
    final_audits: tuple[AuditCapture, ...]
    foundation_fingerprint: str
    disposable_before_fingerprint: str
    disposable_after_fingerprint: str
    initial_generation_id: str
    activation_plan_id: str
    activation_plan_fingerprint: str
    activation_execution_fingerprint: str
    activated_generation_id: str
    rollback_plan_id: str
    rollback_plan_fingerprint: str
    rollback_execution_fingerprint: str
    rollback_generation_id: str
    resolver_sequence: tuple[str, str, str]
    generation_chain: tuple[str, ...]
    registry_event_types: tuple[str, ...]
    final_counts: tuple[tuple[str, int], ...]
    protected_state_unchanged: bool
    atomicity_checks: tuple[str, ...]
    append_only_trigger_count: int
    foreign_key_violations: int
    command_statuses: tuple[tuple[str, str | None, int], ...]
    evidence_fingerprint: str
