"""Controlled staging orchestration over existing audited public boundaries."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

from app.model_operations_rehearsal.execution import (
    ExecutionRehearsalProfile,
    execute_activation_rollback_rehearsal,
    verify_atomic_failure_recovery,
)
from app.model_operations_rehearsal.safety import sha256_file
from app.database import Database
from app.staging_real_artifact_chain import build_real_artifact_chain

from .models import (
    ArtifactCandidate,
    ArtifactInventory,
    AuditCapture,
    EVIDENCE_SCHEMA_VERSION,
    InitialStagingState,
    SourceDatabaseEvidence,
    STAGING_SOURCE_LABEL,
    StagingRehearsalCommand,
    StagingRehearsalOutcome,
)
from .policy import (
    DEFAULT_STAGING_REHEARSAL_POLICY,
    StagingRehearsalPolicy,
    StagingRehearsalPolicyError,
    validate_command,
)
from .reporting import canonical_json, evidence_fingerprint


class StagingRehearsalError(RuntimeError):
    """Fail-closed staging rehearsal failure."""


class AuditCliRunner:
    def __init__(self, source_commit: str, generated_at: str):
        self.source_commit = source_commit
        self.generated_at = generated_at
        self.captures: list[AuditCapture] = []

    def require_preflight(self, path: Path, phase: str) -> None:
        self._run(path, phase, "preflight", "human")
        capture = self._run(path, phase, "preflight", "json")
        _require_audit(capture, allow_info=True)

    def require_final(self, path: Path) -> None:
        self._run(path, "FINAL", "audit", "human")
        capture = self._run(path, "FINAL", "audit", "json")
        _require_audit(capture, allow_info=False)

    def _run(self, path, phase, command, output):
        completed = subprocess.run(
            (
                sys.executable,
                "-m",
                "app.model_activation_audit.cli",
                command,
                "--database",
                str(path.resolve()),
                "--environment",
                "STAGING",
                "--scope",
                "OFFICIAL_GLOBAL",
                "--source-commit",
                self.source_commit,
                "--generated-at",
                self.generated_at,
                "--output",
                output,
            ),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0 or completed.stderr.strip():
            raise StagingRehearsalError(
                f"{phase} {command} {output} audit failed closed."
            )
        if output == "json":
            document = json.loads(completed.stdout)
            capture = AuditCapture(
                phase,
                output,
                completed.returncode,
                document["overall_status"],
                document["staging_readiness"],
                document["audit_fingerprint"],
                tuple(sorted(document["summary_counts"].items())),
            )
        else:
            capture = AuditCapture(
                phase,
                output,
                completed.returncode,
                _line(completed.stdout, "Status"),
                _line(completed.stdout, "Staging readiness"),
                _line(completed.stdout, "Audit fingerprint"),
                (),
            )
        self.captures.append(capture)
        return capture


def run_staging_rehearsal(
    command: StagingRehearsalCommand,
    *,
    policy: StagingRehearsalPolicy = DEFAULT_STAGING_REHEARSAL_POLICY,
    project_root: Path | None = None,
) -> StagingRehearsalOutcome:
    root = project_root or Path(__file__).resolve().parents[2]
    source, destination = validate_command(command, policy, root)
    _verify_ignored_destination(destination, root)
    before = sha256_file(source)
    source_size = source.stat().st_size
    source_schema, source_fk = _source_integrity(source, policy)
    if destination.exists():
        raise StagingRehearsalError("Staging destination must be new.")
    destination.mkdir(parents=True)
    external_backup = destination / f"source_backup_{command.timestamp}.db"
    shutil.copy2(source, external_backup)
    if sha256_file(external_backup) != before:
        raise StagingRehearsalError("External source backup fingerprint differs.")
    controlled_source = (
        destination / f"controlled_real_artifact_source_{command.timestamp}.db"
    )
    chain_database = Database(controlled_source)
    try:
        chain = build_real_artifact_chain(chain_database)
        challenger_estimator_fingerprint = chain_database.connection.execute(
            """SELECT estimator_bundle_fingerprint
               FROM historical_model_artifacts
               WHERE artifact_id=?""",
            (chain.challenger.model_artifact_id,),
        ).fetchone()[0]
    finally:
        chain_database.close()
    candidate = ArtifactCandidate(
        model_artifact_id=chain.challenger.model_artifact_id,
        model_artifact_fingerprint=chain.challenger.model_artifact_fingerprint,
        training_run_id=chain.challenger_training_run_id,
        preprocessing_fingerprint=chain.challenger.preprocessing_fingerprint,
        estimator_fingerprint=challenger_estimator_fingerprint,
        calibration_artifact_set_id=chain.challenger.calibration_artifact_set_id,
        calibration_artifact_set_fingerprint=(
            chain.challenger.calibration_artifact_set_fingerprint
        ),
        backtest_run_id=chain.challenger_backtest_run_id,
        comparison_run_id=chain.comparison_run_id,
        recommendation_id=chain.recommendation_id,
        settled_shadow_count=chain.settled_shadow_count,
        feature_schema_version=chain.challenger.feature_schema_version,
        probability_contract_version=chain.challenger.probability_contract_version,
        runtime_compatibility_version=(
            chain.challenger.runtime_compatibility_version
        ),
        complete=True,
        audit_eligible=True,
        rejection_reasons=(),
    )
    inventory = ArtifactInventory(
        candidates=(candidate,),
        selected_candidate_id=candidate.model_artifact_id,
        used_fixture_fallback=False,
        inventory_reason_codes=("CONTROLLED_REAL_ARTIFACT_CHAIN_COMPLETE",),
    )
    audit_runner = AuditCliRunner(
        command.source_commit,
        _compact_to_iso(command.timestamp),
    )
    profile = _staging_profile(command.timestamp)
    report = execute_activation_rollback_rehearsal(
        source_database=controlled_source,
        destination_directory=destination,
        timestamp=command.timestamp,
        profile=profile,
        fixture_seed=lambda database: chain,
        pre_bootstrap_hook=lambda path: audit_runner.require_preflight(
            path, "PRE_BOOTSTRAP"
        ),
        pre_execution_hook=lambda path: audit_runner.require_preflight(
            path, "PRE_EXECUTION"
        ),
        final_hook=audit_runner.require_final,
    )
    foundation = (
        destination
        / f"{profile.foundation_prefix}_{command.timestamp}.db"
    )
    atomicity = verify_atomic_failure_recovery(
        foundation=foundation,
        destination_directory=destination,
        profile=profile,
    )
    after = sha256_file(source)
    if before != after or sha256_file(external_backup) != before:
        raise StagingRehearsalError(
            "Source or byte-identical backup fingerprint verification failed."
        )
    preflight = tuple(
        item for item in audit_runner.captures if item.phase != "FINAL"
    )
    final = tuple(item for item in audit_runner.captures if item.phase == "FINAL")
    statuses = tuple(
        (
            item.name,
            (
                item.parsed_json.get("status")
                if item.parsed_json is not None
                else None
            ),
            item.exit_code,
        )
        for item in report.commands
    )
    manifest = json.loads(
        foundation.with_suffix(".manifest.json").read_text(encoding="utf-8")
    )
    disposable = (
        destination
        / f"{profile.disposable_prefix}_{command.timestamp}.db"
    )
    foundation_content_fingerprint = _sqlite_content_sha256(foundation)
    disposable_content_fingerprint = _sqlite_content_sha256(disposable)
    selected_references = tuple(
        sorted(
            {
                "champion_model_artifact_id": manifest["champion"][
                    "model_artifact_id"
                ],
                "champion_model_artifact_fingerprint": manifest["champion"][
                    "model_artifact_fingerprint"
                ],
                "champion_calibration_artifact_set_id": manifest["champion"][
                    "calibration_artifact_set_id"
                ],
                "challenger_model_artifact_id": manifest["challenger"][
                    "model_artifact_id"
                ],
                "challenger_model_artifact_fingerprint": manifest["challenger"][
                    "model_artifact_fingerprint"
                ],
                "challenger_calibration_artifact_set_id": manifest["challenger"][
                    "calibration_artifact_set_id"
                ],
                "comparison_run_id": manifest["comparison_run_id"],
                "recommendation_id": manifest["recommendation_id"],
                "shadow_evidence_fingerprint": manifest[
                    "shadow_evidence_fingerprint"
                ],
            }.items()
        )
    )
    outcome = StagingRehearsalOutcome(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        status="STAGING_REHEARSAL_COMPLETED",
        source_commit=command.source_commit,
        timestamp=command.timestamp,
        environment=command.environment,
        scope=command.scope,
        source=SourceDatabaseEvidence(
            source.name,
            before,
            after,
            sha256_file(external_backup),
            source_size,
            source_schema,
            source_fk,
        ),
        artifact_inventory=inventory,
        artifact_mode=command.artifact_mode.name,
        fixture_fallback_used=False,
        real_artifact_chain_complete=True,
        real_artifact_chain_fingerprint=chain.chain_fingerprint,
        selected_artifact_mode="REAL_ONLY",
        selected_artifact_references=selected_references,
        initial_state=InitialStagingState.STAGING_UNBOOTSTRAPPED.value,
        preflight_audits=preflight,
        final_audits=final,
        foundation_fingerprint=foundation_content_fingerprint,
        disposable_before_fingerprint=foundation_content_fingerprint,
        disposable_after_fingerprint=disposable_content_fingerprint,
        initial_generation_id=report.initial_generation_id,
        activation_plan_id=report.activation_plan_id,
        activation_plan_fingerprint=report.activation_plan_fingerprint,
        activation_execution_fingerprint=(
            report.activation_execution_fingerprint
        ),
        activated_generation_id=report.activated_generation_id,
        rollback_plan_id=report.rollback_plan_id,
        rollback_plan_fingerprint=report.rollback_plan_fingerprint,
        rollback_execution_fingerprint=report.rollback_execution_fingerprint,
        rollback_generation_id=report.rollback_generation_id,
        resolver_sequence=report.resolver_sequence,
        generation_chain=report.generation_chain,
        registry_event_types=report.registry_event_types,
        final_counts=tuple(sorted(report.final_counts.items())),
        protected_state_unchanged=report.protected_state_unchanged,
        atomicity_checks=atomicity,
        append_only_trigger_count=report.append_only_trigger_count,
        foreign_key_violations=report.foreign_key_violations,
        command_statuses=statuses,
        evidence_fingerprint="",
    )
    outcome = replace(outcome, evidence_fingerprint=evidence_fingerprint(outcome))
    if command.evidence_report_destination:
        _write_new_evidence(command.evidence_report_destination, outcome)
    return outcome


def _staging_profile(timestamp: str) -> ExecutionRehearsalProfile:
    return ExecutionRehearsalProfile(
        environment="staging",
        fixture_label=STAGING_SOURCE_LABEL,
        execution_label=STAGING_SOURCE_LABEL,
        operator=STAGING_SOURCE_LABEL,
        activation_prepare_request_id="staging-rehearsal-activation-prepare-1",
        activation_execution_request_id="staging-rehearsal-activation-execution-1",
        rollback_request_id="staging-rehearsal-rollback-prepare-1",
        rollback_execution_request_id="staging-rehearsal-rollback-execution-1",
        incident_reference="STAGING-REHEARSAL-INCIDENT-001",
        expected_plan_id=None,
        foundation_prefix="goalvision_staging_rehearsal",
        disposable_prefix="goalvision_staging_activation_rollback",
    )


def _source_integrity(path: Path, policy):
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        versions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        if (
            not versions
            or versions != tuple(range(1, max(versions) + 1))
            or max(versions) < policy.minimum_schema_version
            or max(versions) > policy.current_schema_version
        ):
            raise StagingRehearsalPolicyError(
                "Source migration history is unsupported or incomplete."
            )
        violations = len(tuple(connection.execute("PRAGMA foreign_key_check")))
        if violations:
            raise StagingRehearsalPolicyError(
                "Source database has foreign-key violations."
            )
        return max(versions), violations
    finally:
        connection.close()


def _verify_ignored_destination(destination: Path, root: Path):
    ignore = (root / ".gitignore").read_text(encoding="utf-8")
    if "var/staging_rehearsal/" not in ignore.replace("\\", "/"):
        raise StagingRehearsalPolicyError(
            "Approved staging runtime destination is not Git-ignored."
        )


def _require_audit(capture, *, allow_info):
    counts = dict(capture.summary_counts)
    if (
        capture.overall_status != "AUDIT_PASSED"
        or capture.staging_readiness != "STAGING_REHEARSAL_READY"
        or counts.get("BLOCKER", 0)
        or counts.get("WARNING", 0)
        or (not allow_info and counts.get("INFO", 0))
    ):
        raise StagingRehearsalError("Mandatory independent audit gate rejected.")


def _line(output, name):
    prefix = name + ":"
    return next(
        line.split(":", 1)[1].strip()
        for line in output.splitlines()
        if line.startswith(prefix)
    )


def _compact_to_iso(value):
    return (
        f"{value[0:4]}-{value[4:6]}-{value[6:8]}T"
        f"{value[9:11]}:{value[11:13]}:{value[13:15]}Z"
    )


def _write_new_evidence(value, outcome):
    path = Path(value).expanduser().resolve()
    if path.exists() or not path.parent.is_dir() or path.suffix != ".json":
        raise StagingRehearsalPolicyError(
            "Evidence destination must be a new JSON file in an existing directory."
        )
    path.write_text(canonical_json(outcome) + "\n", encoding="utf-8")


def _sqlite_content_sha256(path: Path) -> str:
    """Fingerprint canonical schema and row content, excluding file layout."""
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        objects = tuple(
            tuple(row)
            for row in connection.execute(
                """SELECT type,name,tbl_name,sql
                   FROM sqlite_master
                   WHERE name NOT LIKE 'sqlite_%'
                   ORDER BY type,name"""
            )
        )
        tables = tuple(
            row[0]
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name NOT LIKE 'sqlite_%'
                   ORDER BY name"""
            )
        )
        rows = []
        for table in tables:
            quoted = table.replace('"', '""')
            if table == "schema_migrations":
                # SQLite CURRENT_TIMESTAMP records operational wall-clock
                # time. Migration identity is the ordered version sequence.
                values = tuple(
                    tuple(row)
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )
                )
            else:
                values = tuple(
                    tuple(row)
                    for row in connection.execute(
                        f'SELECT * FROM "{quoted}" ORDER BY rowid'
                    )
                )
            rows.append((table, values))
        material = json.dumps(
            {"objects": objects, "tables": rows},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return sha256(material.encode("utf-8")).hexdigest()
    finally:
        connection.close()
