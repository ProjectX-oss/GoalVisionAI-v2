from dataclasses import dataclass
from datetime import timedelta

from .models import LineupStatus, PublicationStage


@dataclass(frozen=True, slots=True)
class AvailabilityFreshnessPolicy:
    injury_max_age: timedelta = timedelta(days=3)
    suspension_max_age: timedelta = timedelta(days=7)
    predicted_lineup_max_age: timedelta = timedelta(days=2)
    confirmed_lineup_max_age: timedelta = timedelta(hours=3)
    squad_max_age: timedelta = timedelta(days=14)

    def __post_init__(self) -> None:
        if any(
            value < timedelta(0)
            for value in (
                self.injury_max_age,
                self.suspension_max_age,
                self.predicted_lineup_max_age,
                self.confirmed_lineup_max_age,
                self.squad_max_age,
            )
        ):
            raise ValueError("Freshness thresholds must not be negative.")


@dataclass(frozen=True, slots=True)
class LineupConfirmationPolicy:
    expected_lineup_before_kickoff: timedelta = timedelta(minutes=75)
    predicted_review_allowed: bool = True
    confirmed_required_stages: tuple[PublicationStage, ...] = (
        PublicationStage.POST_LINEUP,
        PublicationStage.FINAL_PRE_KICKOFF,
    )

    def __post_init__(self) -> None:
        if self.expected_lineup_before_kickoff < timedelta(0):
            raise ValueError("Expected lineup window must not be negative.")

    def expected_status(
        self,
        stage: PublicationStage,
        *,
        time_until_kickoff: timedelta,
    ) -> LineupStatus:
        if stage in self.confirmed_required_stages:
            return LineupStatus.CONFIRMED
        if time_until_kickoff <= self.expected_lineup_before_kickoff:
            return LineupStatus.CONFIRMED
        if self.predicted_review_allowed:
            return LineupStatus.PREDICTED
        return LineupStatus.NOT_AVAILABLE
