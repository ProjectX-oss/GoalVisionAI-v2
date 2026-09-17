import sqlite3
from datetime import datetime

from app.bankroll import BankrollProduct
from app.result_publication.models import (
    ResultPublicationAuditRecord,
    ResultPublicationClaim,
    ResultPublicationFailureReason,
    ResultPublicationStatus,
)

from .database import Database
from .migrations import MigrationManager


class SQLiteResultPublicationRepository:
    """Persists Official Telegram result delivery state and retry attempts."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def get(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
    ) -> ResultPublicationAuditRecord | None:
        self._validate_key(prediction_id, product_id, destination)
        row = self._connection.execute(
            """
            SELECT * FROM result_publications
            WHERE prediction_id = ?
              AND product_id = ?
              AND telegram_destination = ?
            """,
            (prediction_id, product_id.value, destination),
        ).fetchone()
        return self._from_row(row) if row is not None else None

    def begin_attempt(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        attempted_at: datetime,
        format_version: str,
    ) -> ResultPublicationClaim:
        self._validate_key(prediction_id, product_id, destination)
        if attempted_at.tzinfo is None:
            raise ValueError("Attempt timestamp must be timezone-aware.")
        if not format_version.strip():
            raise ValueError("Publication format version must not be empty.")
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    INSERT INTO result_publications (
                        prediction_id, product_id, telegram_destination,
                        publication_status, telegram_message_id, attempted_at,
                        published_at, failure_reason, format_version,
                        attempt_count
                    )
                    VALUES (?, ?, ?, 'ATTEMPTING', NULL, ?, NULL, NULL, ?, 1)
                    ON CONFLICT(
                        prediction_id, product_id, telegram_destination
                    ) DO UPDATE SET
                        publication_status = 'ATTEMPTING',
                        telegram_message_id = NULL,
                        attempted_at = excluded.attempted_at,
                        published_at = NULL,
                        failure_reason = NULL,
                        format_version = excluded.format_version,
                        attempt_count = result_publications.attempt_count + 1
                    WHERE result_publications.publication_status = 'FAILED'
                    """,
                    (
                        prediction_id,
                        product_id.value,
                        destination,
                        attempted_at.isoformat(),
                        format_version,
                    ),
                )
        except sqlite3.DatabaseError as error:
            raise ValueError("Publication attempt could not be stored.") from error
        record = self.get(prediction_id, product_id, destination)
        if record is None:
            raise ValueError("Publication attempt was not stored.")
        return ResultPublicationClaim(record=record, acquired=cursor.rowcount == 1)

    def mark_published(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        telegram_message_id: int | None,
        published_at: datetime,
    ) -> ResultPublicationAuditRecord:
        if published_at.tzinfo is None:
            raise ValueError("Published timestamp must be timezone-aware.")
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    UPDATE result_publications
                    SET publication_status = 'PUBLISHED',
                        telegram_message_id = ?,
                        published_at = ?,
                        failure_reason = NULL
                    WHERE prediction_id = ?
                      AND product_id = ?
                      AND telegram_destination = ?
                      AND publication_status = 'ATTEMPTING'
                    """,
                    (
                        telegram_message_id,
                        published_at.isoformat(),
                        prediction_id,
                        product_id.value,
                        destination,
                    ),
                )
        except sqlite3.DatabaseError as error:
            raise ValueError("Published delivery could not be stored.") from error
        if cursor.rowcount != 1:
            raise ValueError("Publication attempt is not active.")
        return self._require(prediction_id, product_id, destination)

    def mark_failed(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        reason: ResultPublicationFailureReason,
    ) -> ResultPublicationAuditRecord:
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    UPDATE result_publications
                    SET publication_status = 'FAILED',
                        telegram_message_id = NULL,
                        published_at = NULL,
                        failure_reason = ?
                    WHERE prediction_id = ?
                      AND product_id = ?
                      AND telegram_destination = ?
                      AND publication_status = 'ATTEMPTING'
                    """,
                    (
                        reason.value,
                        prediction_id,
                        product_id.value,
                        destination,
                    ),
                )
        except sqlite3.DatabaseError as error:
            raise ValueError("Publication failure could not be stored.") from error
        if cursor.rowcount != 1:
            raise ValueError("Publication attempt is not active.")
        return self._require(prediction_id, product_id, destination)

    def _require(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
    ) -> ResultPublicationAuditRecord:
        record = self.get(prediction_id, product_id, destination)
        if record is None:
            raise ValueError("Publication audit record is missing.")
        return record

    @staticmethod
    def _validate_key(
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
    ) -> None:
        if product_id is not BankrollProduct.OFFICIAL:
            raise ValueError("Only Official result publication is enabled.")
        if not prediction_id.strip() or not destination.strip():
            raise ValueError("Prediction ID and destination must not be empty.")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ResultPublicationAuditRecord:
        failure = row["failure_reason"]
        published = row["published_at"]
        return ResultPublicationAuditRecord(
            prediction_id=row["prediction_id"],
            product_id=BankrollProduct(row["product_id"]),
            destination=row["telegram_destination"],
            status=ResultPublicationStatus(row["publication_status"]),
            telegram_message_id=row["telegram_message_id"],
            attempted_at=datetime.fromisoformat(row["attempted_at"]),
            published_at=(datetime.fromisoformat(published) if published else None),
            failure_reason=(
                ResultPublicationFailureReason(failure) if failure else None
            ),
            format_version=row["format_version"],
            attempt_count=row["attempt_count"],
        )
