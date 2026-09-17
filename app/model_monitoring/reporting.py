from collections import Counter
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from app.backtesting import (
    BacktestMetricsService,
    EvaluationOutcome,
    HistoricalEvaluationRecord,
)
from app.calibration import (
    CalibrationObservation,
    CalibrationReportService,
    ExplicitBoundaryBinning,
)
from app.results import ResolutionStatus

from .models import (
    DataCompleteness,
    MonitoringObservation,
    MonitoringReport,
    MonitoringSegment,
    MonitoringWindow,
    SafeDecimal,
)


ZERO = Decimal("0")


class MonitoringReportService:
    """Reuses backtesting performance and calibration reliability services."""

    def __init__(self, boundaries: tuple[Decimal, ...] | None = None) -> None:
        self._backtests = BacktestMetricsService()
        self._calibration = CalibrationReportService(
            ExplicitBoundaryBinning(boundaries)
            if boundaries is not None
            else None
        )

    def build(
        self,
        observations: tuple[MonitoringObservation, ...],
        *,
        report_window: MonitoringWindow,
        generated_for: datetime,
    ) -> MonitoringReport:
        ordered = tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.prediction_timestamp,
                    item.prediction_id,
                    item.fixture_id,
                    item.market,
                ),
            )
        )
        settled = tuple(item for item in ordered if item.authoritative_outcome is not None)
        backtests = tuple(self._backtest(item) for item in settled)
        metrics = self._backtests.evaluate(backtests)
        raw_observations = tuple(
            self._calibration_observation(item, item.raw_probability)
            for item in settled
            if item.authoritative_outcome is not ResolutionStatus.VOID
        )
        calibrated_observations = tuple(
            self._calibration_observation(item, item.calibrated_probability)
            for item in settled
            if item.authoritative_outcome is not ResolutionStatus.VOID
            and item.calibrated_probability is not None
        )
        raw = self._calibration.evaluate(raw_observations)
        calibrated = (
            self._calibration.evaluate(calibrated_observations)
            if calibrated_observations
            else None
        )
        return MonitoringReport(
            observation_count=len(ordered),
            settled_count=len(settled),
            unresolved_count=len(ordered) - len(settled),
            won_count=metrics.wins,
            lost_count=metrics.losses,
            void_count=metrics.voids,
            hit_rate=metrics.hit_rate,
            total_profit_units=metrics.total_profit,
            roi=metrics.roi,
            average_odds=metrics.average_odds,
            maximum_drawdown=metrics.maximum_drawdown,
            raw_brier_score=raw.brier_score,
            calibrated_brier_score=calibrated.brier_score if calibrated else None,
            raw_log_loss=SafeDecimal.from_decimal(raw.log_loss),
            calibrated_log_loss=(
                SafeDecimal.from_decimal(calibrated.log_loss) if calibrated else None
            ),
            raw_ece=raw.expected_calibration_error,
            calibrated_ece=(
                calibrated.expected_calibration_error if calibrated else None
            ),
            raw_mce=raw.maximum_calibration_error,
            calibrated_mce=(
                calibrated.maximum_calibration_error if calibrated else None
            ),
            average_clv=metrics.average_clv,
            positive_clv_percentage=metrics.positive_clv_percentage,
            calibration_artifact_usage_counts=tuple(
                sorted(
                    Counter(
                        item.calibration_artifact_id
                        for item in ordered
                        if item.calibration_artifact_id is not None
                    ).items()
                )
            ),
            competition_segments=self._segments(ordered, "competition"),
            market_segments=self._segments(ordered, "market"),
            data_completeness=DataCompleteness(
                len(ordered),
                sum(item.calibrated_probability is not None for item in ordered),
                sum(item.closing_odds is not None for item in ordered),
                len(settled),
            ),
            report_window=report_window,
            generated_for=generated_for,
            raw_calibration_bins=raw.bins,
            calibrated_calibration_bins=calibrated.bins if calibrated else None,
        )

    @staticmethod
    def _backtest(item: MonitoringObservation) -> HistoricalEvaluationRecord:
        outcome = EvaluationOutcome(item.authoritative_outcome.value)
        return HistoricalEvaluationRecord(
            fixture_id=item.fixture_id,
            competition=item.competition,
            kickoff_datetime=item.settlement_timestamp,
            prediction_timestamp=item.prediction_timestamp,
            feature_timestamp=item.prediction_timestamp,
            odds_timestamp=item.prediction_timestamp,
            market=item.market,
            selection=item.prediction_id,
            model_probability=item.raw_probability,
            offered_odds=item.offered_odds,
            closing_odds=item.closing_odds,
            result=item.authoritative_outcome.value,
            outcome=outcome,
            profit_loss=item.profit_loss_units,
        )

    @staticmethod
    def _calibration_observation(
        item: MonitoringObservation, value: Decimal
    ) -> CalibrationObservation:
        return CalibrationObservation(
            observation_id=item.prediction_id,
            fixture_id=item.fixture_id,
            competition=item.competition,
            market=item.market,
            selection=item.prediction_id,
            prediction_timestamp=item.prediction_timestamp,
            outcome_timestamp=item.settlement_timestamp,
            raw_probability=value,
            binary_outcome=(
                1 if item.authoritative_outcome is ResolutionStatus.WON else 0
            ),
            model_version=item.model_version,
        )

    @staticmethod
    def _segments(
        observations: tuple[MonitoringObservation, ...], attribute: str
    ) -> tuple[MonitoringSegment, ...]:
        keys = sorted({getattr(item, attribute) for item in observations})
        return tuple(
            MonitoringSegment(
                key,
                sum(getattr(item, attribute) == key for item in observations),
                sum(
                    getattr(item, attribute) == key
                    and item.authoritative_outcome is not None
                    for item in observations
                ),
                sum(
                    (
                        item.profit_loss_units or ZERO
                        for item in observations
                        if getattr(item, attribute) == key
                    ),
                    ZERO,
                ),
            )
            for key in keys
        )
