from dataclasses import dataclass
from datetime import datetime

from .models import (
    AvailabilitySource,
    LineupObservation,
    LineupStatus,
    PlayerAvailabilityObservation,
)


@dataclass(frozen=True, slots=True)
class AvailabilityValidationPolicy:
    allow_post_match_historical: bool = False


class AvailabilityValidator:
    def __init__(self, policy: AvailabilityValidationPolicy | None = None) -> None:
        self._policy = policy or AvailabilityValidationPolicy()

    def validate_player(
        self,
        observation: PlayerAvailabilityObservation,
        source: AvailabilitySource | None,
        *,
        evaluation_cutoff: datetime | None = None,
    ) -> PlayerAvailabilityObservation:
        self._source(source)
        self._cutoff(observation.observed_at, evaluation_cutoff)
        return observation

    def validate_lineup(
        self,
        observation: LineupObservation,
        source: AvailabilitySource | None,
        *,
        kickoff: datetime,
        evaluation_cutoff: datetime | None = None,
    ) -> LineupObservation:
        self._source(source)
        self._aware(kickoff, "Kickoff timestamp")
        self._cutoff(observation.observed_at, evaluation_cutoff)
        if (
            observation.lineup_status is LineupStatus.CONFIRMED
            and observation.observed_at > kickoff
            and not self._policy.allow_post_match_historical
        ):
            raise RuntimeError("Confirmed lineup is after kickoff.")
        return observation

    @staticmethod
    def _source(source: AvailabilitySource | None) -> None:
        if source is None:
            raise LookupError("Unknown availability source.")
        if not source.enabled:
            raise PermissionError("Availability source is disabled.")

    @classmethod
    def _cutoff(cls, observed_at: datetime, cutoff: datetime | None) -> None:
        cls._aware(observed_at, "Observed timestamp")
        if cutoff is not None:
            cls._aware(cutoff, "Evaluation cutoff")
            if observed_at > cutoff:
                raise RuntimeError("Availability observation is after evaluation cutoff.")

    @staticmethod
    def _aware(value: datetime, label: str) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware.")
