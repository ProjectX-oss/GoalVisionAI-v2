from app.h2h import H2HEngine
from app.league_strength import LeagueStrengthEngine
from app.models import HistoricalMatch, Match, TeamContext
from app.rest_days import RestDaysEngine

from .models import QualitySignals


class QualitySignalsBuilder:
    """Builds quality signals from existing typed GoalVision data."""

    def __init__(
        self,
        league_strength: LeagueStrengthEngine,
        h2h: H2HEngine,
        rest_days: RestDaysEngine,
        recent_form_target: int = 5,
    ) -> None:
        if recent_form_target < 1:
            raise ValueError("Recent-form target must be at least 1.")

        self.league_strength = league_strength
        self.h2h = h2h
        self.rest_days = rest_days
        self.recent_form_target = recent_form_target

    def build(
        self,
        match: Match,
        home: TeamContext,
        away: TeamContext,
        h2h_history: tuple[HistoricalMatch, ...] | None,
        rest_history: tuple[HistoricalMatch, ...] | None,
    ) -> QualitySignals:
        recent_form = self._sample_availability(
            home.snapshot.games,
            away.snapshot.games,
            self.recent_form_target,
        )
        standings = self._pair_availability(
            home.features.league_position > 0.0,
            away.features.league_position > 0.0,
        )
        home_away = self._pair_availability(
            home.snapshot.home_games > 0,
            away.snapshot.away_games > 0,
        )
        attack = self._pair_availability(
            home.snapshot.games > 0,
            away.snapshot.games > 0,
        )
        defense = attack
        league_strength = (
            1.0 if self.league_strength.has_rating(match.league_id) else None
        )
        h2h_quality = self._h2h_quality(match, h2h_history)
        rest_availability = self._rest_availability(match, rest_history)

        availability_values = (
            recent_form,
            league_strength,
            standings,
            h2h_quality,
            rest_availability,
            home_away,
            attack,
            defense,
        )
        missing_count = sum(value is None for value in availability_values)

        return QualitySignals(
            recent_form=recent_form,
            league_strength=league_strength,
            standings=standings,
            h2h=h2h_quality,
            rest_days=rest_availability,
            home_away=home_away,
            attack=attack,
            defense=defense,
            conflicting_signal_penalty=self._conflict_penalty(home, away),
            missing_data_penalty=missing_count / len(availability_values),
        )

    def _h2h_quality(
        self,
        match: Match,
        history: tuple[HistoricalMatch, ...] | None,
    ) -> float | None:
        if not history:
            return None

        quality = self.h2h.sample_quality_for(
            team_id=match.home_team_id,
            opponent_id=match.away_team_id,
            fixtures=history,
        )
        return quality if quality > 0.0 else None

    def _rest_availability(
        self,
        match: Match,
        history: tuple[HistoricalMatch, ...] | None,
    ) -> float | None:
        if not history:
            return None

        if self.rest_days.has_history_for(
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            fixture_date=match.kickoff,
            fixtures=history,
        ):
            return 1.0
        return None

    @staticmethod
    def _sample_availability(
        home_count: int,
        away_count: int,
        target: int,
    ) -> float | None:
        if home_count == 0 and away_count == 0:
            return None

        available = min(home_count, target) + min(away_count, target)
        return round(available / (target * 2), 6)

    @staticmethod
    def _pair_availability(home_available: bool, away_available: bool) -> float | None:
        available = int(home_available) + int(away_available)
        return available / 2.0 if available else None

    @staticmethod
    def _conflict_penalty(home: TeamContext, away: TeamContext) -> float:
        differences = (
            home.rating.form - away.rating.form,
            home.rating.attack - away.rating.attack,
            home.rating.defense - away.rating.defense,
            home.rating.momentum - away.rating.momentum,
        )
        positive = sum(difference > 0.0 for difference in differences)
        negative = sum(difference < 0.0 for difference in differences)
        directional = positive + negative

        if directional < 2 or positive == 0 or negative == 0:
            return 0.0
        return round(min(positive, negative) / directional, 6)
