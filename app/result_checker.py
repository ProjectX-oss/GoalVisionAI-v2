from app.models import PredictionResult


class ResultChecker:

    def check(
        self,
        prediction,
        fixture,
    ) -> PredictionResult:

        home_goals = fixture["goals"]["home"]
        away_goals = fixture["goals"]["away"]

        real_winner = "DRAW"

        if home_goals > away_goals:
            real_winner = fixture["teams"]["home"]["name"]

        elif away_goals > home_goals:
            real_winner = fixture["teams"]["away"]["name"]

        winner_correct = (
            prediction.winner == real_winner
        )

        total_goals = home_goals + away_goals

        over25_correct = (
            prediction.over25 ==
            (total_goals > 2.5)
        )

        btts_correct = (
            prediction.btts ==
            (
                home_goals > 0 and
                away_goals > 0
            )
        )

        return PredictionResult(

            fixture_id=prediction.fixture_id,

            winner_correct=winner_correct,

            over25_correct=over25_correct,

            btts_correct=btts_correct,

            home_goals=home_goals,

            away_goals=away_goals,
        )