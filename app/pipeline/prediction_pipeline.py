from app.explanations import PredictionExplanationEngine
from app.h2h import H2HEngine
from app.league_strength import LeagueStrengthEngine
from app.models import Match, Prediction, TeamContext
from app.pipeline.team_builder import TeamBuilder
from app.prediction import PredictionEngine
from app.quality_score import QualityScoreEngine, QualitySignalsBuilder
from app.rest_days import RestDaysEngine

from .models import PredictionAssessment, PredictionSupportingData


class PredictionPipeline:

    def __init__(
        self,
        league_strength: LeagueStrengthEngine,
        h2h: H2HEngine,
        rest_days: RestDaysEngine,
        quality_score: QualityScoreEngine,
        explanations: PredictionExplanationEngine,
    ) -> None:

        self.builder = TeamBuilder()

        self.engine = PredictionEngine()

        self.league_strength = league_strength

        self.h2h = h2h

        self.rest_days = rest_days

        self.quality_score = quality_score

        self.explanations = explanations

        self.quality_signals = QualitySignalsBuilder(
            league_strength=league_strength,
            h2h=h2h,
            rest_days=rest_days,
        )

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
        match: Match,
        home: TeamContext,
        away: TeamContext,
    ) -> Prediction:

        return self.engine.predict(

            match,

            home.rating,

            away.rating,
        )

    def assess(
        self,
        match: Match,
        home: TeamContext,
        away: TeamContext,
        supporting_data: PredictionSupportingData | None = None,
    ) -> PredictionAssessment:
        support = supporting_data or PredictionSupportingData()
        prediction = self.predict(match, home, away)
        signals = self.quality_signals.build(
            match=match,
            home=home,
            away=away,
            h2h_history=support.h2h_history,
            rest_history=support.rest_history,
        )
        quality_score = self.quality_score.evaluate(signals)
        explanation = self.explanations.explain(
            match=match,
            prediction=prediction,
            quality_score=quality_score,
            quality_signals=signals,
            home=home,
            away=away,
            h2h_history=support.h2h_history,
            rest_history=support.rest_history,
        )

        return PredictionAssessment(
            prediction=prediction,
            quality_score=quality_score,
            explanation=explanation,
            home_context=home,
            away_context=away,
            quality_signals=signals,
            reason_codes=quality_score.reason_codes,
            supporting_metadata=support.metadata,
        )
