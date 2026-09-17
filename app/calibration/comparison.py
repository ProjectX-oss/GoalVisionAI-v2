from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Sequence

from .calibrators import FittedProbabilityCalibrator
from .models import CalibrationObservation, CalibrationScope
from .report import CalibrationReportService


@dataclass(frozen=True, slots=True)
class CalibrationMetricComparison:
    raw_brier_score: Decimal
    calibrated_brier_score: Decimal
    brier_improvement: Decimal
    brier_improved: bool
    raw_log_loss: Decimal
    calibrated_log_loss: Decimal
    log_loss_improvement: Decimal
    log_loss_improved: bool
    raw_expected_calibration_error: Decimal
    calibrated_expected_calibration_error: Decimal
    calibration_method: str
    scope_used: CalibrationScope
    observation_count: int


class CalibrationComparisonService:
    def __init__(self, reports: CalibrationReportService) -> None:
        self._reports = reports

    def compare(
        self,
        observations: Sequence[CalibrationObservation],
        calibrator: FittedProbabilityCalibrator,
        scope_used: CalibrationScope,
    ) -> CalibrationMetricComparison:
        ordered = tuple(sorted(
            observations,
            key=lambda item: (
                item.prediction_timestamp,
                item.observation_id,
                item.fixture_id,
            ),
        ))
        calibrated = tuple(
            replace(
                observation,
                raw_probability=calibrator.calibrate(
                    observation.raw_probability
                ),
            )
            for observation in ordered
        )
        raw_report = self._reports.evaluate(ordered)
        calibrated_report = self._reports.evaluate(calibrated)
        brier_improvement = _improvement(
            raw_report.brier_score,
            calibrated_report.brier_score,
        )
        log_improvement = _improvement(
            raw_report.log_loss,
            calibrated_report.log_loss,
        )
        return CalibrationMetricComparison(
            raw_brier_score=raw_report.brier_score,
            calibrated_brier_score=calibrated_report.brier_score,
            brier_improvement=brier_improvement,
            brier_improved=(brier_improvement > 0),
            raw_log_loss=raw_report.log_loss,
            calibrated_log_loss=calibrated_report.log_loss,
            log_loss_improvement=log_improvement,
            log_loss_improved=(log_improvement > 0),
            raw_expected_calibration_error=raw_report.expected_calibration_error,
            calibrated_expected_calibration_error=(
                calibrated_report.expected_calibration_error
            ),
            calibration_method=calibrator.metadata.method_name,
            scope_used=scope_used,
            observation_count=len(ordered),
        )


def _improvement(raw: Decimal, calibrated: Decimal) -> Decimal:
    if raw == calibrated:
        return Decimal("0")
    if raw.is_infinite():
        return Decimal("Infinity")
    if calibrated.is_infinite():
        return Decimal("-Infinity")
    return raw - calibrated
