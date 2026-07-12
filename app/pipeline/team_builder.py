from app.analyzers import FormAnalyzer
from app.models import TeamContext
from app.prediction import (
    FeatureBuilder,
    RatingEngine,
    TeamStrengthEngine,
)


class TeamBuilder:

    def __init__(self):

        self.form = FormAnalyzer()
        self.features = FeatureBuilder()
        self.strength = TeamStrengthEngine()
        self.rating = RatingEngine()

    def build(
        self,
        team_id: int,
        history,
        table,
        is_home: bool,
    ) -> TeamContext:

        snapshot = self.form.analyze(
            team_id,
            history,
        )

        features = self.features.build(
            snapshot
        )

        if table and team_id in table:

            row = table[team_id]

            teams = len(table)

            features.league_position = (
                (teams - row.position + 1)
                / teams
            )

        strength = self.strength.calculate(
            features
        )

        rating = self.rating.calculate(
            strength,
            is_home=is_home,
        )

        return TeamContext(

            team_id=team_id,

            snapshot=snapshot,

            features=features,

            strength=strength,

            rating=rating,
        )