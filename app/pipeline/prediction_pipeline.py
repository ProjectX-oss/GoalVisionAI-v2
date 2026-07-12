from app.pipeline.team_builder import TeamBuilder
from app.prediction import PredictionEngine


class PredictionPipeline:

    def __init__(self):

        self.builder = TeamBuilder()

        self.engine = PredictionEngine()

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