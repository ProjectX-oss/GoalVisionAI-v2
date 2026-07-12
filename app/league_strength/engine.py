from collections.abc import Mapping
from types import MappingProxyType


class LeagueStrengthEngine:
    """Provides normalized strength ratings for football leagues."""

    def __init__(
        self,
        ratings: Mapping[int, float],
        default_strength: float,
    ) -> None:
        self._validate_strength(default_strength)

        normalized_ratings = {
            league_id: float(strength)
            for league_id, strength in ratings.items()
        }

        for league_id, strength in normalized_ratings.items():
            if not isinstance(league_id, int):
                raise TypeError("League IDs must be integers.")
            self._validate_strength(strength)

        self._ratings = MappingProxyType(normalized_ratings)
        self._default_strength = float(default_strength)

    def strength_for(self, league_id: int) -> float:
        """Return the normalized strength for a league ID."""
        return self._ratings.get(league_id, self._default_strength)

    @staticmethod
    def _validate_strength(strength: float) -> None:
        if not isinstance(strength, (int, float)):
            raise TypeError("League strength must be numeric.")
        if not 0.0 <= strength <= 1.0:
            raise ValueError("League strength must be between 0.0 and 1.0.")
