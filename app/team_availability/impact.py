from typing import Protocol, runtime_checkable

from .models import PlayerImpactEstimate, PlayerImportanceInput


@runtime_checkable
class PlayerImpactEstimator(Protocol):
    def estimate(self, value: PlayerImportanceInput) -> PlayerImpactEstimate: ...


class NoOpPlayerImpactEstimator:
    def estimate(self, value: PlayerImportanceInput) -> PlayerImpactEstimate:
        return PlayerImpactEstimate(
            player=value.player,
            score=None,
            available=False,
            reason="Player impact is unavailable without reliable strength inputs.",
        )
