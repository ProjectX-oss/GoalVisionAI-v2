import asyncio

from app.collector import HistoryCollector
from app.core.settings import settings
from app.football.service import FootballService
from app.h2h import H2HEngine
from app.league_strength import (
    LEAGUE_STRENGTH_RATINGS,
    UNKNOWN_LEAGUE_STRENGTH,
    LeagueStrengthEngine,
)
from app.logger import logger
from app.models import Match
from app.pipeline import (
    PredictionSupportingData,
    PredictionPipeline,
    StandingsService,
)
from app.repositories import TeamRepository
from app.quality_score import (
    DEFAULT_QUALITY_SCORE_CONFIG,
    QualityScoreEngine,
)
from app.rest_days import RestDaysEngine
from app.services.telegram_service import TelegramService


class GoalVisionApp:

    def __init__(self):

        self.telegram = TelegramService(
            settings.bot_token
        )

        self.football = FootballService()

        self.history_collector = HistoryCollector()

        self.league_strength = LeagueStrengthEngine(
            ratings=LEAGUE_STRENGTH_RATINGS,
            default_strength=UNKNOWN_LEAGUE_STRENGTH,
        )

        self.h2h = H2HEngine()

        self.rest_days = RestDaysEngine()

        self.quality_score = QualityScoreEngine(
            DEFAULT_QUALITY_SCORE_CONFIG
        )

        self.pipeline = PredictionPipeline(
            league_strength=self.league_strength,
            h2h=self.h2h,
            rest_days=self.rest_days,
            quality_score=self.quality_score,
        )

        self.repository = TeamRepository()

        self.standings = StandingsService(
            self.football
        )

        logger.info(
            "GoalVision initialized."
        )

    async def build_team(
        self,
        match,
        team_id,
        is_home,
    ):

        if self.repository.has(team_id):
            return

        history = await self.football.load_team_form(
            team_id
        )

        table = self.standings.get(
            match.league_id,
            match.season,
        )

        context = self.pipeline.build_team(

            team_id=team_id,

            history=history,

            table=table,

            is_home=is_home,
        )

        self.repository.save(context)

    async def start(self):

        try:
            await self._run()
        finally:
            self.repository.clear()
            self.standings.clear()
            self.football.clear_cache()
            await self.football.client.close()

    async def _run(self):

        matches = await self.football.get_today_matches()

        logger.info(
            "%d matches loaded.",
            len(matches),
        )

        if not matches:
            return

        await self.standings.load(
            matches
        )

        await asyncio.gather(

            *[
                self.build_team(
                    match,
                    match.home_team_id,
                    True,
                )
                for match in matches
            ],

            *[
                self.build_team(
                    match,
                    match.away_team_id,
                    False,
                )
                for match in matches
            ],

        )

        predictions = []

        for match in matches:

            home = self.repository.get(
                match.home_team_id
            )

            away = self.repository.get(
                match.away_team_id
            )

            assessment = self.pipeline.assess(
                match,
                home,
                away,
                supporting_data=self._supporting_data(match),
            )

            predictions.append(
                (
                    match,
                    assessment,
                )
            )

        predictions.sort(

            key=lambda item: (
                item[1].prediction.confidence,
                item[1].prediction.rating_difference,
            ),

            reverse=True,
        )

        logger.warning(
            "%d predictions generated but not published because required "
            "odds and reasoning are unavailable.",
            len(predictions),
        )

    def _supporting_data(self, match: Match) -> PredictionSupportingData:
        raw_history = (
            self.football.cached_team_form(match.home_team_id)
            + self.football.cached_team_form(match.away_team_id)
        )

        if not raw_history:
            return PredictionSupportingData()

        history = tuple(self.history_collector.collect(raw_history))
        return PredictionSupportingData(
            h2h_history=history,
            rest_history=history,
            metadata=(("history_source", "cached_recent_team_fixtures"),),
        )
