from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Sequence

from .calibrators import (
    CalibrationFitRequest,
    CalibrationFittingError,
    IdentityCalibrator,
    IsotonicCalibrator,
    PlattCalibrator,
)
from .models import CalibrationObservation, CalibrationReport
from .report import CalibrationReportService


class CalibrationSelectionMetric(str, Enum):
    BRIER_SCORE = "BRIER_SCORE"
    LOG_LOSS = "LOG_LOSS"
    EXPECTED_CALIBRATION_ERROR = "EXPECTED_CALIBRATION_ERROR"


@dataclass(frozen=True, slots=True)
class CalibrationSelectionPolicy:
    primary_metric: CalibrationSelectionMetric = CalibrationSelectionMetric.BRIER_SCORE
    tie_tolerance: Decimal = Decimal("0.000000001")
    method_order: tuple[str, ...] = ("identity", "platt", "isotonic")

    def __post_init__(self) -> None:
        if self.tie_tolerance < 0 or not self.tie_tolerance.is_finite():
            raise ValueError("Selection tie tolerance must be finite and non-negative.")
        if self.method_order != ("identity", "platt", "isotonic"):
            raise ValueError("Conservative method tie order is fixed.")


@dataclass(frozen=True, slots=True)
class SafeMetricValue:
    finite_value: Decimal | None
    is_positive_infinity: bool = False

    @classmethod
    def from_decimal(cls, value: Decimal) -> "SafeMetricValue":
        if value == Decimal("Infinity"):
            return cls(None, True)
        if not value.is_finite():
            raise ValueError("Only positive infinite Log Loss is supported.")
        return cls(value, False)


@dataclass(frozen=True, slots=True)
class CalibrationMethodEvaluation:
    method: str
    fitted: bool
    eligible: bool
    selected: bool
    reason: str | None
    fit_version: str | None
    scope: object | None
    training_count: int
    validation_count: int
    converged: bool
    brier_score: Decimal | None
    log_loss: SafeMetricValue | None
    expected_calibration_error: Decimal | None
    maximum_calibration_error: Decimal | None
    brier_improvement_vs_raw: Decimal | None


@dataclass(frozen=True, slots=True)
class CalibrationMethodSelection:
    selected_calibrator: object
    selected_method: str
    raw_report: CalibrationReport
    evaluations: tuple[CalibrationMethodEvaluation, ...]


class CalibrationMethodSelectionService:
    def __init__(
        self,
        reports: CalibrationReportService | None = None,
        policy: CalibrationSelectionPolicy | None = None,
    ) -> None:
        self._reports = reports or CalibrationReportService()
        self._policy = policy or CalibrationSelectionPolicy()

    def select(
        self,
        training: Sequence[CalibrationObservation],
        validation: Sequence[CalibrationObservation],
        request: CalibrationFitRequest,
        platt: PlattCalibrator,
        isotonic: IsotonicCalibrator,
    ) -> CalibrationMethodSelection:
        if not validation:
            raise ValueError("A separate validation window is required.")
        if max(item.outcome_timestamp for item in training) >= min(
            item.prediction_timestamp for item in validation
        ):
            raise ValueError("Training outcomes must precede validation predictions.")
        raw = self._reports.evaluate(validation)
        candidates: list[tuple[str, object, CalibrationReport]] = []
        failures: dict[str, str] = {}
        identity = IdentityCalibrator.fit(training, request)
        candidates.append(("identity", identity, raw))
        for name, trainer in (("platt", platt), ("isotonic", isotonic)):
            try:
                fitted = trainer.fit(training, request)
                calibrated = tuple(
                    replace(item, raw_probability=fitted.calibrate(item.raw_probability))
                    for item in validation
                )
                candidates.append((name, fitted, self._reports.evaluate(calibrated)))
            except CalibrationFittingError as exc:
                failures[name] = str(exc)
        best_metric = min(self._metric(item[2]) for item in candidates)
        tied = tuple(
            item for item in candidates
            if self._within_tolerance(self._metric(item[2]), best_metric)
        )
        selected = min(
            tied,
            key=lambda item: self._policy.method_order.index(item[0]),
        )
        evaluations = []
        for method in self._policy.method_order:
            candidate = next((item for item in candidates if item[0] == method), None)
            if candidate is None:
                evaluations.append(CalibrationMethodEvaluation(
                    method, False, False, False, failures.get(method, "Not fitted."),
                    None, None, len(training), len(validation), False,
                    None, None, None, None, None,
                ))
                continue
            _, calibrator, report = candidate
            evaluations.append(CalibrationMethodEvaluation(
                method, True, True, method == selected[0],
                None if method == selected[0] else "Not selected by validation metric.",
                calibrator.metadata.version, calibrator.metadata.scope,
                len(training), len(validation),
                getattr(getattr(calibrator, "diagnostics", None), "converged", True),
                report.brier_score, SafeMetricValue.from_decimal(report.log_loss),
                report.expected_calibration_error, report.maximum_calibration_error,
                raw.brier_score - report.brier_score,
            ))
        return CalibrationMethodSelection(
            selected[1], selected[0], raw, tuple(evaluations)
        )

    def _metric(self, report: CalibrationReport) -> Decimal:
        return {
            CalibrationSelectionMetric.BRIER_SCORE: report.brier_score,
            CalibrationSelectionMetric.LOG_LOSS: report.log_loss,
            CalibrationSelectionMetric.EXPECTED_CALIBRATION_ERROR: (
                report.expected_calibration_error
            ),
        }[self._policy.primary_metric]

    def _within_tolerance(self, value: Decimal, best: Decimal) -> bool:
        if value.is_infinite() or best.is_infinite():
            return value == best
        return value - best <= self._policy.tie_tolerance
