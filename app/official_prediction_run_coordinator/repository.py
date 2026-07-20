import json
import sqlite3
from datetime import datetime

from app.database import Database, MigrationManager

from .exceptions import OfficialPredictionRunPersistenceError
from .models import (
    CandidateDiscoveryStatus,
    CandidateHistoricalState,
    OfficialPredictionCandidateReference,
    OfficialPredictionRunClaim,
    OfficialPredictionRunItemResult,
    OfficialPredictionRunItemStatus,
    OfficialPredictionRunRequest,
    OfficialPredictionRunResult,
    OfficialPredictionRunStart,
    OfficialPredictionRunStatus,
)


class SQLiteOfficialCandidateHistoricalStateReader:
    """Classifies immutable candidate references using durable local history."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def get(
        self,
        candidate: OfficialPredictionCandidateReference,
        evaluated_at: datetime,
    ) -> CandidateHistoricalState:
        published = self._connection.execute(
            "SELECT 1 FROM published_predictions WHERE prediction_id = ?",
            (candidate.prediction_id,),
        ).fetchone()
        if published is not None:
            return CandidateHistoricalState(
                CandidateDiscoveryStatus.ALREADY_PUBLISHED
            )
        events = self._connection.execute(
            """
            SELECT status, attempt_number, occurred_at
            FROM official_prediction_publication_events
            WHERE prediction_id = ? AND destination_scope = 'OFFICIAL'
            ORDER BY attempt_number DESC, event_sequence DESC, event_id DESC
            """,
            (candidate.prediction_id,),
        ).fetchall()
        if events:
            latest = events[0]
            status = {
                "CLAIMED": CandidateDiscoveryStatus.ACTIVE_DUPLICATE_CLAIM,
                "PUBLISHED": CandidateDiscoveryStatus.ALREADY_PUBLISHED,
                "FAILED": CandidateDiscoveryStatus.RETRYABLE_CONFIRMED_FAILURE,
                "INDETERMINATE": CandidateDiscoveryStatus.INDETERMINATE,
            }[latest["status"]]
            return CandidateHistoricalState(
                status=status,
                attempt_count=max(row["attempt_number"] for row in events),
                last_attempt_timestamp=datetime.fromisoformat(latest["occurred_at"]),
            )
        coordinated = self._connection.execute(
            """
            SELECT item_status, candidate_fingerprint
            FROM official_prediction_run_items
            WHERE prediction_id = ?
              AND candidate_fingerprint = ?
              AND item_status IN ('REJECTED', 'REVIEW_REQUIRED')
            ORDER BY completed_timestamp DESC, run_item_id DESC
            LIMIT 1
            """,
            (candidate.prediction_id, candidate.immutable_fingerprint),
        ).fetchone()
        immutable = _immutable_state(coordinated, candidate.immutable_fingerprint)
        if immutable is not None:
            return immutable
        orchestrated = self._connection.execute(
            """
            SELECT final_status, candidate_fingerprint
            FROM official_prediction_orchestrations
            WHERE prediction_id = ?
              AND candidate_fingerprint = ?
              AND final_status IN ('REJECTED', 'REVIEW_REQUIRED')
            ORDER BY created_timestamp DESC, orchestration_id DESC
            LIMIT 1
            """,
            (candidate.prediction_id, candidate.immutable_fingerprint),
        ).fetchone()
        immutable = _immutable_state(orchestrated, candidate.immutable_fingerprint)
        if immutable is not None:
            return immutable
        return CandidateHistoricalState(CandidateDiscoveryStatus.READY)


class SQLiteOfficialPredictionRunRepository:
    """Append-only run start, ordered item, and terminal summary persistence."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def begin_run(self, start: OfficialPredictionRunStart) -> OfficialPredictionRunClaim:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._start_row_for_fingerprint(start.run_fingerprint)
            if row is not None:
                self._connection.commit()
                existing_start = _start_from_row(row)
                if existing_start != start:
                    raise OfficialPredictionRunPersistenceError(
                        "Run fingerprint conflicts with different start material."
                    )
                result = self.load_complete_run(existing_start.run_id)
                return OfficialPredictionRunClaim(
                    acquired=False,
                    start=existing_start,
                    existing_result=result,
                    incomplete=result is None,
                )
            self._connection.execute(
                """
                INSERT INTO official_prediction_runs (
                    run_event_id, run_id, event_sequence, run_fingerprint,
                    idempotency_key, run_status, policy_version, dry_run,
                    bankroll_scope, destination_scope, started_timestamp,
                    completed_timestamp, discovered_count, eligible_count,
                    processed_count, published_count,
                    approved_not_published_count, rejected_count,
                    review_required_count, duplicate_blocked_count,
                    retryable_failure_count, indeterminate_failure_count,
                    assembly_failure_count, skipped_count,
                    internal_failure_count, ordered_reasons, stop_reason,
                    request_snapshot, summary_snapshot
                ) VALUES (?, ?, 1, ?, ?, NULL, ?, ?, ?, ?, ?, NULL,
                    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                    NULL, NULL, NULL, NULL, NULL, '[]', NULL, ?, NULL)
                """,
                (
                    f"{start.run_id}:START",
                    start.run_id,
                    start.run_fingerprint,
                    start.request.idempotency_key,
                    start.policy_version,
                    int(start.request.dry_run),
                    start.bankroll_scope.value,
                    start.destination_scope.value,
                    start.request.evaluation_timestamp.isoformat(),
                    _start_json(start),
                ),
            )
            self._connection.commit()
        except OfficialPredictionRunPersistenceError:
            self._connection.rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._connection.rollback()
            raise OfficialPredictionRunPersistenceError(
                "Official prediction run could not be started."
            ) from exc
        return OfficialPredictionRunClaim(True, start)

    def append_item(
        self,
        item: OfficialPredictionRunItemResult,
    ) -> OfficialPredictionRunItemResult:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            if not self._active_start_exists(item.run_id):
                raise OfficialPredictionRunPersistenceError(
                    "Run start is missing or already terminal."
                )
            count = self._connection.execute(
                "SELECT COUNT(*) FROM official_prediction_run_items WHERE run_id = ?",
                (item.run_id,),
            ).fetchone()[0]
            if count != item.item_index:
                raise OfficialPredictionRunPersistenceError(
                    "Run items must be appended in contiguous order."
                )
            self._connection.execute(
                """
                INSERT INTO official_prediction_run_items (
                    run_item_id, run_id, run_event_sequence, item_index,
                    prediction_id, match_id, candidate_fingerprint,
                    kickoff_timestamp, discovery_status, item_status,
                    was_eligible, orchestration_id,
                    publication_attempt_reference, started_timestamp,
                    completed_timestamp, ordered_reasons, result_snapshot
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{item.run_id}:ITEM:{item.item_index:04d}",
                    item.run_id,
                    item.item_index,
                    item.prediction_id,
                    item.match_id,
                    item.candidate_fingerprint,
                    item.kickoff_timestamp.isoformat(),
                    item.discovery_status.value,
                    item.status.value,
                    int(item.was_eligible),
                    item.orchestration_id,
                    item.publication_attempt_reference,
                    item.started_timestamp.isoformat(),
                    item.completed_timestamp.isoformat(),
                    _json(list(item.ordered_reason_codes)),
                    _item_json(item),
                ),
            )
            self._connection.commit()
        except OfficialPredictionRunPersistenceError:
            self._connection.rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._connection.rollback()
            raise OfficialPredictionRunPersistenceError(
                "Official prediction run item could not be appended."
            ) from exc
        stored = self._item(item.run_id, item.item_index)
        if stored != item:
            raise OfficialPredictionRunPersistenceError(
                "Stored run item conflicts with its immutable input."
            )
        return stored

    def finalize_run(
        self,
        result: OfficialPredictionRunResult,
    ) -> OfficialPredictionRunResult:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            if not self._active_start_exists(result.run_id):
                raise OfficialPredictionRunPersistenceError(
                    "Run cannot be terminally finalized more than once."
                )
            stored_items = self._items(result.run_id)
            if stored_items != result.ordered_items:
                raise OfficialPredictionRunPersistenceError(
                    "Terminal run items do not match append-only history."
                )
            start = self._connection.execute(
                """
                SELECT * FROM official_prediction_runs
                WHERE run_id = ? AND event_sequence = 1
                """,
                (result.run_id,),
            ).fetchone()
            if start is None or start["run_fingerprint"] != result.run_fingerprint:
                raise OfficialPredictionRunPersistenceError(
                    "Terminal run fingerprint does not match its start event."
                )
            counts = _result_counts(result)
            self._connection.execute(
                """
                INSERT INTO official_prediction_runs (
                    run_event_id, run_id, event_sequence, run_fingerprint,
                    idempotency_key, run_status, policy_version, dry_run,
                    bankroll_scope, destination_scope, started_timestamp,
                    completed_timestamp, discovered_count, eligible_count,
                    processed_count, published_count,
                    approved_not_published_count, rejected_count,
                    review_required_count, duplicate_blocked_count,
                    retryable_failure_count, indeterminate_failure_count,
                    assembly_failure_count, skipped_count,
                    internal_failure_count, ordered_reasons, stop_reason,
                    request_snapshot, summary_snapshot
                ) VALUES (?, ?, 2, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{result.run_id}:TERMINAL",
                    result.run_id,
                    result.run_fingerprint,
                    start["idempotency_key"],
                    result.run_status.value,
                    result.policy_version,
                    int(result.dry_run),
                    start["bankroll_scope"],
                    start["destination_scope"],
                    result.started_timestamp.isoformat(),
                    result.completed_timestamp.isoformat(),
                    *counts,
                    _json(list(result.ordered_internal_reasons)),
                    result.stop_reason,
                    start["request_snapshot"],
                    _result_json(result),
                ),
            )
            self._connection.commit()
        except OfficialPredictionRunPersistenceError:
            self._connection.rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._connection.rollback()
            raise OfficialPredictionRunPersistenceError(
                "Official prediction run could not be finalized."
            ) from exc
        stored = self.load_complete_run(result.run_id)
        if stored != result:
            raise OfficialPredictionRunPersistenceError(
                "Stored terminal run conflicts with its immutable result."
            )
        return stored

    def load_by_fingerprint(
        self,
        run_fingerprint: str,
    ) -> OfficialPredictionRunClaim | None:
        row = self._start_row_for_fingerprint(run_fingerprint)
        if row is None:
            return None
        start = _start_from_row(row)
        result = self.load_complete_run(start.run_id)
        return OfficialPredictionRunClaim(
            acquired=False,
            start=start,
            existing_result=result,
            incomplete=result is None,
        )

    def load_complete_run(self, run_id: str) -> OfficialPredictionRunResult | None:
        terminal = self._connection.execute(
            """
            SELECT * FROM official_prediction_runs
            WHERE run_id = ? AND event_sequence = 2
            """,
            (run_id,),
        ).fetchone()
        if terminal is None:
            return None
        items = self._items(run_id)
        return OfficialPredictionRunResult(
            run_id=run_id,
            run_fingerprint=terminal["run_fingerprint"],
            started_timestamp=datetime.fromisoformat(terminal["started_timestamp"]),
            completed_timestamp=datetime.fromisoformat(
                terminal["completed_timestamp"]
            ),
            run_status=OfficialPredictionRunStatus(terminal["run_status"]),
            policy_version=terminal["policy_version"],
            dry_run=bool(terminal["dry_run"]),
            discovered_count=terminal["discovered_count"],
            eligible_count=terminal["eligible_count"],
            processed_count=terminal["processed_count"],
            published_count=terminal["published_count"],
            approved_not_published_count=terminal[
                "approved_not_published_count"
            ],
            rejected_count=terminal["rejected_count"],
            review_required_count=terminal["review_required_count"],
            duplicate_blocked_count=terminal["duplicate_blocked_count"],
            retryable_failure_count=terminal["retryable_failure_count"],
            indeterminate_failure_count=terminal["indeterminate_failure_count"],
            assembly_failure_count=terminal["assembly_failure_count"],
            skipped_count=terminal["skipped_count"],
            internal_failure_count=terminal["internal_failure_count"],
            ordered_items=items,
            ordered_internal_reasons=tuple(
                json.loads(terminal["ordered_reasons"])
            ),
            stop_reason=terminal["stop_reason"],
        )

    def _start_row_for_fingerprint(self, run_fingerprint: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM official_prediction_runs
            WHERE run_fingerprint = ? AND event_sequence = 1
            """,
            (run_fingerprint,),
        ).fetchone()

    def _active_start_exists(self, run_id: str) -> bool:
        row = self._connection.execute(
            """
            SELECT
                EXISTS(SELECT 1 FROM official_prediction_runs
                    WHERE run_id = ? AND event_sequence = 1),
                EXISTS(SELECT 1 FROM official_prediction_runs
                    WHERE run_id = ? AND event_sequence = 2)
            """,
            (run_id, run_id),
        ).fetchone()
        return bool(row[0]) and not bool(row[1])

    def _items(self, run_id: str) -> tuple[OfficialPredictionRunItemResult, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM official_prediction_run_items
            WHERE run_id = ? ORDER BY item_index
            """,
            (run_id,),
        ).fetchall()
        return tuple(_item_from_row(row) for row in rows)

    def _item(self, run_id: str, item_index: int) -> OfficialPredictionRunItemResult:
        row = self._connection.execute(
            """
            SELECT * FROM official_prediction_run_items
            WHERE run_id = ? AND item_index = ?
            """,
            (run_id, item_index),
        ).fetchone()
        if row is None:
            raise OfficialPredictionRunPersistenceError("Stored run item is missing.")
        return _item_from_row(row)


