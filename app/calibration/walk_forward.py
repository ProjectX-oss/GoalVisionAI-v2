from dataclasses import dataclass
from typing import Sequence

from app.backtesting import WalkForwardWindow

from .calibrators import (
    CalibrationFitRequest,
    ProbabilityCalibratorTrainer,
    observation_matches_scope,
)
from .comparison import CalibrationComparisonService, CalibrationMetricComparison
from .models import (
    CalibrationFitMetadata,
    CalibrationObservation,
    CalibrationScope,
    CalibrationTrainingWindow,
)


@dataclass(frozen=True, slots=True)
class CalibrationWalkForwardFold:
    window: WalkForwardWindow
    fit_metadata: CalibrationFitMetadata
    training_observation_ids: tuple[str, ...]
    target_observation_ids: tuple[str, ...]
    comparison: CalibrationMetricComparison
    calibrated_targets: tuple[tuple[str, object], ...] = ()
    scope_used: CalibrationScope | None = None
    fit_version: str | None = None


class CalibrationWalkForwardService:
    """Fits once per fold; equal-cutoff timestamps remain training-only."""

    def __init__(self, comparisons: CalibrationComparisonService) -> None:
        self._comparisons = comparisons

    def evaluate(
        self,
        observations: Sequence[CalibrationObservation],
        windows: Sequence[WalkForwardWindow],
        trainer: ProbabilityCalibratorTrainer,
        scope: CalibrationScope,
        version: str,
        model_version: str | None = None,
    ) -> tuple[CalibrationWalkForwardFold, ...]:
        ordered_observations = tuple(sorted(
            observations,
            key=lambda item: (
                item.prediction_timestamp,
                item.observation_id,
                item.fixture_id,
            ),
        ))
        ordered_windows = tuple(sorted(
            windows,
            key=lambda item: (
                item.evaluation_start,
                item.evaluation_end,
                item.training_start,
                item.training_end,
            ),
        ))
        self._validate_windows(ordered_windows)
        folds: list[CalibrationWalkForwardFold] = []
        for window in ordered_windows:
            training = tuple(
                item
                for item in ordered_observations
                if window.training_start
                <= item.prediction_timestamp
                <= window.training_end
                and item.outcome_timestamp <= window.training_end
                and observation_matches_scope(item, scope)
                and (
                    model_version is None
                    or item.model_version == model_version
                )
            )
            targets = tuple(
                item
                for item in ordered_observations
                if window.evaluation_start
                <= item.prediction_timestamp
                < window.evaluation_end
                and item.prediction_timestamp > window.training_end
                and observation_matches_scope(item, scope)
                and (
                    model_version is None
                    or item.model_version == model_version
                )
            )
            target_at = min(
                (item.prediction_timestamp for item in targets),
                default=None,
            )
            request = CalibrationFitRequest(
                fitted_at=window.training_end,
                training_window=CalibrationTrainingWindow(
                    window.training_start,
                    window.training_end,
                ),
                scope=scope,
                version=version,
                target_prediction_timestamp=target_at,
                model_version=model_version,
            )
            fitted = trainer.fit(training, request)
            self._validate_fit_contract(fitted.metadata, request, len(training))
            folds.append(CalibrationWalkForwardFold(
                window=window,
                fit_metadata=fitted.metadata,
                training_observation_ids=tuple(
                    item.observation_id for item in training
                ),
                target_observation_ids=tuple(
                    item.observation_id for item in targets
                ),
                comparison=self._comparisons.compare(targets, fitted, scope),
                calibrated_targets=tuple(
                    (
                        item.observation_id,
                        fitted.calibrate(item.raw_probability),
                    )
                    for item in targets
                ),
                scope_used=fitted.metadata.scope,
                fit_version=fitted.metadata.version,
            ))
        return tuple(folds)

    @staticmethod
    def _validate_windows(windows: tuple[WalkForwardWindow, ...]) -> None:
        if len(set(windows)) != len(windows):
            raise ValueError("Walk-forward windows must be unique.")
        for previous, current in zip(windows, windows[1:]):
            if previous.evaluation_end > current.evaluation_start:
                raise ValueError("Walk-forward evaluation windows must not overlap.")

    @staticmethod
    def _validate_fit_contract(
        metadata: CalibrationFitMetadata,
        request: CalibrationFitRequest,
        observation_count: int,
    ) -> None:
        if metadata.training_window != request.training_window:
            raise ValueError("Calibrator returned different training boundaries.")
        if metadata.scope != request.scope:
            raise ValueError("Calibrator returned a different scope.")
        if metadata.observation_count != observation_count:
            raise ValueError("Calibrator returned an incorrect observation count.")
