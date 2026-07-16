from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.results import ResolutionStatus


def aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")


def probability(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= 1:
        raise ValueError(f"{label} must be a finite Decimal in [0, 1].")


@dataclass(frozen=True, slots=True)
class MonitoringObservation:
    prediction_id: str
    fixture_id: int
    competition: str
    market: str
    model_version: str
    calibration_artifact_id: str | None
    prediction_timestamp: datetime
    raw_probability: Decimal
    calibrated_probability: Decimal | None
    offered_odds: Decimal
    closing_odds: Decimal | None
    authoritative_outcome: ResolutionStatus | None
    profit_loss_units: Decimal | None
    settlement_timestamp: datetime | None
    source: str
    source_stage: str | None = None
    actually_published: bool | None = None
    gate_status: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.prediction_id,
            self.competition,
            self.market,
            self.model_version,
            self.source,
        ):
            if not value.strip():
                raise ValueError("Monitoring identity values must not be empty.")
        if self.fixture_id <= 0:
            raise ValueError("Monitoring fixture ID must be positive.")
        aware(self.prediction_timestamp, "Prediction timestamp")
        probability(self.raw_probability, "Raw probability")
        if self.calibrated_probability is not None:
            probability(self.calibrated_probability, "Calibrated probability")
        for value, label in (
            (self.offered_odds, "Offered odds"),
            (self.closing_odds, "Closing odds"),
        ):
            if value is not None and (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or value <= Decimal("1")
            ):
                raise ValueError(f"{label} must be a finite Decimal greater than one.")
        settled = self.authoritative_outcome is not None
        if settled != (
            self.profit_loss_units is not None and self.settlement_timestamp is not None
        ):
            raise ValueError("Settlement monitoring facts must be complete.")
        if settled and self.authoritative_outcome not in {
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        }:
            raise ValueError("Monitoring outcome must be terminal.")
        if self.settlement_timestamp is not None:
            aware(self.settlement_timestamp, "Settlement timestamp")
            if self.settlement_timestamp < self.prediction_timestamp:
                raise ValueError("Settlement must not predate prediction.")
        if self.profit_loss_units is not None and not self.profit_loss_units.is_finite():
            raise ValueError("Profit/loss units must be finite.")

    @property
    def deduplication_identity(self) -> tuple[str, int, str]:
        return (self.prediction_id, self.fixture_id, self.market)


class MonitoringWindowKind(str, Enum):
    FIXED_COUNT = "FIXED_COUNT"
    FIXED_INTERVAL = "FIXED_INTERVAL"
    ROLLING_COUNT = "ROLLING_COUNT"
    ROLLING_INTERVAL = "ROLLING_INTERVAL"
    EXPLICIT_RANGE = "EXPLICIT_RANGE"


@dataclass(frozen=True, slots=True)
class MonitoringWindow:
    kind: MonitoringWindowKind
    start_at: datetime
    end_at: datetime
    observation_limit: int | None = None

    def __post_init__(self) -> None:
        aware(self.start_at, "Window start")
        aware(self.end_at, "Window end")
        if self.start_at >= self.end_at:
            raise ValueError("Monitoring window start must be before end.")
        if self.observation_limit is not None and self.observation_limit <= 0:
            raise ValueError("Observation limit must be positive.")


@dataclass(frozen=True, slots=True)
class SafeDecimal:
    finite_value: Decimal | None
    is_positive_infinity: bool = False

    @classmethod
    def from_decimal(cls, value: Decimal) -> "SafeDecimal":
        if value == Decimal("Infinity"):
            return cls(None, True)
        if not value.is_finite():
            raise ValueError("Only positive infinity can be represented.")
        return cls(value, False)


@dataclass(frozen=True, slots=True)
class MonitoringSegment:
    key: str
    observation_count: int
    settled_count: int
    profit_loss_units: Decimal


@dataclass(frozen=True, slots=True)
class DataCompleteness:
    total_observations: int
    calibrated_probability_count: int
    closing_odds_count: int
    settlement_count: int

    @property
    def settlement_fraction(self) -> Decimal:
        return (
            Decimal(self.settlement_count) / Decimal(self.total_observations)
            if self.total_observations
            else Decimal("0")
        )


@dataclass(frozen=True, slots=True)
class MonitoringReport:
    observation_count: int
    settled_count: int
    unresolved_count: int
    won_count: int
    lost_count: int
    void_count: int
    hit_rate: Decimal
    total_profit_units: Decimal
    roi: Decimal
    average_odds: Decimal
    maximum_drawdown: Decimal
    raw_brier_score: Decimal
    calibrated_brier_score: Decimal | None
    raw_log_loss: SafeDecimal
    calibrated_log_loss: SafeDecimal | None
    raw_ece: Decimal
    calibrated_ece: Decimal | None
    raw_mce: Decimal
    calibrated_mce: Decimal | None
    average_clv: Decimal | None
    positive_clv_percentage: Decimal | None
    calibration_artifact_usage_counts: tuple[tuple[str, int], ...]
    competition_segments: tuple[MonitoringSegment, ...]
    market_segments: tuple[MonitoringSegment, ...]
    data_completeness: DataCompleteness
    report_window: MonitoringWindow
    generated_for: datetime
    raw_calibration_bins: tuple[object, ...]
    calibrated_calibration_bins: tuple[object, ...] | None

    def __post_init__(self) -> None:
        aware(self.generated_for, "Generated-for timestamp")


