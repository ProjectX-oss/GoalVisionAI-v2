import hashlib
import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from app.database import Database, MigrationManager
from app.risk_management import RiskProductScope

from .exceptions import PredictionPublicationPersistenceError
from .models import (
    OfficialPredictionPublicationPayload,
    PredictionPublicationClaim,
    PredictionPublicationEvent,
    PredictionPublicationEventStatus,
    PredictionPublicationFailureReason,
    PublicStakeRating,
)


class SQLiteAtomicPredictionPublicationRepository:
    """Append-only prediction delivery claims and terminal events."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def latest(
        self,
        prediction_id: str,
        destination_scope: str,
    ) -> PredictionPublicationEvent | None:
        row = self._connection.execute(
            """
            SELECT * FROM official_prediction_publication_events
            WHERE prediction_id = ? AND destination_scope = ?
            ORDER BY attempt_number DESC, event_sequence DESC, event_id DESC
            LIMIT 1
            """,
            (prediction_id, destination_scope),
        ).fetchone()
        return _event(row) if row is not None else None

    def begin_attempt(
        self,
        payload: OfficialPredictionPublicationPayload,
        attempted_at: datetime,
    ) -> PredictionPublicationClaim:
        _aware(attempted_at, "Publication attempt timestamp")
        scope = payload.destination_scope.value
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            latest = self.latest(payload.prediction_id, scope)
            if latest is not None and latest.status is not PredictionPublicationEventStatus.FAILED:
                self._connection.commit()
                return PredictionPublicationClaim(False, latest)
            attempt_number = latest.attempt_number + 1 if latest else 1
            reference = _attempt_reference(payload, attempt_number)
            event = PredictionPublicationEvent(
                event_id=f"{reference}:CLAIMED",
                attempt_reference=reference,
                attempt_number=attempt_number,
                event_sequence=1,
                status=PredictionPublicationEventStatus.CLAIMED,
                payload=payload,
                occurred_at=attempted_at,
            )
            self._insert(event)
            self._connection.commit()
            return PredictionPublicationClaim(True, event)
        except sqlite3.DatabaseError as exc:
            self._connection.rollback()
            raise PredictionPublicationPersistenceError(
                "Prediction publication claim could not be stored."
            ) from exc

    def append_terminal(
        self,
        attempt_reference: str,
        status: PredictionPublicationEventStatus,
        occurred_at: datetime,
        *,
        telegram_message_id: int | None = None,
        failure_reason: PredictionPublicationFailureReason | None = None,
    ) -> PredictionPublicationEvent:
        if status not in {
            PredictionPublicationEventStatus.PUBLISHED,
            PredictionPublicationEventStatus.FAILED,
            PredictionPublicationEventStatus.INDETERMINATE,
        }:
            raise ValueError("A terminal publication status is required.")
        _aware(occurred_at, "Publication terminal timestamp")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            claimed_row = self._connection.execute(
                """
                SELECT * FROM official_prediction_publication_events
                WHERE attempt_reference = ? AND status = 'CLAIMED'
                """,
                (attempt_reference,),
            ).fetchone()
            if claimed_row is None:
                raise PredictionPublicationPersistenceError(
                    "Prediction publication claim is missing."
                )
            claimed = _event(claimed_row)
            current = self.latest(
                claimed.payload.prediction_id,
                claimed.payload.destination_scope.value,
            )
            if current is None or current.event_id != claimed.event_id:
                raise PredictionPublicationPersistenceError(
                    "Prediction publication claim is no longer active."
                )
            event = PredictionPublicationEvent(
                event_id=f"{attempt_reference}:{status.value}",
                attempt_reference=attempt_reference,
                attempt_number=claimed.attempt_number,
                event_sequence=2,
                status=status,
                payload=claimed.payload,
                occurred_at=occurred_at,
                telegram_message_id=telegram_message_id,
                failure_reason=failure_reason,
            )
            self._insert(event)
            self._connection.commit()
        except PredictionPublicationPersistenceError:
            self._connection.rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._connection.rollback()
            raise PredictionPublicationPersistenceError(
                "Prediction publication terminal event could not be stored."
            ) from exc
        return event

    def history(
        self,
        prediction_id: str,
    ) -> tuple[PredictionPublicationEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM official_prediction_publication_events
            WHERE prediction_id = ?
            ORDER BY attempt_number, event_sequence, event_id
            """,
            (prediction_id,),
        ).fetchall()
        return tuple(_event(row) for row in rows)

    def _insert(self, event: PredictionPublicationEvent) -> None:
        self._connection.execute(
            """
            INSERT INTO official_prediction_publication_events (
                event_id, attempt_reference, attempt_number, event_sequence,
                prediction_id, match_id, orchestration_id,
                gate_evaluation_id, candidate_fingerprint,
                message_fingerprint, destination_scope, status,
                telegram_message_id, failure_reason, payload_snapshot,
                occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.attempt_reference,
                event.attempt_number,
                event.event_sequence,
                event.payload.prediction_id,
                event.payload.match_id,
                event.payload.orchestration_id,
                event.payload.gate_evaluation_id,
                event.payload.candidate_fingerprint,
                event.payload.message_fingerprint,
                event.payload.destination_scope.value,
                event.status.value,
                event.telegram_message_id,
                event.failure_reason.value if event.failure_reason else None,
                _payload_json(event.payload),
                event.occurred_at.isoformat(),
            ),
        )


def _attempt_reference(
    payload: OfficialPredictionPublicationPayload,
    attempt_number: int,
) -> str:
    seed = "|".join((
        "official-prediction-attempt-v1",
        payload.prediction_id,
        payload.destination_scope.value,
        str(attempt_number),
        payload.message_fingerprint,
    ))
    return "official-prediction-attempt-" + hashlib.sha256(
        seed.encode("utf-8")
    ).hexdigest()


def _payload_json(payload: OfficialPredictionPublicationPayload) -> str:
    return json.dumps(
        {
            "prediction_id": payload.prediction_id,
            "match_id": payload.match_id,
            "orchestration_id": payload.orchestration_id,
            "gate_evaluation_id": payload.gate_evaluation_id,
            "candidate_fingerprint": payload.candidate_fingerprint,
            "message_fingerprint": payload.message_fingerprint,
            "destination_scope": payload.destination_scope.value,
            "rendered_text": payload.rendered_text,
            "parse_mode": payload.parse_mode,
            "approved_odds": str(payload.approved_odds),
            "calibrated_probability": str(payload.calibrated_probability),
            "public_confidence": payload.public_confidence,
            "public_stake_rating": {
                "stars": payload.public_stake_rating.stars,
                "rendered": payload.public_stake_rating.rendered,
            },
            "created_timestamp": payload.created_timestamp.isoformat(),
            "model_version": payload.model_version,
            "policy_version": payload.policy_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _event(row: sqlite3.Row) -> PredictionPublicationEvent:
    value = json.loads(row["payload_snapshot"])
    rating = value["public_stake_rating"]
    payload = OfficialPredictionPublicationPayload(
        prediction_id=value["prediction_id"],
        match_id=value["match_id"],
        orchestration_id=value["orchestration_id"],
        gate_evaluation_id=value["gate_evaluation_id"],
        candidate_fingerprint=value["candidate_fingerprint"],
        message_fingerprint=value["message_fingerprint"],
        destination_scope=RiskProductScope(value["destination_scope"]),
        rendered_text=value["rendered_text"],
        parse_mode=value["parse_mode"],
        approved_odds=Decimal(value["approved_odds"]),
        calibrated_probability=Decimal(value["calibrated_probability"]),
        public_confidence=value["public_confidence"],
        public_stake_rating=PublicStakeRating(
            stars=rating["stars"],
            rendered=rating["rendered"],
        ),
        created_timestamp=datetime.fromisoformat(value["created_timestamp"]),
        model_version=value["model_version"],
        policy_version=value["policy_version"],
    )
    failure = row["failure_reason"]
    return PredictionPublicationEvent(
        event_id=row["event_id"],
        attempt_reference=row["attempt_reference"],
        attempt_number=row["attempt_number"],
        event_sequence=row["event_sequence"],
        status=PredictionPublicationEventStatus(row["status"]),
        payload=payload,
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        telegram_message_id=row["telegram_message_id"],
        failure_reason=(
            PredictionPublicationFailureReason(failure) if failure else None
        ),
    )


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
