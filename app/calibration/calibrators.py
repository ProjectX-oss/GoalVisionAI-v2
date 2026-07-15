from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, Sequence, runtime_checkable

from .models import (
    CalibrationFitMetadata,
    CalibrationObservation,
    CalibrationScope,
    CalibrationScopeKind,
    CalibrationTrainingWindow,
    validate_aware,
    validate_probability,
)


@dataclass(frozen=True, slots=True)
class CalibrationFitRequest:
    fitted_at: datetime
    training_window: CalibrationTrainingWindow
    scope: CalibrationScope
    version: str
    target_prediction_timestamp: datetime | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        validate_aware(self.fitted_at, "Fitted timestamp")
        if self.fitted_at < self.training_window.end:
            raise ValueError("Fitted timestamp must not predate training data.")
        if not self.version.strip():
            raise ValueError("Calibration version must not be empty.")
        if self.model_version is not None and not self.model_version.strip():
            raise ValueError("Model version must not be empty when provided.")
        if self.target_prediction_timestamp is not None:
            validate_aware(
                self.target_prediction_timestamp,
                "Target prediction timestamp",
            )
            if self.training_window.end >= self.target_prediction_timestamp:
                raise ValueError(
                    "Training cutoff must be strictly earlier than the target."
                )


@runtime_checkable
class FittedProbabilityCalibrator(Protocol):
    @property
    def metadata(self) -> CalibrationFitMetadata: ...

    def calibrate(self, probability: Decimal) -> Decimal: ...


@runtime_checkable
class ProbabilityCalibratorTrainer(Protocol):
    def fit(
        self,
        observations: Sequence[CalibrationObservation],
        request: CalibrationFitRequest,
    ) -> FittedProbabilityCalibrator: ...


@dataclass(frozen=True, slots=True)
class IdentityCalibrator:
    metadata: CalibrationFitMetadata

    @classmethod
    def fit(
        cls,
        observations: Sequence[CalibrationObservation],
        request: CalibrationFitRequest,
    ) -> "IdentityCalibrator":
        ordered = _validate_fit_observations(observations, request)
        return cls(CalibrationFitMetadata(
            fitted_at=request.fitted_at,
            training_window=request.training_window,
            observation_count=len(ordered),
            scope=request.scope,
            method_name="identity",
            version=request.version,
            model_version=request.model_version,
        ))

    @classmethod
    def fallback(cls, at: datetime, version: str = "identity-v1") -> "IdentityCalibrator":
        validate_aware(at, "Identity fallback timestamp")
        return cls(CalibrationFitMetadata(
            fitted_at=at,
            training_window=CalibrationTrainingWindow(at, at),
            observation_count=0,
            scope=CalibrationScope.identity_scope(),
            method_name="identity",
            version=version,
            model_version=None,
        ))

    def calibrate(self, probability: Decimal) -> Decimal:
        validate_probability(probability)
        return probability


class CalibrationFittingNotImplemented(NotImplementedError):
    """Raised by honest method foundations until reviewed fitting is added."""


class PlattCalibrator:
    """Typed Platt fitting boundary; production coefficient fitting is pending."""

    method_name = "platt"

    def fit(
        self,
        observations: Sequence[CalibrationObservation],
        request: CalibrationFitRequest,
    ) -> FittedProbabilityCalibrator:
        _validate_fit_observations(observations, request)
        raise CalibrationFittingNotImplemented(
            "Production Platt fitting is not implemented; no calibration was produced."
        )


class IsotonicCalibrator:
    """Typed isotonic fitting boundary; production PAV fitting is pending."""

    method_name = "isotonic"

    def fit(
        self,
        observations: Sequence[CalibrationObservation],
        request: CalibrationFitRequest,
    ) -> FittedProbabilityCalibrator:
        _validate_fit_observations(observations, request)
        raise CalibrationFittingNotImplemented(
            "Production isotonic fitting is not implemented; no calibration was produced."
        )


def _validate_fit_observations(
    observations: Sequence[CalibrationObservation],
    request: CalibrationFitRequest,
) -> tuple[CalibrationObservation, ...]:
    ordered = tuple(sorted(
        observations,
        key=lambda item: (
            item.prediction_timestamp,
            item.observation_id,
            item.fixture_id,
        ),
    ))
    identifiers = tuple(item.observation_id for item in ordered)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Calibration fit observation IDs must be unique.")
    for observation in ordered:
        if not (
            request.training_window.start
            <= observation.prediction_timestamp
            <= request.training_window.end
        ):
            raise ValueError("Calibration fit contains data outside its training window.")
        if observation.outcome_timestamp > request.training_window.end:
            raise ValueError(
                "Calibration fit contains an outcome unavailable at the cutoff."
            )
        if request.target_prediction_timestamp is not None and (
            observation.prediction_timestamp
            >= request.target_prediction_timestamp
            or observation.outcome_timestamp
            >= request.target_prediction_timestamp
        ):
            raise ValueError("Calibration fit contains future target information.")
        if not observation_matches_scope(observation, request.scope):
            raise ValueError("Calibration observation does not match the fit scope.")
        if (
            request.model_version is not None
            and observation.model_version != request.model_version
        ):
            raise ValueError("Calibration observation does not match the model version.")
    return ordered


def observation_matches_scope(
    observation: CalibrationObservation,
    scope: CalibrationScope,
) -> bool:
    if scope.kind in {CalibrationScopeKind.GLOBAL, CalibrationScopeKind.IDENTITY}:
        return True
    if scope.kind is CalibrationScopeKind.COMPETITION:
        return observation.competition == scope.competition
    if scope.kind is CalibrationScopeKind.MARKET:
        return observation.market == scope.market
    if scope.kind is CalibrationScopeKind.COMPETITION_MARKET:
        return (
            observation.competition == scope.competition
            and observation.market == scope.market
        )
    if scope.kind is CalibrationScopeKind.ODDS_BAND:
        return observation.odds_band == scope.odds_band
    return False