class DriftFindingType(str, Enum):
    BRIER_DEGRADATION = "BRIER_DEGRADATION"
    LOG_LOSS_DEGRADATION = "LOG_LOSS_DEGRADATION"
    ECE_DEGRADATION = "ECE_DEGRADATION"
    ROI_DEGRADATION = "ROI_DEGRADATION"
    CLV_DEGRADATION = "CLV_DEGRADATION"
    HIT_RATE_DEGRADATION = "HIT_RATE_DEGRADATION"
    DRAWDOWN_INCREASE = "DRAWDOWN_INCREASE"
    CLASS_BALANCE_SHIFT = "CLASS_BALANCE_SHIFT"
    PROBABILITY_DISTRIBUTION_SHIFT = "PROBABILITY_DISTRIBUTION_SHIFT"
    CALIBRATION_BIN_DRIFT = "CALIBRATION_BIN_DRIFT"
    DATA_COMPLETENESS_DEGRADATION = "DATA_COMPLETENESS_DEGRADATION"
    SAMPLE_TOO_SMALL = "SAMPLE_TOO_SMALL"
    ARTIFACT_PERFORMANCE_DEGRADATION = "ARTIFACT_PERFORMANCE_DEGRADATION"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ThresholdComparison(str, Enum):
    ABSOLUTE = "ABSOLUTE"
    RELATIVE = "RELATIVE"


@dataclass(frozen=True, slots=True)
class MetricDriftThreshold:
    enabled: bool
    warning: Decimal
    critical: Decimal
    comparison: ThresholdComparison = ThresholdComparison.ABSOLUTE

    def __post_init__(self) -> None:
        if (
            not self.warning.is_finite()
            or not self.critical.is_finite()
            or self.warning < 0
            or self.critical < self.warning
        ):
            raise ValueError("Drift thresholds must be finite and ordered.")


@dataclass(frozen=True, slots=True)
class MonitoringPolicy:
    version: str = "model-monitoring-v1"
    minimum_observations: int = 30
    minimum_settled_observations: int = 20
    probability_bins: tuple[Decimal, ...] = (
        Decimal("0"),
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("0.3"),
        Decimal("0.4"),
        Decimal("0.5"),
        Decimal("0.6"),
        Decimal("0.7"),
        Decimal("0.8"),
        Decimal("0.9"),
        Decimal("1"),
    )
    psi_smoothing: Decimal = Decimal("0.000001")
    allow_window_overlap: bool = False
    thresholds: tuple[tuple[str, MetricDriftThreshold], ...] = ()
    competition_overrides: tuple[tuple[str, tuple[tuple[str, MetricDriftThreshold], ...]], ...] = ()
    market_overrides: tuple[tuple[str, tuple[tuple[str, MetricDriftThreshold], ...]], ...] = ()
    artifact_overrides: tuple[tuple[str, tuple[tuple[str, MetricDriftThreshold], ...]], ...] = ()

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Monitoring policy version must not be empty.")
        if self.minimum_observations <= 0 or self.minimum_settled_observations <= 0:
            raise ValueError("Monitoring minimums must be positive.")
        if not 0 < self.psi_smoothing < 1:
            raise ValueError("PSI smoothing must be in (0, 1).")
        if (
            len(self.probability_bins) < 2
            or self.probability_bins[0] != Decimal("0")
            or self.probability_bins[-1] != Decimal("1")
            or any(
                not value.is_finite() or not Decimal("0") <= value <= Decimal("1")
                for value in self.probability_bins
            )
            or any(
                left >= right
                for left, right in zip(
                    self.probability_bins, self.probability_bins[1:]
                )
            )
        ):
            raise ValueError(
                "Probability drift bins must increase strictly from 0 to 1."
            )


@dataclass(frozen=True, slots=True)
class DriftFinding:
    finding_type: DriftFindingType
    metric: str
    baseline_value: SafeDecimal | None
    current_value: SafeDecimal | None
    absolute_change: SafeDecimal | None
    relative_change: SafeDecimal | None
    configured_threshold: Decimal | None
    severity: AlertSeverity
    baseline_sample_count: int
    current_sample_count: int
    scope: str
    reason_code: str


class MonitoringRunStatus(str, Enum):
    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class MonitoringRun:
    run_id: str
    policy_version: str
    baseline_window: MonitoringWindow
    current_window: MonitoringWindow
    scope: str
    artifact_id: str | None
    started_at: datetime
    completed_at: datetime
    baseline_observation_count: int
    current_observation_count: int
    report_snapshot: tuple[tuple[str, object], ...]
    findings: tuple[DriftFinding, ...]
    status: MonitoringRunStatus
    safe_error_type: str | None = None
    safe_error_message: str | None = None

    def __post_init__(self) -> None:
        aware(self.started_at, "Monitoring-run start")
        aware(self.completed_at, "Monitoring-run completion")
        if self.completed_at < self.started_at:
            raise ValueError("Monitoring run cannot complete before it starts.")
        if not self.run_id.strip() or not self.policy_version.strip() or not self.scope.strip():
            raise ValueError("Monitoring-run identity values must not be empty.")
        object.__setattr__(
            self,
            "report_snapshot",
            tuple(sorted(self.report_snapshot, key=lambda item: item[0])),
        )


@dataclass(frozen=True, slots=True)
class MonitoringAlert:
    alert_id: str
    run_id: str
    scope: str
    finding_type: DriftFindingType
    metric: str
    threshold_version: str
    severity: AlertSeverity
    reason_code: str
    created_at: datetime
    finding: DriftFinding


class MonitoringError(RuntimeError):
    pass
