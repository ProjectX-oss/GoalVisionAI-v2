from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.calibration import CalibrationScope


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")


class CalibrationArtifactStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    SHADOW = "SHADOW"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class CalibrationArtifactIdentity:
    artifact_id: str
    method: str
    method_version: str
    configuration_fingerprint: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.artifact_id,
                self.method,
                self.method_version,
                self.configuration_fingerprint,
            )
        ):
            raise ValueError("Calibration artifact identity values must not be empty.")


@dataclass(frozen=True, slots=True)
class CalibrationArtifactMetadata:
    created_at: datetime
    fitted_at: datetime
    training_window_start: datetime
    training_window_end: datetime
    training_cutoff: datetime
    observation_count: int
    positive_count: int
    negative_count: int
    competition_scope: str | None
    market_scope: str | None
    odds_band_scope: str | None
    model_version_scope: str | None
    calibration_scope: CalibrationScope
    fit_version: str
    parent_artifact_id: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.created_at, "Created timestamp"),
            (self.fitted_at, "Fitted timestamp"),
            (self.training_window_start, "Training-window start"),
            (self.training_window_end, "Training-window end"),
            (self.training_cutoff, "Training cutoff"),
        ):
            _aware(value, label)
        if self.training_window_start > self.training_window_end:
            raise ValueError("Training window start must not be after its end.")
        if self.training_cutoff != self.training_window_end:
            raise ValueError("Training cutoff must equal the training window end.")
        if self.fitted_at < self.training_cutoff or self.created_at < self.fitted_at:
            raise ValueError("Artifact timestamps are chronologically invalid.")
        if min(self.observation_count, self.positive_count, self.negative_count) < 0:
            raise ValueError("Artifact sample counts must not be negative.")
        if self.positive_count + self.negative_count != self.observation_count:
            raise ValueError("Artifact class counts must match observation count.")
        if not self.fit_version.strip():
            raise ValueError("Fit version must not be empty.")
        for value in (
            self.competition_scope,
            self.market_scope,
            self.odds_band_scope,
            self.model_version_scope,
            self.parent_artifact_id,
        ):
            if value is not None and not value.strip():
                raise ValueError("Optional artifact metadata strings must not be empty.")


@dataclass(frozen=True, slots=True)
class ArtifactMetricSnapshot:
    brier_score: Decimal
    log_loss: Decimal | None
    log_loss_is_infinite: bool
    expected_calibration_error: Decimal
    maximum_calibration_error: Decimal

    def __post_init__(self) -> None:
        for value in (
            self.brier_score,
            self.expected_calibration_error,
            self.maximum_calibration_error,
        ):
            if not value.is_finite():
                raise ValueError("Finite artifact metrics are required.")
        if self.log_loss_is_infinite != (self.log_loss is None):
            raise ValueError("Log Loss infinity representation is inconsistent.")
        if self.log_loss is not None and not self.log_loss.is_finite():
            raise ValueError("Log Loss must be finite or explicitly infinite.")


@dataclass(frozen=True, slots=True)
class CalibrationArtifact:
    identity: CalibrationArtifactIdentity
    serialized_calibrator: str
    metadata: CalibrationArtifactMetadata
    fitting_diagnostics: tuple[tuple[str, str | bool | int], ...]
    training_metrics: ArtifactMetricSnapshot
    validation_metrics: ArtifactMetricSnapshot | None
    status: CalibrationArtifactStatus
    status_reason: str

    def __post_init__(self) -> None:
        if not self.serialized_calibrator.strip():
            raise ValueError("Serialized calibrator must not be empty.")
        if not self.status_reason.strip():
            raise ValueError("Artifact status reason must not be empty.")

    @property
    def artifact_id(self) -> str:
        return self.identity.artifact_id


CalibrationRegistryEntry = CalibrationArtifact


@dataclass(frozen=True, slots=True)
class CalibrationRegistryQuery:
    method: str | None = None
    status: CalibrationArtifactStatus | None = None
    competition_scope: str | None = None
    market_scope: str | None = None
    model_version_scope: str | None = None
    cutoff_at_or_before: datetime | None = None

    def __post_init__(self) -> None:
        if self.cutoff_at_or_before is not None:
            _aware(self.cutoff_at_or_before, "Query cutoff")


@dataclass(frozen=True, slots=True)
class CalibrationRegistrationResult:
    artifact: CalibrationArtifact
    inserted: bool


@dataclass(frozen=True, slots=True)
class CalibrationValidationResult:
    valid: bool
    artifact_id: str | None
    method: str | None
    serialization_version: str | None
    reason_code: str
    safe_message: str


@dataclass(frozen=True, slots=True)
class CalibrationStatusTransition:
    transition_id: str
    artifact_id: str
    previous_status: CalibrationArtifactStatus
    new_status: CalibrationArtifactStatus
    reason: str
    changed_at: datetime
    actor_source: str

    def __post_init__(self) -> None:
        _aware(self.changed_at, "Status-change timestamp")
        if not all(
            value.strip()
            for value in (
                self.transition_id,
                self.artifact_id,
                self.reason,
                self.actor_source,
            )
        ):
            raise ValueError("Status transition values must not be empty.")


class CalibrationRegistryError(RuntimeError):
    pass


class CalibrationArtifactConflictError(CalibrationRegistryError):
    pass


class InvalidCalibrationStatusTransition(CalibrationRegistryError):
    pass
