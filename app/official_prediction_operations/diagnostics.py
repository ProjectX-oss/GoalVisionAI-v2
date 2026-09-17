"""Read-only integrity diagnostics for manual Official pipeline evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.database import Database
from app.database.migrations import MIGRATIONS

from .factory import DestinationVerificationPort


REQUIRED_TABLES = frozenset({
    "match_data_snapshot_versions", "match_feature_sets", "model_input_vectors",
    "prediction_inference_results", "calibrated_market_probability_assemblies",
    "market_value_assessments", "official_prediction_selection_decisions",
    "official_candidate_preparation_executions", "official_prediction_candidate_versions",
    "official_prediction_candidate_lifecycle_events", "official_quality_gate_evaluations",
    "official_prediction_orchestrations", "official_prediction_publication_events",
    "official_prediction_pipeline_executions", "official_prediction_pipeline_stage_events",
})
_PROVENANCE_KEYS = frozenset({
    "selection_decision_id", "selected_value_assessment_id", "model_input_id", "inference_id",
    "calibrated_assembly_id", "calibration_set_id", "odds_record_id", "bookmaker_id",
    "odds_fingerprint", "calibrated_assembly_fingerprint", "selection_fingerprint",
    "assessment_fingerprint", "risk_fingerprint", "preparation_request_fingerprint",
    "bankroll_snapshot_identity", "exposure_snapshot_identity",
})


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    passed: bool
    status: str
    evidence: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class OfficialPipelineDiagnostics:
    healthy: bool
    checks: tuple[DiagnosticCheck, ...]
    execution_id: str | None = None
    candidate_id: str | None = None

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)


def run_official_pipeline_diagnostics(
    database: Database,
    *,
    execution_id: str | None = None,
    request_id: str | None = None,
    candidate_id: str | None = None,
    destination_verifier: DestinationVerificationPort | None = None,
) -> OfficialPipelineDiagnostics:
    """Inspect schema and linkage without migrations, claims, updates, or sends."""

    before = database.connection.total_changes
    connection = database.connection
    checks: list[DiagnosticCheck] = []
    objects = connection.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','trigger')").fetchall()
    tables = {row["name"] for row in objects if row["type"] == "table"}
    triggers = {row["name"] for row in objects if row["type"] == "trigger"}
    latest = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone() if "schema_migrations" in tables else None
    actual_version = latest[0] if latest else None
    checks.append(_check("MIGRATION_LEVEL", actual_version == MIGRATIONS[-1].version, actual_version))
    missing_tables = sorted(REQUIRED_TABLES - tables)
    checks.append(_check("REQUIRED_TABLES", not missing_tables, ",".join(missing_tables) or "complete"))
    append_triggers = tuple(sorted(name for name in triggers if name.endswith(("_no_update", "_no_delete"))))
    pipeline_guards = {
        "official_pipeline_executions_no_update", "official_pipeline_executions_no_delete",
        "official_pipeline_stage_events_no_update", "official_pipeline_stage_events_no_delete",
        "official_prediction_publication_no_update", "official_prediction_publication_no_delete",
    }
    checks.append(_check("APPEND_ONLY_TRIGGERS", pipeline_guards <= set(append_triggers), str(len(append_triggers))))

    execution = None
    if execution_id and "official_prediction_pipeline_executions" in tables:
        execution = connection.execute("SELECT * FROM official_prediction_pipeline_executions WHERE pipeline_execution_id=?", (execution_id,)).fetchone()
    elif request_id and "official_prediction_pipeline_executions" in tables:
        rows = connection.execute("SELECT * FROM official_prediction_pipeline_executions WHERE pipeline_request_identity=?", (request_id,)).fetchall()
        checks.append(_check("REQUEST_IDENTITY_CONFLICT", len(rows) <= 1, len(rows)))
        execution = rows[0] if rows else None
    if execution_id or request_id:
        checks.append(_check("EXECUTION_EXISTS", execution is not None, "found" if execution else "missing"))
    if execution is not None:
        execution_id = execution["pipeline_execution_id"]
        candidate_id = candidate_id or execution["candidate_id"]
        stages = connection.execute(
            "SELECT stage_order,stage_name,stage_status FROM official_prediction_pipeline_stage_events WHERE pipeline_execution_id=? ORDER BY stage_order",
            (execution_id,),
        ).fetchall()
        orders = tuple(row["stage_order"] for row in stages)
        complete_order = orders == tuple(range(1, len(orders) + 1)) and len(orders) == len(set(orders))
        expected_terminal = {
            "DRY_RUN_COMPLETED": "MESSAGE_ASSEMBLY",
            "PUBLISHED": "PUBLICATION_FINALIZATION",
            "IDEMPOTENT_EXISTING": "PUBLICATION_STATE_VERIFICATION",
            "NO_PUBLICATION_QUALITY_GATE_REJECTED": "QUALITY_GATE",
            "NO_PUBLICATION_REVIEW_REQUIRED": "QUALITY_GATE",
            "REJECTED_CANDIDATE_STATE": "CANDIDATE_STATE_VERIFICATION",
            "PUBLICATION_IN_PROGRESS": "PUBLICATION_STATE_VERIFICATION",
            "RETRY_REQUIRED": "PUBLICATION_STATE_VERIFICATION",
        }.get(execution["final_pipeline_status"])
        last_stage = stages[-1]["stage_name"] if stages else None
        stage_complete = bool(stages) and complete_order and (expected_terminal is None or last_stage == expected_terminal)
        checks.append(_check("STAGE_EVENT_COMPLETENESS", stage_complete, f"count={len(stages)},last={last_stage},expected={expected_terminal}"))
        if execution["quality_gate_evaluation_id"]:
            gate = connection.execute("SELECT 1 FROM official_quality_gate_evaluations WHERE evaluation_id=?", (execution["quality_gate_evaluation_id"],)).fetchone()
            checks.append(_check("GATE_EVALUATION_LINKAGE", gate is not None, execution["quality_gate_evaluation_id"]))
        if execution["orchestration_id"]:
            orchestration = connection.execute("SELECT 1 FROM official_prediction_orchestrations WHERE orchestration_id=?", (execution["orchestration_id"],)).fetchone()
            checks.append(_check("ORCHESTRATION_LINKAGE", orchestration is not None, execution["orchestration_id"]))
        duplicate = connection.execute(
            "SELECT COUNT(*) FROM official_prediction_pipeline_executions WHERE pipeline_fingerprint=?",
            (execution["pipeline_fingerprint"],),
        ).fetchone()[0]
        checks.append(_check("DUPLICATE_PIPELINE_FINGERPRINT", duplicate <= 1, duplicate))

    if candidate_id and "official_prediction_candidate_versions" not in tables:
        checks.append(_check("CANDIDATE_EXISTS", False, "candidate table missing"))
    elif candidate_id:
        candidate = connection.execute("SELECT * FROM official_prediction_candidate_versions WHERE registry_candidate_id=?", (candidate_id,)).fetchone()
        checks.append(_check("CANDIDATE_EXISTS", candidate is not None, candidate_id))
        if candidate is not None:
            import json
            provenance = dict(json.loads(candidate["provenance_snapshot"]))
            missing = sorted(_PROVENANCE_KEYS - set(provenance))
            checks.append(_check("CANDIDATE_PROVENANCE", not missing, ",".join(missing) or "complete"))
            lifecycle = connection.execute(
                "SELECT event_type FROM official_prediction_candidate_lifecycle_events WHERE registry_candidate_id=? ORDER BY event_sequence DESC LIMIT 1",
                (candidate_id,),
            ).fetchone()
            state = lifecycle[0] if lifecycle else "MISSING"
            checks.append(_check("CANDIDATE_LIFECYCLE", state == "READY", state))
            prediction_id = candidate["prediction_id"]
            events = connection.execute(
                "SELECT status,failure_reason,attempt_reference FROM official_prediction_publication_events WHERE prediction_id=? ORDER BY attempt_number DESC,event_sequence DESC LIMIT 1",
                (prediction_id,),
            ).fetchone()
            publication_state = events["status"] if events else "NEVER_ATTEMPTED"
            checks.append(_check("PUBLICATION_CLAIM_STATE", publication_state not in {"CLAIMED"}, publication_state))
            checks.append(_check("PUBLICATION_TERMINAL_STATE", publication_state in {"NEVER_ATTEMPTED","PUBLISHED","FAILED","INDETERMINATE"}, publication_state))

    if destination_verifier is not None:
        verification = destination_verifier.verify()
        checks.append(_check("DESTINATION_VERIFICATION", verification.state.value == "VERIFIED" and verification.enabled, verification.state.value))
    if database.connection.total_changes != before:
        raise AssertionError("Read-only diagnostics changed database state.")
    return OfficialPipelineDiagnostics(
        healthy=all(check.passed for check in checks), checks=tuple(checks),
        execution_id=execution_id, candidate_id=candidate_id,
    )


def _check(name: str, passed: bool, evidence: Any) -> DiagnosticCheck:
    return DiagnosticCheck(name, passed, "PASS" if passed else "FAIL", (("evidence", str(evidence)),))
