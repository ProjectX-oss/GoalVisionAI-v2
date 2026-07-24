"""Typed operator-facing results for manual model operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


OUTPUT_SCHEMA_VERSION = "goalvision-model-operations-output-v1"
SUPPORTED_MODEL_SCOPES = ("OFFICIAL_GLOBAL",)


class OperationMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    STATE_CHANGING = "STATE_CHANGING"


class OperatorStatus(str, Enum):
    BOOTSTRAP_EXECUTED = "BOOTSTRAP_EXECUTED"
    BOOTSTRAP_REJECTED = "BOOTSTRAP_REJECTED"
    ACTIVATION_PLAN_PREPARED = "ACTIVATION_PLAN_PREPARED"
    ACTIVATION_EXECUTED = "ACTIVATION_EXECUTED"
    ACTIVATION_ALREADY_EXECUTED = "ACTIVATION_ALREADY_EXECUTED"
    ACTIVATION_REJECTED = "ACTIVATION_REJECTED"
    ACTIVATION_STALE_PLAN = "ACTIVATION_STALE_PLAN"
    ACTIVATION_CONFLICT = "ACTIVATION_CONFLICT"
    ROLLBACK_PLAN_PREPARED = "ROLLBACK_PLAN_PREPARED"
    ROLLBACK_EXECUTED = "ROLLBACK_EXECUTED"
    ROLLBACK_ALREADY_EXECUTED = "ROLLBACK_ALREADY_EXECUTED"
    ROLLBACK_REJECTED = "ROLLBACK_REJECTED"
    ROLLBACK_STALE_PLAN = "ROLLBACK_STALE_PLAN"
    ROLLBACK_CONFLICT = "ROLLBACK_CONFLICT"
    CONFIRMATION_REJECTED = "CONFIRMATION_REJECTED"
    CHAMPION_SHOWN = "CHAMPION_SHOWN"
    ACTIVATION_SHOWN = "ACTIVATION_SHOWN"
    GENERATIONS_LISTED = "GENERATIONS_LISTED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    DATABASE_REJECTED = "DATABASE_REJECTED"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class DiagnosticStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    INVALID_STATE = "INVALID_STATE"


@dataclass(frozen=True, slots=True)
class DiagnosticFinding:
    code: str
    severity: DiagnosticStatus
    detail: str
    recovery: str


@dataclass(frozen=True, slots=True)
class OperatorResult:
    command: str
    status: str
    success: bool
    mode: OperationMode
    production_state_changed: bool
    model_scope: str | None = None
    reason_codes: tuple[str, ...] = ()
    recovery_guidance: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)
    output_schema_version: str = OUTPUT_SCHEMA_VERSION

    @property
    def exit_code(self) -> int:
        if self.success:
            return 0
        if self.status in {
            OperatorStatus.INVALID_ARGUMENTS.value,
            OperatorStatus.CONFIRMATION_REJECTED.value,
        }:
            return 2
        if self.status == OperatorStatus.NOT_FOUND.value:
            return 3
        if self.status == OperatorStatus.DATABASE_REJECTED.value:
            return 4
        if self.status in {
            DiagnosticStatus.WARNING.value,
            DiagnosticStatus.RECOVERY_REQUIRED.value,
            DiagnosticStatus.INVALID_STATE.value,
        }:
            return 5
        return 6