def _immutable_state(
    row: sqlite3.Row | None,
    fingerprint: str,
) -> CandidateHistoricalState | None:
    if row is None or row["candidate_fingerprint"] != fingerprint:
        return None
    value = row["item_status"] if "item_status" in row.keys() else row["final_status"]
    if value == "REJECTED":
        status = CandidateDiscoveryStatus.REJECTED_IMMUTABLE
    elif value == "REVIEW_REQUIRED":
        status = CandidateDiscoveryStatus.REVIEW_REQUIRED_IMMUTABLE
    else:
        return None
    return CandidateHistoricalState(
        status=status,
        unchanged_candidate_fingerprint=fingerprint,
    )


def _start_json(start: OfficialPredictionRunStart) -> str:
    request = start.request
    return _json({
        "run_id": start.run_id,
        "run_fingerprint": start.run_fingerprint,
        "evaluation_timestamp": request.evaluation_timestamp.isoformat(),
        "idempotency_key": request.idempotency_key,
        "dry_run": request.dry_run,
        "force_review": request.force_review,
        "normalized_discovery_filters": [list(item) for item in request.normalized_discovery_filters],
        "policy_version": start.policy_version,
        "bankroll_scope": start.bankroll_scope.value,
        "destination_scope": start.destination_scope.value,
        "request_snapshot": [list(item) for item in start.request_snapshot],
    })


