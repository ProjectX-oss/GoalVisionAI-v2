"""Resolve reviewed source identity for an exact activated artifact chain."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from app.model_activation import (
    ActivationStatus,
    RuntimeArtifactReference,
    build_runtime_champion_resolver,
)


REVIEWED_CHAIN_EVIDENCE = (
    (
        "docs/rehearsals/live_78_recent_calibration_champion_2026-07-31.json",
        "9a5120cc40ab79715cdc757198f6e4d7ae2757119168ab99802454fec420458f",
    ),
)


class ReviewedSourceProvenanceError(ValueError):
    """The active artifact chain has no unique intact reviewed source identity."""


@dataclass(frozen=True, slots=True)
class ReviewedSourceProvenance:
    source_commit: str
    evidence_path: str
    evidence_fingerprint: str
    activation_audit_fingerprint: str


def resolve_active_reviewed_source_provenance(
    database,
    scope: str,
    *,
    project_root: Path | None = None,
) -> ReviewedSourceProvenance:
    """Resolve provenance only after the persisted active champion verifies."""
    resolution = build_runtime_champion_resolver(database, migrate=False).resolve(scope)
    if (
        resolution.status is not ActivationStatus.CHAMPION_RESOLVED
        or resolution.champion_generation is None
    ):
        raise ReviewedSourceProvenanceError(
            "The active champion cannot be resolved for source review."
        )
    return resolve_reviewed_source_provenance(
        resolution.champion_generation.artifact,
        scope,
        project_root=project_root,
    )


def resolve_reviewed_source_provenance(
    artifact: RuntimeArtifactReference,
    scope: str,
    *,
    project_root: Path | None = None,
) -> ReviewedSourceProvenance:
    """Bind an exact artifact pair to its immutable reviewed audit evidence."""
    root = project_root or Path(__file__).resolve().parents[2]
    matches: list[ReviewedSourceProvenance] = []
    for relative_path, expected_fingerprint in REVIEWED_CHAIN_EVIDENCE:
        path = root / relative_path
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _evidence_is_intact(document, expected_fingerprint):
            continue
        source_commit = document.get("source_commit")
        audit = document.get("activation_audit")
        if (
            not isinstance(source_commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
            or not isinstance(audit, dict)
            or audit.get("status") != "AUDIT_PASSED"
            or not isinstance(audit.get("fingerprint"), str)
            or document.get("comparison", {}).get("recommendation")
            != "PROMOTE_CHALLENGER"
            or not _candidate_matches(document, artifact)
            or not _successful_activation_matches(document, artifact, scope)
        ):
            continue
        matches.append(
            ReviewedSourceProvenance(
                source_commit,
                relative_path,
                expected_fingerprint,
                audit["fingerprint"],
            )
        )
    commits = {item.source_commit for item in matches}
    if len(matches) != 1 or len(commits) != 1:
        raise ReviewedSourceProvenanceError(
            "The active artifact chain has no unique intact reviewed source commit."
        )
    return matches[0]


def _evidence_is_intact(document: dict, expected_fingerprint: str) -> bool:
    if (
        document.get("schema_version")
        != "goalvision-live-78-recent-calibration-evidence-v1"
        or document.get("evidence_fingerprint") != expected_fingerprint
    ):
        return False
    material = {**document, "evidence_fingerprint": ""}
    actual = hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return actual == expected_fingerprint


def _candidate_matches(document: dict, artifact: RuntimeArtifactReference) -> bool:
    expected = {
        "model_artifact_id": artifact.model_artifact_id,
        "model_fingerprint": artifact.model_artifact_fingerprint,
        "calibration_id": artifact.calibration_artifact_set_id,
        "calibration_fingerprint": artifact.calibration_artifact_set_fingerprint,
    }
    return sum(
        isinstance(candidate, dict)
        and all(candidate.get(key) == value for key, value in expected.items())
        for candidate in document.get("candidates", ())
    ) == 1


def _successful_activation_matches(
    document: dict, artifact: RuntimeArtifactReference, scope: str
) -> bool:
    expected = {
        "model_scope": scope,
        "model_artifact_id": artifact.model_artifact_id,
        "model_artifact_fingerprint": artifact.model_artifact_fingerprint,
        "preprocessing_fingerprint": artifact.preprocessing_fingerprint,
        "calibration_artifact_set_id": artifact.calibration_artifact_set_id,
        "calibration_artifact_set_fingerprint": (
            artifact.calibration_artifact_set_fingerprint
        ),
        "feature_schema_version": artifact.feature_schema_version,
        "feature_schema_fingerprint": artifact.feature_schema_fingerprint,
        "target_contract_version": artifact.target_contract_version,
        "probability_contract_version": artifact.probability_contract_version,
        "runtime_compatibility_version": artifact.runtime_compatibility_version,
    }
    matches = 0
    for command in document.get("staging_operations", {}).get("commands", ()):
        parsed = command.get("parsed_json") if isinstance(command, dict) else None
        if not isinstance(parsed, dict):
            continue
        generation = parsed.get("details", {}).get("new_champion_generation")
        if (
            command.get("exit_code") == 0
            and parsed.get("success") is True
            and parsed.get("status") == "ACTIVATION_EXECUTED"
            and isinstance(generation, dict)
            and all(generation.get(key) == value for key, value in expected.items())
        ):
            matches += 1
    return matches == 1
