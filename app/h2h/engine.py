from collections.abc import Iterable

from app.models import HistoricalMatch


class H2HEngine:
    """Calculates a team's normalized strength in historical meetings."""

    FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})
    NEUTRAL_STRENGTH = 0.5

    def __init__(
        self,
        max_history: int = 10,
        minimum_confidence: float = 0.3,
    ) -> None:
        if max_history < 1:
            raise ValueError("Maximum H2H history must be at least 1.")
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(
                "Minimum H2H confidence must be between 0.0 and 1.0."
            )

        self.max_history = max_history
        self.minimum_confidence = minimum_confidence

    def strength_for(
        self,
        team_id: int,
        opponent_id: int,
        fixtures: Iterable[HistoricalMatch],
    ) -> float:
        """Return H2H strength for ``team_id`` using injected fixture history."""
        matches = self._eligible_matches(
            team_id=team_id,
            opponent_id=opponent_id,
            fixtures=fixtures,
        )

        if not matches:
            return self.NEUTRAL_STRENGTH

        weighted_score = 0.0
        total_weight = 0.0
        match_count = len(matches)

        for index, match in enumerate(matches):
            weight = float(match_count - index)
            weighted_score += self._result_value(match, team_id) * weight
            total_weight += weight

        strength = weighted_score / total_weight
        history_confidence = match_count / self.max_history

        if (
            self.minimum_confidence > 0.0
            and history_confidence < self.minimum_confidence
        ):
            confidence_ratio = history_confidence / self.minimum_confidence
            strength = self.NEUTRAL_STRENGTH + (
                strength - self.NEUTRAL_STRENGTH
            ) * confidence_ratio

        return round(max(0.0, min(strength, 1.0)), 6)

    def _eligible_matches(
        self,
        team_id: int,
        opponent_id: int,
        fixtures: Iterable[HistoricalMatch],
    ) -> list[HistoricalMatch]:
        unique_matches: dict[int, HistoricalMatch] = {}

        for fixture in fixtures:
            teams = {fixture.home_team_id, fixture.away_team_id}

            if fixture.status not in self.FINISHED_STATUSES:
                continue
            if teams != {team_id, opponent_id}:
                continue
            if fixture.fixture_id not in unique_matches:
                unique_matches[fixture.fixture_id] = fixture

        return sorted(
            unique_matches.values(),
            key=lambda fixture: fixture.kickoff,
            reverse=True,
        )[: self.max_history]

    @staticmethod
    def _result_value(match: HistoricalMatch, team_id: int) -> float:
        if match.home_team_id == team_id:
            team_goals = match.home_goals
            opponent_goals = match.away_goals
        else:
            team_goals = match.away_goals
            opponent_goals = match.home_goals

        if team_goals > opponent_goals:
            return 1.0
        if team_goals == opponent_goals:
            return 0.5
        return 0.0
