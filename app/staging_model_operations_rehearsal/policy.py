"""Fail-closed staging authorization and path policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ArtifactMode, StagingRehearsalCommand


class StagingRehearsalPolicyError(ValueError):
    """Typed staging authorization or path failure."""


@dataclass(frozen=True, slots=True)
class StagingRehearsalPolicy:
    version: str = "controlled-staging-model-operations-rehearsal-v1"
    required_environment: str = "STAGING"
    required_scope: str = "OFFICIAL_GLOBAL"
    minimum_schema_version: int = 7
    current_schema_version: int = 34
    allow_preflight_warnings: bool = False
    approved_destination_roots: tuple[Path, ...] = ()

    def roots(self, project_root: Path) -> tuple[Path, ...]:
        return self.approved_destination_roots or (
            (project_root / "var" / "staging_rehearsal").resolve(),
        )


DEFAULT_STAGING_REHEARSAL_POLICY = StagingRehearsalPolicy()


def validate_command(
    command: StagingRehearsalCommand,
    policy: StagingRehearsalPolicy,
    project_root: Path,
) -> tuple[Path, Path]:
    if not isinstance(command, StagingRehearsalCommand):
        raise StagingRehearsalPolicyError(
            "A typed StagingRehearsalCommand is required."
        )
    if command.environment != policy.required_environment:
        raise StagingRehearsalPolicyError(
            "Only the explicitly authorized STAGING environment is allowed."
        )
    if command.scope != policy.required_scope:
        raise StagingRehearsalPolicyError("The explicit supported scope is required.")
    if not re.fullmatch(r"\d{8}T\d{6}Z", command.timestamp):
        raise StagingRehearsalPolicyError(
            "Timestamp must use compact UTC YYYYMMDDTHHMMSSZ."
        )
    if not re.fullmatch(r"[0-9a-f]{40}", command.source_commit):
        raise StagingRehearsalPolicyError("A full lowercase source commit is required.")
    if command.audit_output_mode not in {"human", "json", "both"}:
        raise StagingRehearsalPolicyError("Unsupported explicit audit output mode.")
    if not isinstance(command.artifact_mode, ArtifactMode):
        raise StagingRehearsalPolicyError("Unsupported artifact-selection mode.")
    if command.artifact_mode is not ArtifactMode.REAL_ONLY:
        raise StagingRehearsalPolicyError(
            "The controlled staging command requires REAL_ONLY artifacts."
        )
    source = Path(command.source_database).expanduser().resolve()
    destination = Path(command.destination_directory).expanduser().resolve()
    if not source.is_file() or source.suffix.casefold() != ".db":
        raise StagingRehearsalPolicyError(
            "One explicit existing SQLite source database is required."
        )
    if source == destination or source.parent == destination:
        raise StagingRehearsalPolicyError(
            "Source and staging destination must be distinct."
        )
    if not any(_is_within(destination, root) for root in policy.roots(project_root)):
        raise StagingRehearsalPolicyError(
            "Destination is outside approved ignored staging runtime locations."
        )
    return source, destination


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
