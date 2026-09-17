"""Read-only fail-closed champion resolution boundary."""

from .exceptions import ChampionStateInvalidError
from .models import ActivationStatus, ChampionResolution


class RuntimeChampionResolver:
    def __init__(self, repository, model_repository, calibration_repository, policy):
        self._repository = repository
        self._model_repository = model_repository
        self._calibration_repository = calibration_repository
        self._policy = policy

    def resolve(self, model_scope):
        try:
            generation = self._repository.resolve_current_champion(model_scope)
            from .source_verification import verify_runtime_artifact
            verify_runtime_artifact(
                generation.artifact, self._model_repository,
                self._calibration_repository, self._policy,
            )
            return ChampionResolution(ActivationStatus.CHAMPION_RESOLVED, model_scope, generation, ())
        except Exception as exc:
            return ChampionResolution(ActivationStatus.CHAMPION_STATE_INVALID, model_scope, None, (str(exc),))
