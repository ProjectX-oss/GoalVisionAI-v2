"""Manual dry-run orchestration and explicit exactly-once Lab delivery."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol

from telegram.error import TelegramError

from app.services.telegram_service import TelegramMessageReceipt

from .engine import EngineRejected
from .fingerprint import fingerprint
from .message import build_message
from .models import (
    AnalysisRecord,
    AnalysisStatus,
    DeliveryRecord,
    DeliveryStatus,
    LAB_BOT_USERNAME,
    LAB_CHAT_ID,
    SCHEMA_VERSION,
    SEND_CONFIRMATION,
    RealMatchLabInput,
)
from .repository import (
    AnalysisConflictError,
    DeliveryConflictError,
    SQLiteRealMatchLabRepository,
)


class AnalysisEngine(Protocol):
    def analyze(self, command: RealMatchLabInput, now: datetime): ...


class TelegramTransport(Protocol):
    async def send_message_receipt(
        self, chat_id: str, text: str, parse_mode: str | None = None,
        *, timeout_seconds: float,
    ) -> TelegramMessageReceipt: ...


class RealMatchLabAnalysisService:
    def __init__(
        self, repository: SQLiteRealMatchLabRepository, engine: AnalysisEngine
    ) -> None:
        self.repository = repository
        self.engine = engine

    def analyze(self, command: RealMatchLabInput) -> AnalysisRecord:
        request_fp = fingerprint(command)
        existing = self.repository.connection.execute(
            "SELECT request_fingerprint FROM real_match_lab_analyses WHERE request_id=?",
            (command.request_id,),
        ).fetchone()
        if existing is not None and existing[0] != request_fp:
            raise AnalysisConflictError(
                "Analysis request ID has different immutable content."
            )
        stages = [
            ("INPUT_VALIDATION", "PASSED", None),
            ("DESTINATION_GUARD", "PASSED", None),
        ]
        evidence = None
        selected = None
        message = None
        message_fp = None
        reasons = ()
        try:
            evidence = self.engine.analyze(command, command.collected_at)
            stages.extend((
                ("MATCH_SNAPSHOT", "PASSED", None),
                ("FEATURE_STORE", "PASSED", None),
                ("MODEL_INPUT", "PASSED", None),
                ("CHAMPION_RESOLUTION", "PASSED", None),
                ("RAW_INFERENCE", "PASSED", None),
                ("CALIBRATION", "PASSED", None),
                ("VALUE_ASSESSMENT", "PASSED", None),
                ("LAB_SELECTION", "PASSED", None),
            ))
            selected = next((item for item in evidence.evaluations if item.selected), None)
            if selected is not None:
                message, message_fp = build_message(command, evidence, selected)
                status = AnalysisStatus.COMPLETED
                stages.append(("MESSAGE_ASSEMBLY", "PASSED", None))
            else:
                status = AnalysisStatus.NO_SELECTION
                reasons = ("NO_POSITIVE_VALUE_LAB_SELECTION",)
                stages.append(("MESSAGE_ASSEMBLY", "SKIPPED", reasons[0]))
        except EngineRejected as exc:
            status = AnalysisStatus.REJECTED
            reasons = (exc.reason_code,)
            stages.append(("ANALYSIS_PIPELINE", "REJECTED", exc.reason_code))

        result_material = {
            "schema_version": SCHEMA_VERSION,
            "request_fingerprint": request_fp,
            "status": status,
            "evidence": evidence,
            "selection": selected,
            "message_fingerprint": message_fp,
            "rejection_reasons": reasons,
        }
        result_fp = fingerprint(result_material)
        record = AnalysisRecord(
            analysis_id="real-match-lab-analysis-" + fingerprint(
                (command.request_id, request_fp)
            ),
            request_id=command.request_id,
            request_fingerprint=request_fp,
            result_fingerprint=result_fp,
            status=status,
            input=command,
            evidence=evidence,
            selected_market=selected,
            message_html=message,
            message_fingerprint=message_fp,
            rejection_reasons=reasons,
            created_at=command.collected_at,
        )
        self.repository.append_analysis(record, tuple(stages))
        return record

    async def send(
        self, analysis_id: str, confirmation: str,
        *, token: str | None, configured_chat_id: str | None,
        configured_bot: str | None, transport: TelegramTransport,
        occurred_at: datetime | None = None,
    ) -> DeliveryRecord:
        if confirmation != SEND_CONFIRMATION:
            raise DeliveryConflictError("Exact send confirmation is required.")
        if configured_chat_id != LAB_CHAT_ID:
            raise DeliveryConflictError("Configured destination is not the Lab channel.")
        if configured_bot != LAB_BOT_USERNAME:
            raise DeliveryConflictError("Configured bot is not the approved Lab bot.")
        if not token:
            raise DeliveryConflictError("Lab bot token is missing.")
        row = self.repository.load_analysis(analysis_id)
        if row is None or row["destination_chat_id"] != LAB_CHAT_ID:
            raise DeliveryConflictError("Analysis destination is invalid.")
        if row["destination_bot"] != LAB_BOT_USERNAME or not row["message_html"]:
            raise DeliveryConflictError("Analysis has no eligible Lab message.")
        occurred_at = occurred_at or datetime.now(timezone.utc)
        claim = self.repository.claim_delivery(analysis_id, occurred_at)
        try:
            receipt = await asyncio.wait_for(
                transport.send_message_receipt(
                    LAB_CHAT_ID, row["message_html"], parse_mode="HTML",
                    timeout_seconds=10.0,
                ),
                timeout=11.0,
            )
        except TelegramError:
            return self.repository.finalize_delivery(
                claim, DeliveryStatus.FAILED, occurred_at,
                reason_code="TELEGRAM_CONFIRMED_FAILURE",
            )
        except Exception:
            return self.repository.finalize_delivery(
                claim, DeliveryStatus.INDETERMINATE, occurred_at,
                reason_code="TELEGRAM_DELIVERY_UNCERTAIN",
            )
        if (
            receipt.chat_id != LAB_CHAT_ID
            or not isinstance(receipt.message_id, int)
            or receipt.message_id <= 0
        ):
            return self.repository.finalize_delivery(
                claim, DeliveryStatus.INDETERMINATE, occurred_at,
                reason_code="INVALID_TELEGRAM_RECEIPT",
            )
        return self.repository.finalize_delivery(
            claim, DeliveryStatus.SENT, occurred_at,
            telegram_message_id=receipt.message_id,
        )
