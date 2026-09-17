"""Central audit inventory and staging-readiness policy."""

from __future__ import annotations

from .models import AuditCheck, AuditSeverity, AuditStatus, StagingReadiness

AUDIT_SCHEMA_VERSION = "goalvision-model-activation-audit-v1"
SUPPORTED_ENVIRONMENTS = ("LAB", "STAGING", "PRODUCTION")
SUPPORTED_SCOPES = ("OFFICIAL_GLOBAL",)

ACTIVATION_TABLES = (
    "model_activation_requests",
    "model_activation_plans",
    "model_rollback_requests",
    "model_rollback_plans",
    "model_activation_validations",
    "model_champion_generations",
    "model_champion_registry_events",
    "model_activation_executions",
    "model_rollback_executions",
    "model_activation_evidence_links",
)
REQUIRED_INDEXES = (
    "idx_champion_scope_generation",
    "idx_champion_model",
    "idx_activation_request_scope",
    "idx_rollback_request_scope",
    "idx_activation_evidence_shadow",
)
REQUIRED_TRIGGERS = tuple(
    f"{table}_{operation}"
    for table in ACTIVATION_TABLES
    for operation in ("no_update", "no_delete")
)
REQUIRED_FOREIGN_KEYS = {
    "model_activation_plans": {
        ("activation_request_id", "model_activation_requests"),
    },
    "model_rollback_plans": {
        ("rollback_request_id", "model_rollback_requests"),
        ("target_champion_generation_id", "model_champion_generations"),
    },
    "model_activation_validations": {
        ("activation_plan_id", "model_activation_plans"),
        ("rollback_plan_id", "model_rollback_plans"),
    },
    "model_champion_generations": {
        ("model_artifact_id", "historical_model_artifacts"),
        (
            "calibration_artifact_set_id",
            "historical_probability_calibration_artifact_sets",
        ),
        ("previous_champion_generation_id", "model_champion_generations"),
        ("activation_plan_id", "model_activation_plans"),
        ("rollback_plan_id", "model_rollback_plans"),
    },
    "model_champion_registry_events": {
        ("champion_generation_id", "model_champion_generations"),
    },
    "model_activation_executions": {
        ("activation_plan_id", "model_activation_plans"),
        ("champion_generation_id", "model_champion_generations"),
    },
    "model_rollback_executions": {
        ("rollback_plan_id", "model_rollback_plans"),
        ("champion_generation_id", "model_champion_generations"),
    },
    "model_activation_evidence_links": {
        ("activation_plan_id", "model_activation_plans"),
        ("shadow_execution_id", "shadow_evaluation_executions"),
    },
}


def overall_status(checks: tuple[AuditCheck, ...]) -> AuditStatus:
    if not checks:
        return AuditStatus.AUDIT_INCOMPLETE
    if any(item.severity is AuditSeverity.BLOCKER for item in checks):
        return AuditStatus.AUDIT_BLOCKED
    if any(item.severity is AuditSeverity.WARNING for item in checks):
        return AuditStatus.AUDIT_PASSED_WITH_WARNINGS
    return AuditStatus.AUDIT_PASSED


def assess_staging_readiness(
    status: AuditStatus,
    checks: tuple[AuditCheck, ...],
) -> StagingReadiness:
    if status in {AuditStatus.AUDIT_BLOCKED, AuditStatus.AUDIT_INCOMPLETE}:
        return StagingReadiness.STAGING_REHEARSAL_BLOCKED
    if any(
        item.mandatory and item.severity is not AuditSeverity.PASS
        for item in checks
    ):
        return StagingReadiness.STAGING_REHEARSAL_NOT_READY
    return StagingReadiness.STAGING_REHEARSAL_READY
