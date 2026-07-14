from datetime import datetime
from typing import Protocol

from app.bankroll import BankrollProduct

from .models import (
    ResultPublicationAuditRecord,
    ResultPublicationClaim,
    ResultPublicationFailureReason,
    ResultPublicationStatus,
)


class ResultPublicationRepository(Protocol):
    def get(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
    ) -> ResultPublicationAuditRecord | None:
        ...

    def begin_attempt(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        attempted_at: datetime,
        format_version: str,
    ) -> ResultPublicationClaim:
        ...

    def mark_published(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        telegram_message_id: int | None,
        published_at: datetime,
    ) -> ResultPublicationAuditRecord:
        ...

    def mark_failed(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        reason: ResultPublicationFailureReason,
    ) -> ResultPublicationAuditRecord:
        ...


class InMemoryResultPublicationRepository:
    def __init__(self) -> None:
        self._records: dict[
            tuple[str, BankrollProduct, str],
            ResultPublicationAuditRecord,
        ] = {}

    @staticmethod
    def _key(
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
    ) -> tuple[str, BankrollProduct, str]:
        return prediction_id, product_id, destination

    def get(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
    ) -> ResultPublicationAuditRecord | None:
        return self._records.get(self._key(prediction_id, product_id, destination))

    def begin_attempt(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        attempted_at: datetime,
        format_version: str,
    ) -> ResultPublicationClaim:
        key = self._key(prediction_id, product_id, destination)
        existing = self._records.get(key)
        if existing is not None and existing.status is not ResultPublicationStatus.FAILED:
            return ResultPublicationClaim(record=existing, acquired=False)
        record = ResultPublicationAuditRecord(
            prediction_id=prediction_id,
            product_id=product_id,
            destination=destination,
            status=ResultPublicationStatus.ATTEMPTING,
            telegram_message_id=None,
            attempted_at=attempted_at,
            published_at=None,
            failure_reason=None,
            format_version=format_version,
            attempt_count=(existing.attempt_count + 1 if existing else 1),
        )
        self._records[key] = record
        return ResultPublicationClaim(record=record, acquired=True)

    def mark_published(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        telegram_message_id: int | None,
        published_at: datetime,
    ) -> ResultPublicationAuditRecord:
        record = self._active(prediction_id, product_id, destination)
        published = ResultPublicationAuditRecord(
            prediction_id=record.prediction_id,
            product_id=record.product_id,
            destination=record.destination,
            status=ResultPublicationStatus.PUBLISHED,
            telegram_message_id=telegram_message_id,
            attempted_at=record.attempted_at,
            published_at=published_at,
            failure_reason=None,
            format_version=record.format_version,
            attempt_count=record.attempt_count,
        )
        self._records[self._key(prediction_id, product_id, destination)] = published
        return published

    def mark_failed(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
        reason: ResultPublicationFailureReason,
    ) -> ResultPublicationAuditRecord:
        record = self._active(prediction_id, product_id, destination)
        failed = ResultPublicationAuditRecord(
            prediction_id=record.prediction_id,
            product_id=record.product_id,
            destination=record.destination,
            status=ResultPublicationStatus.FAILED,
            telegram_message_id=None,
            attempted_at=record.attempted_at,
            published_at=None,
            failure_reason=reason,
            format_version=record.format_version,
            attempt_count=record.attempt_count,
        )
        self._records[self._key(prediction_id, product_id, destination)] = failed
        return failed

    def _active(
        self,
        prediction_id: str,
        product_id: BankrollProduct,
        destination: str,
    ) -> ResultPublicationAuditRecord:
        record = self.get(prediction_id, product_id, destination)
        if record is None or record.status is not ResultPublicationStatus.ATTEMPTING:
            raise ValueError("Publication attempt is not active.")
        return record
