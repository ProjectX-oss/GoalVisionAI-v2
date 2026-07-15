from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from app.quality_gate import QualityGateStatus
from app.results import ResolutionStatus

from .models import (
    ShadowComparisonReport,
    ShadowEvaluationRecord,
    ShadowGateStatusStatistics,
    ShadowPerformanceStatistics,
    ShadowReasonStatistics,
)
from .repository import ShadowEvaluationRepository


ZERO = Decimal("0")
ONE = Decimal("1")


class ShadowComparisonReportService:
    """Produces descriptive and explicitly hypothetical one-unit reports.

    Hypotheticals include only settled records in their selected gate statuses,
    use the immutable evaluation-time offered odds for WON returns, use -1 unit
    for LOST and zero for VOID, and include VOID in the ROI denominator while
    excluding it from hit rate. Reference or closing odds are never consulted.
    """

    def __init__(self, repository: ShadowEvaluationRepository) -> None:
        self._repository = repository

    def build(
        self,
        start_at: datetime,
        end_at: datetime,
        policy_version: str,
        generated_at: datetime,
    ) -> ShadowComparisonReport:
        if (
            start_at.tzinfo is None
            or end_at.tzinfo is None
            or generated_at.tzinfo is None
        ):
            raise ValueError("Report timestamps must be timezone-aware.")
        if start_at >= end_at:
            raise ValueError("Report start must be earlier than end.")
        records = self._repository.query(
            start_at,
            end_at,
            policy_version=policy_version,
        )
        errors = self._repository.query_errors(
            start_at,
            end_at,
            policy_version=policy_version,
        )
        by_status = tuple(
            ShadowGateStatusStatistics(
                gate_status=status,
                performance=self._performance(
                    tuple(record for record in records if record.gate_status is status),
                    hypothetical=False,
                ),
            )
            for status in QualityGateStatus
        )
        approved = tuple(
            record
            for record in records
            if record.gate_status is QualityGateStatus.APPROVED
        )
        approved_and_review = tuple(
            record
            for record in records
            if record.gate_status in {
                QualityGateStatus.APPROVED,
                QualityGateStatus.REVIEW_REQUIRED,
            }
        )
        published = tuple(record for record in records if record.actually_published)
        return ShadowComparisonReport(
            policy_version=policy_version,
            start_at=start_at,
            end_at=end_at,
            total_shadow_evaluations=len(records),
            approved_count=self._status_count(records, QualityGateStatus.APPROVED),
            review_required_count=self._status_count(
                records,
                QualityGateStatus.REVIEW_REQUIRED,
            ),
            rejected_count=self._status_count(records, QualityGateStatus.REJECTED),
            actually_published_count=len(published),
            unpublished_count=len(records) - len(published),
            settlement_coverage_count=sum(
                record.settlement_outcome is not None for record in records
            ),
            by_gate_status=by_status,
            hypothetical_approved_only=self._performance(
                approved,
                hypothetical=True,
            ),
            hypothetical_approved_and_review=self._performance(
                approved_and_review,
                hypothetical=True,
            ),
            actual_published_result=self._performance(
                published,
                hypothetical=False,
            ),
            rejection_reasons=self._reason_statistics(
                reason.value
                for record in records
                for reason in record.rejection_reasons
            ),
            review_reasons=self._reason_statistics(
                reason.value
                for record in records
                for reason in record.review_reasons
            ),
            error_count=len(errors),
            generated_at=generated_at,
        )

    @staticmethod
    def _status_count(
        records: tuple[ShadowEvaluationRecord, ...],
        status: QualityGateStatus,
    ) -> int:
        return sum(record.gate_status is status for record in records)

    @staticmethod
    def _performance(
        records: tuple[ShadowEvaluationRecord, ...],
        hypothetical: bool,
    ) -> ShadowPerformanceStatistics:
        settled = tuple(
            record for record in records if record.settlement_outcome is not None
        )
        won = sum(
            record.settlement_outcome is ResolutionStatus.WON for record in settled
        )
        lost = sum(
            record.settlement_outcome is ResolutionStatus.LOST for record in settled
        )
        void = sum(
            record.settlement_outcome is ResolutionStatus.VOID for record in settled
        )
        profit = sum(
            (
                ShadowComparisonReportService._hypothetical_profit(record)
                if hypothetical
                else record.eventual_profit_loss_units or ZERO
            )
            for record in settled
        )
        return ShadowPerformanceStatistics(
            total_records=len(records),
            settled_count=len(settled),
            won_count=won,
            lost_count=lost,
            void_count=void,
            profit_loss_units=profit,
            roi=(profit / Decimal(len(settled)) if settled else None),
            hit_rate=(
                Decimal(won) / Decimal(won + lost)
                if won + lost
                else None
            ),
            hypothetical=hypothetical,
        )

    @staticmethod
    def _hypothetical_profit(record: ShadowEvaluationRecord) -> Decimal:
        if record.settlement_outcome is ResolutionStatus.WON:
            return record.candidate_snapshot.offered_odds - ONE
        if record.settlement_outcome is ResolutionStatus.LOST:
            return -ONE
        return ZERO

    @staticmethod
    def _reason_statistics(
        values: Iterable[str],
    ) -> tuple[ShadowReasonStatistics, ...]:
        counts = Counter(values)
        return tuple(
            ShadowReasonStatistics(reason=reason, count=count)
            for reason, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