def _start_from_row(row: sqlite3.Row) -> OfficialPredictionRunStart:
    from app.risk_management import RiskProductScope

    value = json.loads(row["request_snapshot"])
    request = OfficialPredictionRunRequest(
        evaluation_timestamp=datetime.fromisoformat(value["evaluation_timestamp"]),
        idempotency_key=value["idempotency_key"],
        dry_run=bool(value["dry_run"]),
        force_review=bool(value["force_review"]),
        normalized_discovery_filters=tuple(
            (item[0], item[1])
            for item in value["normalized_discovery_filters"]
        ),
    )
    return OfficialPredictionRunStart(
        run_id=row["run_id"],
        run_fingerprint=row["run_fingerprint"],
        request=request,
        policy_version=row["policy_version"],
        bankroll_scope=RiskProductScope(row["bankroll_scope"]),
        destination_scope=RiskProductScope(row["destination_scope"]),
        request_snapshot=tuple(
            (item[0], item[1]) for item in value["request_snapshot"]
        ),
    )


def _item_json(item: OfficialPredictionRunItemResult) -> str:
    return _json({
        "run_id": item.run_id,
        "item_index": item.item_index,
        "prediction_id": item.prediction_id,
        "match_id": item.match_id,
        "candidate_fingerprint": item.candidate_fingerprint,
        "kickoff_timestamp": item.kickoff_timestamp.isoformat(),
        "discovery_status": item.discovery_status.value,
        "status": item.status.value,
        "was_eligible": item.was_eligible,
        "started_timestamp": item.started_timestamp.isoformat(),
        "completed_timestamp": item.completed_timestamp.isoformat(),
        "orchestration_id": item.orchestration_id,
        "publication_attempt_reference": item.publication_attempt_reference,
        "ordered_reason_codes": list(item.ordered_reason_codes),
    })


