import math


class ProbabilityEngine:

    SCALE = 8.0

    def calculate(
        self,
        home_rating: float,
        away_rating: float,
    ):

        difference = home_rating - away_rating

        home_probability = 1 / (
            1 + math.exp(-difference / self.SCALE)
        )

        away_probability = 1 - home_probability

        return (
            round(home_probability * 100, 1),
            round(away_probability * 100, 1),
        )