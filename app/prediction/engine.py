from app.models import Match, Prediction, TeamRating

from .confidence_engine import ConfidenceEngine
from .probability_engine import ProbabilityEngine


class PredictionEngine:

    def __init__(self):

        self.probability = ProbabilityEngine()
        self.confidence = ConfidenceEngine()

    def predict(
        self,
        match: Match,
        home_rating: TeamRating,
        away_rating: TeamRating,
    ) -> Prediction:

        home_probability, away_probability = (
            self.probability.calculate(
                home_rating.total,
                away_rating.total,
            )
        )

        confidence, difference = (
            self.confidence.calculate(
                home_rating.total,
                away_rating.total,
            )
        )

        winner = (
            match.home_team_name
            if home_probability >= away_probability
            else match.away_team_name
        )

        return Prediction(
            winner=winner,
            home_probability=home_probability,
            away_probability=away_probability,
            confidence=confidence,
            rating_difference=round(difference, 2),
        )