def _item_from_row(row: sqlite3.Row) -> OfficialPredictionRunItemResult:
    return OfficialPredictionRunItemResult(
        run_id=row["run_id"],
        item_index=row["item_index"],
        prediction_id=row["prediction_id"],
        match_id=row["match_id"],
        candidate_fingerprint=row["candidate_fingerprint"],
        kickoff_timestamp=datetime.fromisoformat(row["kickoff_timestamp"]),
        discovery_status=CandidateDiscoveryStatus(row["discovery_status"]),
        status=OfficialPredictionRunItemStatus(row["item_status"]),
        was_eligible=bool(row["was_eligible"]),
        started_timestamp=datetime.fromisoformat(row["started_timestamp"]),
        completed_timestamp=datetime.fromisoformat(row["completed_timestamp"]),
        orchestration_id=row["orchestration_id"],
        publication_attempt_reference=row["publication_attempt_reference"],
        ordered_reason_codes=tuple(json.loads(row["ordered_reasons"])),
    )


def _result_counts(result: OfficialPredictionRunResult) -> tuple[int, ...]:
    return (
        result.discovered_count,
        result.eligible_count,
        result.processed_count,
        result.published_count,
        result.approved_not_published_count,
        result.rejected_count,
        result.review_required_count,
        result.duplicate_blocked_count,
        result.retryable_failure_count,
        result.indeterminate_failure_count,
        result.assembly_failure_count,
        result.skipped_count,
        result.internal_failure_count,
    )


def _result_json(result: OfficialPredictionRunResult) -> str:
    return _json({
        "run_id": result.run_id,
        "run_fingerprint": result.run_fingerprint,
        "run_status": result.run_status.value,
        "policy_version": result.policy_version,
        "dry_run": result.dry_run,
        "counts": list(_result_counts(result)),
        "ordered_internal_reasons": list(result.ordered_internal_reasons),
        "stop_reason": result.stop_reason,
    })


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
