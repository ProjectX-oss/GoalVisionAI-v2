class ConfidenceEngine:

    def calculate(
        self,
        home_rating: float,
        away_rating: float,
    ) -> tuple[str, float]:

        difference = abs(home_rating - away_rating)

        if difference >= 15:
            return "HIGH", difference

        if difference >= 8:
            return "MEDIUM", difference

        return "LOW", difference