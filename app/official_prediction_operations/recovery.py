"""Read-only recovery classification for immutable pipeline history."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.database import Database
from app.official_prediction_pipeline import SQLiteOfficialPredictionPipelineRepository


class RecoveryClassification(str, Enum):
    TERMINAL_SUCCESS = "TERMINAL_SUCCESS"
    TERMINAL_NO_PUBLICATION = "TERMINAL_NO_PUBLICATION"
    RETRYABLE_BEFORE_CLAIM = "RETRYABLE_BEFORE_CLAIM"
    RETRYABLE_SEND_FAILURE = "RETRYABLE_SEND_FAILURE"
    ACTIVE_CLAIM = "ACTIVE_CLAIM"
    INDETERMINATE_POST_SEND = "INDETERMINATE_POST_SEND"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"
    CONFLICTED = "CONFLICTED"
    INVALID_HISTORY = "INVALID_HISTORY"


@dataclass(frozen=True, slots=True)
class RecoveryAnalysis:
    classification: RecoveryClassification
    execution_id: str
    last_completed_stage: str | None
    missing_expected_stage: str | None
    retry_safe: bool
    resend_forbidden: bool
    required_operator_action: str
    candidate_id: str | None
    gate_evaluation_id: str | None
    orchestration_id: str | None
    publication_event_id: str | None
    reason_codes: tuple[str, ...]


def analyze_execution_recovery(database: Database, execution_id: str) -> RecoveryAnalysis:
    before = database.connection.total_changes
    try:
        stored = SQLiteOfficialPredictionPipelineRepository(database, migrate=False).load_execution_with_stages(execution_id)
    except Exception:
        stored = None
    if stored is None:
        return _analysis(RecoveryClassification.INVALID_HISTORY, execution_id, None, None, False, True, "Locate the correct immutable execution ID; do not retry.")
    execution = stored.execution
    stages = stored.stages
    last = stages[-1].stage_name.value if stages else None
    status = execution.final_status.value
    latest_event = None
    if execution.candidate_id:
        candidate = database.connection.execute("SELECT prediction_id FROM official_prediction_candidate_versions WHERE registry_candidate_id=?", (execution.candidate_id,)).fetchone()
        if candidate:
            latest_event = database.connection.execute(
                "SELECT * FROM official_prediction_publication_events WHERE prediction_id=? ORDER BY attempt_number DESC,event_sequence DESC LIMIT 1",
                (candidate[0],),
            ).fetchone()
    event_status = latest_event["status"] if latest_event else None
    failure = latest_event["failure_reason"] if latest_event else None
    if status in {"PUBLISHED", "IDEMPOTENT_EXISTING"}:
        classification = RecoveryClassification.TERMINAL_SUCCESS
        retry_safe, forbidden, action = False, True, "Collect audit evidence; no retry is permitted."
    elif status in {"NO_PUBLICATION_QUALITY_GATE_REJECTED", "NO_PUBLICATION_REVIEW_REQUIRED"}:
        classification = RecoveryClassification.TERMINAL_NO_PUBLICATION
        retry_safe, forbidden, action = False, True, "Resolve the gate decision through normal review; do not resend."
    elif status == "PUBLICATION_IN_PROGRESS" or event_status == "CLAIMED":
        classification = RecoveryClassification.ACTIVE_CLAIM
        retry_safe, forbidden, action = False, True, "Wait and investigate the active claim; never create a second send."
    elif event_status == "INDETERMINATE" or execution.publication_state_result == "INDETERMINATE":
        classification = RecoveryClassification.INDETERMINATE_POST_SEND
        retry_safe, forbidden, action = False, True, "Obtain external delivery evidence; automatic resend is forbidden."
    elif event_status == "FAILED" and failure == "TELEGRAM_CONFIRMED_FAILED":
        classification = RecoveryClassification.RETRYABLE_SEND_FAILURE
        retry_safe, forbidden, action = True, False, "Use retry-execution with the exact confirmation token after destination verification."
    elif status == "RETRY_REQUIRED":
        classification = RecoveryClassification.RETRYABLE_BEFORE_CLAIM
        retry_safe, forbidden, action = True, False, "Verify the failure occurred before send, then use explicit retry."
    elif status in {"CONFLICT", "ALREADY_PUBLISHED_CONFLICT"}:
        classification = RecoveryClassification.CONFLICTED
        retry_safe, forbidden, action = False, True, "Reconcile conflicting immutable identities; do not retry."
    elif not stages:
        classification = RecoveryClassification.INVALID_HISTORY
        retry_safe, forbidden, action = False, True, "Preserve the database and run diagnostics before any action."
    else:
        classification = RecoveryClassification.TERMINAL_FAILURE
        retry_safe, forbidden, action = False, True, "Investigate and correct upstream state; this execution is not retryable."
    if database.connection.total_changes != before:
        raise AssertionError("Recovery analysis changed database state.")
    expected = _next_stage(last, classification)
    return RecoveryAnalysis(
        classification, execution_id, last, expected, retry_safe, forbidden, action,
        execution.candidate_id, execution.quality_gate_evaluation_id,
        execution.orchestration_id,
        latest_event["event_id"] if latest_event else execution.publication_event_id,
        execution.ordered_reason_codes,
    )


def _analysis(classification: RecoveryClassification, execution_id: str, last: str | None, missing: str | None, retry: bool, forbidden: bool, action: str) -> RecoveryAnalysis:
    return RecoveryAnalysis(classification, execution_id, last, missing, retry, forbidden, action, None, None, None, None, ("EXECUTION_NOT_FOUND",))


def _next_stage(last: str | None, classification: RecoveryClassification) -> str | None:
    if classification in {RecoveryClassification.TERMINAL_SUCCESS, RecoveryClassification.TERMINAL_NO_PUBLICATION}:
        return None
    order = ("REQUEST_VALIDATION", "CANDIDATE_STATE_VERIFICATION", "PUBLICATION_STATE_VERIFICATION", "QUALITY_GATE", "ORCHESTRATION", "MESSAGE_ASSEMBLY", "PUBLICATION_CLAIM", "TELEGRAM_SEND", "PUBLICATION_FINALIZATION")
    if last not in order:
        return order[0]
    index = order.index(last) + 1
    return order[index] if index < len(order) else None
