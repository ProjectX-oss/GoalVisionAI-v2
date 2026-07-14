import json
import sqlite3
from datetime import datetime

from app.results import (
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
    SettlementReasonCode,
)

from .database import Database
from .migrations import MigrationManager


class SQLitePredictionResultRepository:
    """Persists published predictions and immutable terminal settlements."""

    _TERMINAL_STATUSES = (
        ResolutionStatus.WON.value,
        ResolutionStatus.LOST.value,
        ResolutionStatus.VOID.value,
    )

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._database = database
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def save_published(
        self,
        prediction: PublishedPredictionReference,
    ) -> PublishedPredictionReference:
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO published_predictions (
                        prediction_id,
                        fixture_id,
                        market,
                        pick,
                        odds,
                        stake,
                        published_at,
                        settlement_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                    ON CONFLICT(prediction_id) DO NOTHING
                    """,
                    (
                        prediction.prediction_id,
                        prediction.fixture_id,
                        prediction.market,
                        prediction.selection,
                        prediction.odds,
                        prediction.stake,
                        prediction.published_at.isoformat(),
                    ),
                )
        except sqlite3.DatabaseError as error:
            raise ValueError("Published prediction could not be stored.") from error

        stored = self.get_published(prediction.prediction_id)
        if stored is None:
            raise ValueError("Published prediction was not stored.")
        if stored != prediction:
            raise ValueError("Prediction ID already has different published data.")
        return stored

    def load_pending(self) -> tuple[PublishedPredictionReference, ...]:
        rows = self._connection.execute(
            """
            SELECT prediction_id, fixture_id, market, pick, odds, stake,
                   published_at
            FROM published_predictions
            WHERE settlement_status IN ('PENDING', 'UNRESOLVED')
            ORDER BY published_at, prediction_id
            """
        ).fetchall()
        return tuple(self._prediction_from_row(row) for row in rows)

    def get_published(
        self,
        prediction_id: str,
    ) -> PublishedPredictionReference | None:
        row = self._connection.execute(
            """
            SELECT prediction_id, fixture_id, market, pick, odds, stake,
                   published_at
            FROM published_predictions
            WHERE prediction_id = ?
            """,
            (prediction_id,),
        ).fetchone()
        return self._prediction_from_row(row) if row is not None else None

    def get_resolved(
        self,
        prediction_id: str,
    ) -> ResolvedPredictionResult | None:
        row = self._connection.execute(
            """
            SELECT prediction_id, fixture_id, settlement_status,
                   home_score, away_score, settlement_reason_codes,
                   settlement_rule_version, resolved_at
            FROM published_predictions
            WHERE prediction_id = ?
              AND settlement_status IN ('WON', 'LOST', 'VOID')
            """,
            (prediction_id,),
        ).fetchone()
        return self._result_from_row(row) if row is not None else None

    def store_if_absent(
        self,
        result: ResolvedPredictionResult,
    ) -> ResolvedPredictionResult:
        if not result.is_terminal:
            raise ValueError("Only terminal prediction results may be stored.")
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    UPDATE published_predictions
                    SET settlement_status = ?,
                        home_score = ?,
                        away_score = ?,
                        settlement_reason_codes = ?,
                        settlement_rule_version = ?,
                        resolved_at = ?
                    WHERE prediction_id = ?
                      AND fixture_id = ?
                      AND settlement_status IN ('PENDING', 'UNRESOLVED')
                    """,
                    (
                        result.status.value,
                        result.home_score,
                        result.away_score,
                        self._encode_reason_codes(result.reason_codes),
                        result.settlement_rule_version,
                        result.resolved_at.isoformat(),
                        result.prediction_id,
                        result.fixture_id,
                    ),
                )
        except sqlite3.DatabaseError as error:
            raise ValueError("Resolved prediction could not be stored.") from error

        if cursor.rowcount == 1:
            return result
        existing = self.get_resolved(result.prediction_id)
        if existing is not None:
            return existing
        raise ValueError("Cannot settle an unknown or mismatched prediction.")

    def load_history(self) -> tuple[ResolvedPredictionResult, ...]:
        placeholders = ", ".join("?" for _ in self._TERMINAL_STATUSES)
        rows = self._connection.execute(
            f"""
            SELECT prediction_id, fixture_id, settlement_status,
                   home_score, away_score, settlement_reason_codes,
                   settlement_rule_version, resolved_at
            FROM published_predictions
            WHERE settlement_status IN ({placeholders})
            ORDER BY resolved_at, prediction_id
            """,
            self._TERMINAL_STATUSES,
        ).fetchall()
        return tuple(self._result_from_row(row) for row in rows)

    @staticmethod
    def _prediction_from_row(row: sqlite3.Row) -> PublishedPredictionReference:
        return PublishedPredictionReference(
            prediction_id=row["prediction_id"],
            fixture_id=row["fixture_id"],
            market=row["market"],
            selection=row["pick"],
            published_at=datetime.fromisoformat(row["published_at"]),
            odds=row["odds"],
            stake=row["stake"],
        )

    @staticmethod
    def _result_from_row(row: sqlite3.Row) -> ResolvedPredictionResult:
        resolved_at = row["resolved_at"]
        rule_version = row["settlement_rule_version"]
        if resolved_at is None or rule_version is None:
            raise ValueError("Stored terminal settlement audit data is incomplete.")
        return ResolvedPredictionResult(
            prediction_id=row["prediction_id"],
            fixture_id=row["fixture_id"],
            status=ResolutionStatus(row["settlement_status"]),
            resolved_at=datetime.fromisoformat(resolved_at),
            home_score=row["home_score"],
            away_score=row["away_score"],
            settlement_rule_version=rule_version,
            reason_codes=SQLitePredictionResultRepository._decode_reason_codes(
                row["settlement_reason_codes"]
            ),
        )

    @staticmethod
    def _encode_reason_codes(
        reason_codes: tuple[SettlementReasonCode, ...],
    ) -> str:
        return json.dumps(
            [reason.value for reason in reason_codes],
            separators=(",", ":"),
        )

    @staticmethod
    def _decode_reason_codes(value: str) -> tuple[SettlementReasonCode, ...]:
        try:
            decoded = json.loads(value)
            if not isinstance(decoded, list):
                raise ValueError
            return tuple(SettlementReasonCode(reason) for reason in decoded)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError("Stored settlement reason codes are invalid.") from error
