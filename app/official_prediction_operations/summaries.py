"""Stable operator-facing result schema and deterministic exit-code mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping

from .serialization import canonical_json, canonical_value


RESULT_SCHEMA = "goalvision_official_operations_result_v1"


class OperationsExitCode(IntEnum):
    SUCCESS = 0
    INVALID_ARGUMENTS = 2
    FIXTURE_VALIDATION_FAILURE = 3
    PROVENANCE_OR_CANDIDATE_REJECTION = 4
    QUALITY_GATE_NO_PUBLICATION = 5
    RETRY_OR_IN_PROGRESS = 6
    PUBLICATION_FAILURE = 7
    CONFLICT = 8
    PERSISTENCE_FAILURE = 9
    INTERNAL_FAILURE = 10


@dataclass(frozen=True, slots=True)
class OperationsResult:
    command: str
    success: bool
    final_status: str
    exit_code: int = 0
    fixture_id: str | None = None
    request_id: str | None = None
    execution_id: str | None = None
    candidate_id: str | None = None
    candidate_version: int | None = None
    match_id: str | None = None
    gate_status: str | None = None
    orchestration_status: str | None = None
    publication_status: str | None = None
    message_fingerprint: str | None = None
    reason_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    database_path: str | None = None
    environment: str | None = None
    dry_run: bool = False
    retry: bool = False
    timestamps: tuple[tuple[str, str], ...] = ()
    policy_versions: tuple[tuple[str, str], ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return canonical_value({"schema": RESULT_SCHEMA, **self.__dict_value()})

    def to_json(self, *, pretty: bool = True) -> str:
        return canonical_json(self.as_dict(), pretty=pretty)

    def to_human(self) -> str:
        lines = [
            f"Command: {self.command}",
            f"Status: {self.final_status}",
            f"Success: {'yes' if self.success else 'no'}",
        ]
        labels = (
            ("Fixture", self.fixture_id), ("Request", self.request_id),
            ("Execution", self.execution_id), ("Candidate", self.candidate_id),
            ("Match", self.match_id), ("Quality Gate", self.gate_status),
            ("Orchestration", self.orchestration_status),
            ("Publication", self.publication_status),
            ("Message fingerprint", self.message_fingerprint),
            ("Database", self.database_path), ("Environment", self.environment),
        )
        lines.extend(f"{label}: {value}" for label, value in labels if value is not None)
        if self.candidate_version is not None:
            lines.append(f"Candidate version: {self.candidate_version}")
        if self.reason_codes:
            lines.append("Reasons: " + ", ".join(self.reason_codes))
        if self.warnings:
            lines.append("Warnings: " + ", ".join(self.warnings))
        return "\n".join(lines)

    def __dict_value(self) -> dict[str, Any]:
        return {
            "command": self.command, "success": self.success,
            "final_status": self.final_status, "exit_code": self.exit_code,
            "fixture_id": self.fixture_id, "request_id": self.request_id,
            "execution_id": self.execution_id, "candidate_id": self.candidate_id,
            "candidate_version": self.candidate_version, "match_id": self.match_id,
            "gate_status": self.gate_status,
            "orchestration_status": self.orchestration_status,
            "publication_status": self.publication_status,
            "message_fingerprint": self.message_fingerprint,
            "reason_codes": self.reason_codes, "warnings": self.warnings,
            "database_path": self.database_path, "environment": self.environment,
            "dry_run": self.dry_run, "retry": self.retry,
            "timestamps": dict(self.timestamps),
            "policy_versions": dict(self.policy_versions),
            "details": self.details,
        }


def exit_code_for_status(status: str) -> OperationsExitCode:
    if status in {"VALID", "DRY_RUN_COMPLETED", "PUBLISHED", "IDEMPOTENT_EXISTING", "HEALTHY", "TERMINAL_SUCCESS"}:
        return OperationsExitCode.SUCCESS
    if status in {"NO_PUBLICATION_QUALITY_GATE_REJECTED", "NO_PUBLICATION_REVIEW_REQUIRED", "QUALITY_GATE_REJECTED", "REVIEW_REQUIRED", "TERMINAL_NO_PUBLICATION"}:
        return OperationsExitCode.QUALITY_GATE_NO_PUBLICATION
    if status in {"PUBLICATION_IN_PROGRESS", "RETRY_REQUIRED", "ACTIVE_CLAIM", "RETRYABLE_BEFORE_CLAIM", "RETRYABLE_SEND_FAILURE", "INDETERMINATE_POST_SEND"}:
        return OperationsExitCode.RETRY_OR_IN_PROGRESS
    if status in {"CONFLICT", "CONFLICTED", "ALREADY_PUBLISHED_CONFLICT"}:
        return OperationsExitCode.CONFLICT
    if "PERSISTENCE" in status:
        return OperationsExitCode.PERSISTENCE_FAILURE
    if status.startswith("REJECTED_"):
        return OperationsExitCode.PROVENANCE_OR_CANDIDATE_REJECTION
    if any(fragment in status for fragment in ("PUBLICATION", "ORCHESTRATION", "SEND", "TERMINAL_FAILURE")):
        return OperationsExitCode.PUBLICATION_FAILURE
    return OperationsExitCode.INTERNAL_FAILURE
