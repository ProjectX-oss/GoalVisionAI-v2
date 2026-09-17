from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.calibration import CalibrationBinReport, CalibrationObservation
from app.calibration.models import validate_aware, validate_probability

from .config import CalibrationMethod


@dataclass(frozen=True, slots=True)
class ProbabilityCalibrationRequest:
    """One post-prediction calibration request with settled training history."""

    calibration_run_id: str
    raw_probability: Decimal
    historical_data: tuple[CalibrationObservation, ...]
    timestamp: datetime
    model_version: str

    def __post_init__(self) -> None:
        if not self.calibration_run_id.strip():
            raise ValueError("Calibration run ID must not be empty.")
        validate_probability(self.raw_probability, "Raw probability")
        validate_aware(self.timestamp, "Calibration timestamp")
        if not self.model_version.strip():
            raise ValueError("Model version must not be empty.")
        identifiers = tuple(item.observation_id for item in self.historical_data)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Historical calibration observation IDs must be unique.")
        for observation in self.historical_data:
            if observation.outcome_timestamp >= self.timestamp:
                raise ValueError(
                    "Historical calibration outcomes must predate calibration."
                )
            if observation.model_version != self.model_version:
                raise ValueError(
                    "Historical calibration data must match the requested model version."
                )


@dataclass(frozen=True, slots=True)
class ConfidenceHistogramBin:
    """One immutable calibrated-confidence distribution bucket."""

    index: int
    lower_bound: Decimal
    upper_bound: Decimal
    includes_upper_bound: bool
    observation_count: int
    observation_fraction: Decimal


@dataclass(frozen=True, slots=True)
class CalibrationMetricSummary:
    """Deterministic metrics calculated over the calibrated history."""

    observation_count: int
    brier_score: Decimal
    log_loss: Decimal
    expected_calibration_error: Decimal
    maximum_calibration_error: Decimal
    reliability_bins: tuple[CalibrationBinReport, ...]


@dataclass(frozen=True, slots=True)
class ProbabilityCalibrationReport:
    """Immutable audit record for one calibrated model probability."""

    calibration_run_id: str
    raw_probability: Decimal
    calibrated_probability: Decimal
    delta: Decimal
    calibration_method: CalibrationMethod
    metric_summary: CalibrationMetricSummary
    confidence_histogram: tuple[ConfidenceHistogramBin, ...]
    timestamp: datetime
    model_version: str
    calibration_version: str

    def __post_init__(self) -> None:
        if not self.calibration_run_id.strip():
            raise ValueError("Calibration run ID must not be empty.")
        validate_probability(self.raw_probability, "Raw probability")
        validate_probability(self.calibrated_probability, "Calibrated probability")
        if self.delta != self.calibrated_probability - self.raw_probability:
            raise ValueError("Calibration delta must equal calibrated minus raw probability.")
        if not isinstance(self.calibration_method, CalibrationMethod):
            raise TypeError("Calibration method must be a CalibrationMethod.")
        validate_aware(self.timestamp, "Calibration timestamp")
        if not self.model_version.strip() or not self.calibration_version.strip():
            raise ValueError("Model and calibration versions must not be empty.")
