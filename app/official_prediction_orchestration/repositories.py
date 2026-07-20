import json
import sqlite3
from datetime import datetime

from app.database import Database, MigrationManager

from .models import (
    OfficialPredictionOrchestrationOutcome,
    OfficialPredictionOrchestrationRecord,
    OrchestrationStatus,
    PublicationDeliveryState,
    PublicationStateRecord,
)

class SQLiteOfficialPublicationStateReader:
    """Reads durable publication facts without claiming or mutating delivery."""

    def __init__(self, database: Database) -> None:
        self._connection = database.connection
        MigrationManager(self._connection).migrate()

    def get(
        self,
        prediction_id: str,
        match_id: str,
        evaluated_at: datetime,
    ) -> PublicationStateRecord:
        if not prediction_id.strip() or not match_id.strip():
            raise ValueError("Publication lookup identity must not be empty.")
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("Publication-state cutoff must be timezone-aware.")
        published = self._connection.execute(
            """
            SELECT fixture_id, published_at FROM published_predictions
            WHERE prediction_id = ?
            """,
            (prediction_id,),
        ).fetchone()
        if published is not None:
            if str(published["fixture_id"]) != match_id:
                raise ValueError("Published prediction has a different match identity.")
            return PublicationStateRecord(
                prediction_id=prediction_id,
                match_id=match_id,
                state=PublicationDeliveryState.PUBLISHED,
                observed_at=evaluated_at,
                attempt_reference=None,
            )
        delivery = self._connection.execute(
            """
            SELECT match_id, status, attempt_reference
            FROM official_prediction_publication_events
            WHERE prediction_id = ? AND destination_scope = 'OFFICIAL'
            ORDER BY attempt_number DESC, event_sequence DESC, event_id DESC
            LIMIT 1
            """,
            (prediction_id,),
        ).fetchone()
        if delivery is not None:
            if delivery["match_id"] != match_id:
                raise ValueError("Publication attempt has a different match identity.")
            state = {
                "CLAIMED": PublicationDeliveryState.CLAIMED,
                "PUBLISHED": PublicationDeliveryState.PUBLISHED,
                "FAILED": PublicationDeliveryState.CONFIRMED_FAILED_RETRYABLE,
                "INDETERMINATE": PublicationDeliveryState.INDETERMINATE_FAILURE,
            }[delivery["status"]]
            return PublicationStateRecord(
                prediction_id=prediction_id,
                match_id=match_id,
                state=state,
                observed_at=evaluated_at,
                attempt_reference=delivery["attempt_reference"],
            )
        latest = self._connection.execute(
            """
            SELECT final_status, publisher_attempt_reference
            FROM official_prediction_orchestrations
            WHERE prediction_id = ?
            ORDER BY created_timestamp DESC, orchestration_id DESC
            LIMIT 1
            """,
            (prediction_id,),
        ).fetchone()
        state = PublicationDeliveryState.NEVER_ATTEMPTED
        reference = None
        if latest is not None:
            reference = latest["publisher_attempt_reference"]
            status = OrchestrationStatus(latest["final_status"])
            if status is OrchestrationStatus.PUBLISHED:
                state = PublicationDeliveryState.PUBLISHED
            elif status is OrchestrationStatus.RETRYABLE_PUBLICATION_FAILURE:
                state = PublicationDeliveryState.CONFIRMED_FAILED_RETRYABLE
            elif status is OrchestrationStatus.INDETERMINATE_PUBLICATION_FAILURE:
                state = PublicationDeliveryState.INDETERMINATE_FAILURE
        return PublicationStateRecord(
            prediction_id=prediction_id,
            match_id=match_id,
            state=state,
            observed_at=evaluated_at,
            attempt_reference=reference,
        )


class SQLiteOrchestrationHistoryRepository:
    """Append-only orchestration audit history with deterministic JSON."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append(
        self,
        record: OfficialPredictionOrchestrationRecord,
    ) -> OfficialPredictionOrchestrationRecord:
        outcome = record.outcome
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO official_prediction_orchestrations (
                        orchestration_id, prediction_id, candidate_fingerprint,
                        gate_evaluation_id, final_status, ordered_reasons,
                        internal_explanations, policy_version, model_version,
                        dry_run, publisher_attempt_reference,
                        normalized_input_snapshot, evaluated_timestamp,
                        created_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        outcome.orchestration_id,
                        outcome.prediction_id,
                        outcome.candidate_fingerprint,
                        outcome.quality_gate_evaluation_id,
                        outcome.final_status.value,
                        _json(list(outcome.ordered_reason_codes)),
                        _json(list(outcome.internal_explanations)),
                        outcome.policy_version,
                        outcome.model_version,
                        int(outcome.dry_run),
                        outcome.publication_attempt_reference,
                        _json([list(item) for item in record.normalized_input]),
                        outcome.evaluated_timestamp.isoformat(),
                        record.created_timestamp.isoformat(),
                    ),
                )
        except sqlite3.DatabaseError as exc:
            raise ValueError("Orchestration history could not be stored.") from exc
        stored = self.get(outcome.orchestration_id)
        if stored is None:
            raise ValueError("Orchestration history was not stored.")
        if stored != record:
            raise ValueError("Stored orchestration history conflicts with input.")
        return stored

    def get(
        self,
        orchestration_id: str,
    ) -> OfficialPredictionOrchestrationRecord | None:
        if not orchestration_id.strip():
            raise ValueError("Orchestration ID must not be empty.")
        row = self._connection.execute(
            """
            SELECT * FROM official_prediction_orchestrations
            WHERE orchestration_id = ?
            """,
            (orchestration_id,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def latest_for_fingerprint(
        self,
        prediction_id: str,
        candidate_fingerprint: str,
        dry_run: bool,
    ) -> OfficialPredictionOrchestrationRecord | None:
        row = self._connection.execute(
            """
            SELECT * FROM official_prediction_orchestrations
            WHERE prediction_id = ?
              AND candidate_fingerprint = ?
              AND dry_run = ?
            ORDER BY created_timestamp DESC, orchestration_id DESC
            LIMIT 1
            """,
            (prediction_id, candidate_fingerprint, int(dry_run)),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def history_for_prediction(
        self,
        prediction_id: str,
    ) -> tuple[OfficialPredictionOrchestrationRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM official_prediction_orchestrations
            WHERE prediction_id = ?
            ORDER BY created_timestamp, orchestration_id
            """,
            (prediction_id,),
        ).fetchall()
        return tuple(_from_row(row) for row in rows)


def _from_row(row: sqlite3.Row) -> OfficialPredictionOrchestrationRecord:
    outcome = OfficialPredictionOrchestrationOutcome(
        orchestration_id=row["orchestration_id"],
        prediction_id=row["prediction_id"],
        candidate_fingerprint=row["candidate_fingerprint"],
        quality_gate_evaluation_id=row["gate_evaluation_id"],
        final_status=OrchestrationStatus(row["final_status"]),
        ordered_reason_codes=tuple(json.loads(row["ordered_reasons"])),
        internal_explanations=tuple(json.loads(row["internal_explanations"])),
        publication_attempt_reference=row["publisher_attempt_reference"],
        evaluated_timestamp=datetime.fromisoformat(row["evaluated_timestamp"]),
        dry_run=bool(row["dry_run"]),
        policy_version=row["policy_version"],
        model_version=row["model_version"],
    )
    return OfficialPredictionOrchestrationRecord(
        outcome=outcome,
        normalized_input=tuple(
            (item[0], item[1])
            for item in json.loads(row["normalized_input_snapshot"])
        ),
        created_timestamp=datetime.fromisoformat(row["created_timestamp"]),
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
