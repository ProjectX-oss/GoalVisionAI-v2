from app.league_strength import LeagueStrengthEngine
from app.pipeline.team_builder import TeamBuilder
from app.prediction import PredictionEngine


class PredictionPipeline:

    def __init__(
        self,
        league_strength: LeagueStrengthEngine,
    ) -> None:

        self.builder = TeamBuilder()

        self.engine = PredictionEngine()

        self.league_strength = league_strength

    def build_team(
        self,
        team_id,
        history,
        table,
        is_home,
    ):

        return self.builder.build(

            team_id=team_id,

            history=history,

            table=table,

            is_home=is_home,
        )

    def predict(
        self,
        match,
        home,
        away,
    ):

        return self.engine.predict(

            match,

            home.rating,

            away.rating,
        )
