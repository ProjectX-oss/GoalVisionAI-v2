from dataclasses import dataclass
from typing import Sequence

from .calibrators import (
    CalibrationFitRequest,
    CalibrationFittingError,
    FittedProbabilityCalibrator,
    IdentityCalibrator,
    ProbabilityCalibratorTrainer,
    observation_matches_scope,
)
from .models import CalibrationObservation, CalibrationScope, CalibrationScopeKind
from .resolver import CalibrationResolutionRequest


@dataclass(frozen=True, slots=True)
class CalibrationFitAttempt:
    scope: CalibrationScope
    fitted: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class CalibrationFallbackFit:
    calibrator: FittedProbabilityCalibrator
    requested_scope: CalibrationScope
    scope_used: CalibrationScope
    attempts: tuple[CalibrationFitAttempt, ...]


class CalibrationFallbackFittingService:
    """Fits the narrowest reliable scope, then broader scopes, then Identity."""

    def fit(
        self,
        observations: Sequence[CalibrationObservation],
        resolution: CalibrationResolutionRequest,
        request: CalibrationFitRequest,
        trainer: ProbabilityCalibratorTrainer,
    ) -> CalibrationFallbackFit:
        scopes = (
            CalibrationScope(
                CalibrationScopeKind.COMPETITION_MARKET,
                competition=resolution.competition,
                market=resolution.market,
            ),
            CalibrationScope(CalibrationScopeKind.MARKET, market=resolution.market),
            CalibrationScope(
                CalibrationScopeKind.COMPETITION,
                competition=resolution.competition,
            ),
            *(
                (CalibrationScope(
                    CalibrationScopeKind.ODDS_BAND,
                    odds_band=resolution.odds_band,
                ),)
                if resolution.odds_band is not None else ()
            ),
            CalibrationScope.global_scope(),
        )
        attempts: list[CalibrationFitAttempt] = []
        for candidate_scope in scopes:
            selected = tuple(
                item for item in observations
                if observation_matches_scope(item, candidate_scope)
            )
            candidate_request = CalibrationFitRequest(
                fitted_at=request.fitted_at,
                training_window=request.training_window,
                scope=candidate_scope,
                version=request.version,
                target_prediction_timestamp=request.target_prediction_timestamp,
                model_version=request.model_version,
            )
            try:
                fitted = trainer.fit(selected, candidate_request)
            except (CalibrationFittingError, ValueError) as exc:
                attempts.append(CalibrationFitAttempt(
                    candidate_scope, False, str(exc)
                ))
                continue
            attempts.append(CalibrationFitAttempt(candidate_scope, True, None))
            return CalibrationFallbackFit(
                fitted, scopes[0], candidate_scope, tuple(attempts)
            )
        identity = IdentityCalibrator.fit(
            tuple(
                item for item in observations
                if request.training_window.start
                <= item.prediction_timestamp
                <= request.training_window.end
                and item.outcome_timestamp <= request.training_window.end
            ),
            CalibrationFitRequest(
                fitted_at=request.fitted_at,
                training_window=request.training_window,
                scope=CalibrationScope.global_scope(),
                version=f"{request.version}-identity-fallback",
                target_prediction_timestamp=request.target_prediction_timestamp,
                model_version=request.model_version,
            ),
        )
        attempts.append(CalibrationFitAttempt(
            CalibrationScope.identity_scope(), True, "All fitted scopes unsupported."
        ))
        return CalibrationFallbackFit(
            identity, scopes[0], CalibrationScope.identity_scope(), tuple(attempts)
        )
