"""Append-only SQLite audit storage and exactly-once delivery claims."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from app.database import Database, MigrationManager

from .fingerprint import canonical_json, fingerprint
from .models import (
    AnalysisRecord,
    DeliveryRecord,
    DeliveryStatus,
    LAB_CHAT_ID,
)


class AnalysisConflictError(RuntimeError):
    pass


class DeliveryConflictError(RuntimeError):
    pass


class SQLiteRealMatchLabRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self.connection = database.connection
        if migrate:
            MigrationManager(self.connection).migrate()

    def append_analysis(
        self, record: AnalysisRecord, stages: tuple[tuple[str, str, str | None], ...]
    ) -> tuple[sqlite3.Row, bool]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.connection.execute(
                "SELECT * FROM real_match_lab_analyses WHERE request_id=?",
                (record.request_id,),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != record.request_fingerprint:
                    raise AnalysisConflictError(
                        "Analysis request ID has different immutable content."
                    )
                self.connection.commit()
                return existing, True
            selected = record.selected_market.market if record.selected_market else None
            self.connection.execute(
                """INSERT INTO real_match_lab_analyses VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.analysis_id, record.request_id, record.request_fingerprint,
                    record.result_fingerprint, record.status.value,
                    record.input.match_id, record.input.kickoff_utc.isoformat(),
                    record.input.environment, record.input.scope,
                    record.destination_chat_id, record.destination_bot, selected,
                    record.message_html, record.message_fingerprint,
                    canonical_json(record.input), canonical_json(record),
                    record.created_at.isoformat(),
                ),
            )
            evaluations = record.evidence.evaluations if record.evidence else ()
            for order, item in enumerate(evaluations):
                item_fp = fingerprint(item)
                self.connection.execute(
                    """INSERT INTO real_match_lab_market_evaluations
                    VALUES (?,?,?,?,?,?,?)""",
                    (
                        f"real-match-lab-evaluation-{item_fp}",
                        record.analysis_id, order, item.market, int(item.selected),
                        item_fp, canonical_json(item),
                    ),
                )
            for order, (stage, status, reason) in enumerate(stages):
                material = {
                    "analysis_id": record.analysis_id, "order": order,
                    "stage": stage, "status": status, "reason": reason,
                }
                event_fp = fingerprint(material)
                self.connection.execute(
                    """INSERT INTO real_match_lab_stage_events
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        f"real-match-lab-event-{event_fp}", record.analysis_id,
                        order, stage, status, reason, event_fp,
                        canonical_json(material), record.created_at.isoformat(),
                    ),
                )
            self.connection.commit()
            return self.load_analysis(record.analysis_id), False
        except AnalysisConflictError:
            self.connection.rollback()
            raise
        except sqlite3.DatabaseError:
            self.connection.rollback()
            raise

    def load_analysis(self, analysis_id: str):
        return self.connection.execute(
            "SELECT * FROM real_match_lab_analyses WHERE analysis_id=?",
            (analysis_id,),
        ).fetchone()

    def find_by_request_fingerprint(self, request_fingerprint: str):
        return self.connection.execute(
            "SELECT * FROM real_match_lab_analyses WHERE request_fingerprint=?",
            (request_fingerprint,),
        ).fetchone()

    def market_evaluations(self, analysis_id: str):
        return self.connection.execute(
            """SELECT evaluation_snapshot FROM real_match_lab_market_evaluations
            WHERE analysis_id=? ORDER BY deterministic_order""",
            (analysis_id,),
        ).fetchall()

    def stage_events(self, analysis_id: str):
        return self.connection.execute(
            """SELECT event_snapshot FROM real_match_lab_stage_events
            WHERE analysis_id=? ORDER BY deterministic_order""",
            (analysis_id,),
        ).fetchall()

    def delivery_history(self, analysis_id: str) -> tuple[DeliveryRecord, ...]:
        rows = self.connection.execute(
            """SELECT * FROM real_match_lab_deliveries WHERE analysis_id=?
            ORDER BY attempt_number,event_sequence""", (analysis_id,),
        ).fetchall()
        return tuple(_delivery(row) for row in rows)

    def claim_delivery(self, analysis_id: str, occurred_at: datetime) -> DeliveryRecord:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            analysis = self.load_analysis(analysis_id)
            if analysis is None or analysis["status"] != "COMPLETED":
                raise DeliveryConflictError("Analysis is not eligible to send.")
            history = self.delivery_history(analysis_id)
            if history and history[-1].status in {
                DeliveryStatus.SENT, DeliveryStatus.INDETERMINATE,
                DeliveryStatus.CLAIMED,
            }:
                raise DeliveryConflictError(
                    "Delivery already succeeded or is in an uncertain/active state."
                )
            attempt = (history[-1].attempt_number + 1) if history else 1
            record = _make_delivery(
                analysis_id, attempt, 1, DeliveryStatus.CLAIMED,
                analysis["message_fingerprint"], occurred_at,
            )
            self._insert_delivery(record, 1)
            self.connection.commit()
            return record
        except DeliveryConflictError:
            self.connection.rollback()
            raise
        except sqlite3.DatabaseError:
            self.connection.rollback()
            raise

    def finalize_delivery(
        self, claim: DeliveryRecord, status: DeliveryStatus, occurred_at: datetime,
        *, telegram_message_id: int | None = None, reason_code: str | None = None,
    ) -> DeliveryRecord:
        if status not in {
            DeliveryStatus.SENT, DeliveryStatus.FAILED, DeliveryStatus.INDETERMINATE
        }:
            raise ValueError("Terminal delivery status required.")
        record = _make_delivery(
            claim.analysis_id, claim.attempt_number, 2, status,
            claim.message_fingerprint, occurred_at,
            telegram_message_id=telegram_message_id, reason_code=reason_code,
        )
        try:
            with self.connection:
                self._insert_delivery(record, 2)
        except sqlite3.DatabaseError as exc:
            raise DeliveryConflictError(
                "Terminal delivery state could not be persisted; do not retry automatically."
            ) from exc
        return record

    def _insert_delivery(self, record: DeliveryRecord, sequence: int) -> None:
        self.connection.execute(
            """INSERT INTO real_match_lab_deliveries VALUES
            (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.delivery_id, record.analysis_id, record.attempt_number,
                sequence, record.status.value, record.destination_chat_id,
                record.message_fingerprint, record.telegram_message_id,
                record.reason_code, fingerprint(record), record.occurred_at.isoformat(),
            ),
        )


def _make_delivery(
    analysis_id, attempt, sequence, status, message_fingerprint, occurred_at,
    telegram_message_id=None, reason_code=None,
):
    material = (analysis_id, attempt, sequence, status.value, message_fingerprint)
    return DeliveryRecord(
        delivery_id="real-match-lab-delivery-" + fingerprint(material),
        analysis_id=analysis_id, attempt_number=attempt, status=status,
        destination_chat_id=LAB_CHAT_ID,
        message_fingerprint=message_fingerprint, occurred_at=occurred_at,
        telegram_message_id=telegram_message_id, reason_code=reason_code,
    )


def _delivery(row) -> DeliveryRecord:
    return DeliveryRecord(
        row["delivery_id"], row["analysis_id"], row["attempt_number"],
        DeliveryStatus(row["status"]), row["destination_chat_id"],
        row["message_fingerprint"], datetime.fromisoformat(row["occurred_at"]),
        row["telegram_message_id"], row["reason_code"],
    )


def row_as_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("request_snapshot", "result_snapshot"):
        if key in result:
            result[key] = json.loads(result[key])
    return result
