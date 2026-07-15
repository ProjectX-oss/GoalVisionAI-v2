from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.backtesting import EvaluationOutcome, HistoricalEvaluationRecord


ZERO = Decimal("0")
ONE = Decimal("1")


def validate_probability(value: Decimal, name: str = "Probability") -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal.")
    if not value.is_finite() or not ZERO <= value <= ONE:
        raise ValueError(f"{name} must be finite and between 0 and 1.")


def validate_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    """A settled binary outcome; void outcomes are intentionally unrepresentable."""

    observation_id: str
    fixture_id: int
    competition: str
    market: str
    selection: str
    prediction_timestamp: datetime
    outcome_timestamp: datetime
    raw_probability: Decimal
    binary_outcome: int
    model_version: str | None = None
    odds_band: str | None = None
    confidence_band: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("Observation ID", self.observation_id),
            ("Competition", self.competition),
            ("Market", self.market),
            ("Selection", self.selection),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty.")
        if self.fixture_id <= 0:
            raise ValueError("Fixture ID must be positive.")
        validate_aware(self.prediction_timestamp, "Prediction timestamp")
        validate_aware(self.outcome_timestamp, "Outcome timestamp")
        if self.outcome_timestamp < self.prediction_timestamp:
            raise ValueError("Outcome timestamp must not predate the prediction.")
        validate_probability(self.raw_probability, "Raw probability")
        if type(self.binary_outcome) is not int or self.binary_outcome not in (0, 1):
            raise ValueError("Binary outcome must be exactly 0 or 1; void is invalid.")
        for name, value in (
            ("Model version", self.model_version),
            ("Odds band", self.odds_band),
            ("Confidence band", self.confidence_band),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{name} must not be empty when provided.")

    @classmethod
    def from_backtest_record(
        cls,
        observation_id: str,
        record: HistoricalEvaluationRecord,
        outcome_timestamp: datetime,
        *,
        model_version: str | None = None,
        odds_band: str | None = None,
        confidence_band: str | None = None,
    ) -> "CalibrationObservation":
        """Converts decided backtests and explicitly rejects void records."""

        if record.outcome is EvaluationOutcome.VOID:
            raise ValueError("Void backtest records cannot become calibration outcomes.")
        return cls(
            observation_id=observation_id,
            fixture_id=record.fixture_id,
            competition=record.competition,
            market=record.market,
            selection=record.selection,
            prediction_timestamp=record.prediction_timestamp,
            outcome_timestamp=outcome_timestamp,
            raw_probability=record.model_probability,
            binary_outcome=(1 if record.outcome is EvaluationOutcome.WON else 0),
            model_version=model_version,
            odds_band=odds_band,
            confidence_band=confidence_band,
        )


class CalibrationScopeKind(str, Enum):
    GLOBAL = "GLOBAL"
    COMPETITION = "COMPETITION"
    MARKET = "MARKET"
    COMPETITION_MARKET = "COMPETITION_MARKET"
    ODDS_BAND = "ODDS_BAND"
    IDENTITY = "IDENTITY"


@dataclass(frozen=True, slots=True)
class CalibrationScope:
    kind: CalibrationScopeKind
    competition: str | None = None
    market: str | None = None
    odds_band: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CalibrationScopeKind):
            raise TypeError("Scope kind must be a CalibrationScopeKind.")
        provided = {
            "competition": self.competition,
            "market": self.market,
            "odds_band": self.odds_band,
        }
        for name, value in provided.items():
            if value is not None and not value.strip():
                raise ValueError(f"Scope {name} must not be empty.")
        required = {
            CalibrationScopeKind.GLOBAL: set(),
            CalibrationScopeKind.COMPETITION: {"competition"},
            CalibrationScopeKind.MARKET: {"market"},
            CalibrationScopeKind.COMPETITION_MARKET: {"competition", "market"},
            CalibrationScopeKind.ODDS_BAND: {"odds_band"},
            CalibrationScopeKind.IDENTITY: set(),
        }[self.kind]
        actual = {name for name, value in provided.items() if value is not None}
        if actual != required:
            raise ValueError(
                f"{self.kind.value} scope requires exactly {sorted(required)}."
            )

    @classmethod
    def global_scope(cls) -> "CalibrationScope":
        return cls(CalibrationScopeKind.GLOBAL)

    @classmethod
    def identity_scope(cls) -> "CalibrationScope":
        return cls(CalibrationScopeKind.IDENTITY)


@dataclass(frozen=True, slots=True)
class CalibrationTrainingWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        validate_aware(self.start, "Training start")
        validate_aware(self.end, "Training end")
        if self.start > self.end:
            raise ValueError("Training start must not be after training end.")


@dataclass(frozen=True, slots=True)
class CalibrationFitMetadata:
    fitted_at: datetime
    training_window: CalibrationTrainingWindow
    observation_count: int
    scope: CalibrationScope
    method_name: str
    version: str
    model_version: str | None = None

    def __post_init__(self) -> None:
        validate_aware(self.fitted_at, "Fitted timestamp")
        if self.fitted_at < self.training_window.end:
            raise ValueError("Fitted timestamp must not predate the training window.")
        if self.observation_count < 0:
            raise ValueError("Observation count must not be negative.")
        if not self.method_name.strip():
            raise ValueError("Method name must not be empty.")
        if not self.version.strip():
            raise ValueError("Version must not be empty.")
        if self.model_version is not None and not self.model_version.strip():
            raise ValueError("Model version must not be empty when provided.")


@dataclass(frozen=True, slots=True)
class CalibrationBinReport:
    index: int
    lower_bound: Decimal
    upper_bound: Decimal
    includes_upper_bound: bool
    observation_count: int
    mean_predicted_probability: Decimal | None
    observed_success_rate: Decimal | None
    calibration_gap: Decimal | None


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Deterministic binary calibration metrics.

    Brier Score is ``mean((p-y)^2)``. Log Loss is
    ``mean(-log(p))`` for successes and ``mean(-log(1-p))`` for failures.
    ECE is the observation-weighted mean absolute per-bin gap; MCE is the
    largest absolute non-empty-bin gap. Empty bins are retained with ``None``
    statistics and contribute zero weight.
    """

    total_observations: int
    mean_predicted_probability: Decimal
    observed_success_rate: Decimal
    brier_score: Decimal
    log_loss: Decimal
    expected_calibration_error: Decimal
    maximum_calibration_error: Decimal
    bins: tuple[CalibrationBinReport, ...]
