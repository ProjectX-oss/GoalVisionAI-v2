"""Immutable contracts for independent audit results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuditSeverity(str, Enum):
    PASS = "PASS"
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


class AuditStatus(str, Enum):
    AUDIT_PASSED = "AUDIT_PASSED"
    AUDIT_PASSED_WITH_WARNINGS = "AUDIT_PASSED_WITH_WARNINGS"
    AUDIT_BLOCKED = "AUDIT_BLOCKED"
    AUDIT_INCOMPLETE = "AUDIT_INCOMPLETE"


class StagingReadiness(str, Enum):
    STAGING_REHEARSAL_READY = "STAGING_REHEARSAL_READY"
    STAGING_REHEARSAL_NOT_READY = "STAGING_REHEARSAL_NOT_READY"
    STAGING_REHEARSAL_BLOCKED = "STAGING_REHEARSAL_BLOCKED"


@dataclass(frozen=True, slots=True)
class AuditCheck:
    check_id: str
    category: str
    severity: AuditSeverity
    summary: str
    evidence_references: tuple[str, ...] = ()
    remediation_status: str = "NOT_REQUIRED"
    mandatory: bool = True


@dataclass(frozen=True, slots=True)
class AuditReport:
    schema_version: str
    source_commit: str
    generated_timestamp_utc: str
    environment: str
    scope: str
    database_type: str
    overall_status: AuditStatus
    staging_readiness: StagingReadiness
    checks: tuple[AuditCheck, ...]
    summary_counts: tuple[tuple[str, int], ...]
    audit_fingerprint: str
