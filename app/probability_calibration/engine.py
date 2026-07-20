from dataclasses import replace
from decimal import Decimal, localcontext

from app.calibration import (
    CalibrationFitRequest,
    CalibrationObservation,
    CalibrationReportService,
    CalibrationScope,
    CalibrationTrainingWindow,
    EqualWidthBinning,
    FittedProbabilityCalibrator,
    IdentityCalibrator,
    IsotonicCalibrator,
    PlattCalibrator,
)

from .config import CalibrationMethod, ProbabilityCalibrationConfig
from .models import (
    CalibrationMetricSummary,
    ConfidenceHistogramBin,
    ProbabilityCalibrationReport,
    ProbabilityCalibrationRequest,
)


class ProbabilityOrderingError(ValueError):
    """Raised when a fitted transform would reverse probability ordering."""


class ProbabilityCalibrationEngine:
    """Fits and applies an isolated deterministic probability transform."""

    def __init__(self, config: ProbabilityCalibrationConfig | None = None) -> None:
        self.config = config or ProbabilityCalibrationConfig()

    def calibrate(
        self,
        request: ProbabilityCalibrationRequest,
    ) -> ProbabilityCalibrationReport:
        observations = tuple(
            sorted(
                request.historical_data,
                key=lambda item: (
                    item.prediction_timestamp,
                    item.observation_id,
                    item.fixture_id,
                ),
            )
        )
        calibrator = self._fit(request, observations)
        self._validate_ordering(calibrator, observations)
        calibrated_probability = self._clamp(
            calibrator.calibrate(request.raw_probability)
        )
        calibrated_history = tuple(
            replace(
                item,
                raw_probability=self._clamp(
                    calibrator.calibrate(item.raw_probability)
                ),
            )
            for item in observations
        )
        metrics = CalibrationReportService(
            EqualWidthBinning(self.config.reliability_bin_count)
        ).evaluate(calibrated_history)
        summary = CalibrationMetricSummary(
            observation_count=metrics.total_observations,
            brier_score=metrics.brier_score,
            log_loss=metrics.log_loss,
            expected_calibration_error=metrics.expected_calibration_error,
            maximum_calibration_error=metrics.maximum_calibration_error,
            reliability_bins=metrics.bins,
        )
        return ProbabilityCalibrationReport(
            calibration_run_id=request.calibration_run_id,
            raw_probability=request.raw_probability,
            calibrated_probability=calibrated_probability,
            delta=calibrated_probability - request.raw_probability,
            calibration_method=self.config.method,
            metric_summary=summary,
            confidence_histogram=self._histogram(calibrated_history),
            timestamp=request.timestamp,
            model_version=request.model_version,
            calibration_version=self.config.calibration_version,
        )

    def _fit(
        self,
        request: ProbabilityCalibrationRequest,
        observations: tuple[CalibrationObservation, ...],
    ) -> FittedProbabilityCalibrator:
        if not observations:
            if self.config.method is CalibrationMethod.IDENTITY:
                return IdentityCalibrator.fallback(
                    request.timestamp,
                    self.config.calibration_version,
                )
            raise ValueError("Historical calibration data is required for fitted methods.")

        training_window = CalibrationTrainingWindow(
            start=min(item.prediction_timestamp for item in observations),
            end=max(item.outcome_timestamp for item in observations),
        )
        fit_request = CalibrationFitRequest(
            fitted_at=request.timestamp,
            training_window=training_window,
            scope=CalibrationScope.global_scope(),
            version=self.config.calibration_version,
            target_prediction_timestamp=request.timestamp,
            model_version=request.model_version,
        )
        if self.config.method is CalibrationMethod.IDENTITY:
            return IdentityCalibrator.fit(observations, fit_request)
        if self.config.method is CalibrationMethod.PLATT:
            return PlattCalibrator(
                config=self.config.platt,
                policy=self.config.fitting_policy,
            ).fit(observations, fit_request)
        return IsotonicCalibrator(
            config=self.config.isotonic,
            policy=self.config.fitting_policy,
        ).fit(observations, fit_request)

    def _clamp(self, probability: Decimal) -> Decimal:
        return min(
            self.config.maximum_probability,
            max(self.config.minimum_probability, probability),
        )

    def _validate_ordering(
        self,
        calibrator: FittedProbabilityCalibrator,
        observations: tuple[CalibrationObservation, ...],
    ) -> None:
        inputs = tuple(
            sorted(
                {
                    Decimal("0"),
                    Decimal("1"),
                    *(item.raw_probability for item in observations),
                }
            )
        )
        outputs = tuple(self._clamp(calibrator.calibrate(value)) for value in inputs)
        if any(left > right for left, right in zip(outputs, outputs[1:])):
            raise ProbabilityOrderingError(
                "Calibrator output must preserve raw probability ordering."
            )

    def _histogram(
        self,
        observations: tuple[CalibrationObservation, ...],
    ) -> tuple[ConfidenceHistogramBin, ...]:
        boundaries = EqualWidthBinning(
            self.config.confidence_bin_count
        ).boundaries
        counts = [0 for _ in range(self.config.confidence_bin_count)]
        for observation in observations:
            for index, upper in enumerate(boundaries[1:]):
                if (
                    observation.raw_probability < upper
                    or index == len(counts) - 1
                ):
                    counts[index] += 1
                    break
        total = len(observations)
        with localcontext() as context:
            context.prec = 50
            return tuple(
                ConfidenceHistogramBin(
                    index=index,
                    lower_bound=boundaries[index],
                    upper_bound=boundaries[index + 1],
                    includes_upper_bound=(index == len(counts) - 1),
                    observation_count=count,
                    observation_fraction=(
                        Decimal(count) / Decimal(total) if total else Decimal("0")
                    ),
                )
                for index, count in enumerate(counts)
            )
