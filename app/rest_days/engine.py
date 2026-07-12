from collections.abc import Iterable
from datetime import datetime

from app.models import HistoricalMatch


class RestDaysEngine:
    """Calculates normalized rest advantage from historical fixture dates."""

    FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})
    NEUTRAL_ADVANTAGE = 0.5

    def __init__(self, maximum_rest_days: float = 14.0) -> None:
        if maximum_rest_days <= 0.0:
            raise ValueError("Maximum rest days must be greater than zero.")

        self.maximum_rest_days = float(maximum_rest_days)

    def advantage_for(
        self,
        home_team_id: int,
        away_team_id: int,
        fixture_date: datetime,
        fixtures: Iterable[HistoricalMatch],
    ) -> float:
        """Return normalized home-versus-away rest advantage."""
        history = tuple(fixtures)
        home_previous = self._previous_match_date(
            team_id=home_team_id,
            fixture_date=fixture_date,
            fixtures=history,
        )
        away_previous = self._previous_match_date(
            team_id=away_team_id,
            fixture_date=fixture_date,
            fixtures=history,
        )

        if home_previous is None or away_previous is None:
            return self.NEUTRAL_ADVANTAGE

        home_rest = self._normalized_rest(fixture_date, home_previous)
        away_rest = self._normalized_rest(fixture_date, away_previous)
        advantage = self.NEUTRAL_ADVANTAGE + (home_rest - away_rest) / 2.0

        return round(max(0.0, min(advantage, 1.0)), 6)

    def _previous_match_date(
        self,
        team_id: int,
        fixture_date: datetime,
        fixtures: Iterable[HistoricalMatch],
    ) -> datetime | None:
        previous_dates = (
            fixture.kickoff
            for fixture in fixtures
            if fixture.status in self.FINISHED_STATUSES
            and fixture.kickoff < fixture_date
            and team_id in {fixture.home_team_id, fixture.away_team_id}
        )

        return max(previous_dates, default=None)

    def _normalized_rest(
        self,
        fixture_date: datetime,
        previous_match_date: datetime,
    ) -> float:
        elapsed_days = (
            fixture_date - previous_match_date
        ).total_seconds() / 86_400.0
        capped_days = min(max(elapsed_days, 0.0), self.maximum_rest_days)

        return capped_days / self.maximum_rest_days
