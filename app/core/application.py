import asyncio

from app.core.settings import settings
from app.football.service import FootballService
from app.logger import logger
from app.pipeline import (
    PredictionPipeline,
    StandingsService,
)
from app.repositories import TeamRepository
from app.services.telegram_service import TelegramService


class GoalVisionApp:

    def __init__(self):

        self.telegram = TelegramService(
            settings.bot_token
        )

        self.football = FootballService()

        self.pipeline = PredictionPipeline()

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

            prediction = self.pipeline.predict(
                match,
                home,
                away,
            )

            predictions.append(
                (
                    match,
                    prediction,
                )
            )

        predictions.sort(

            key=lambda item: (
                item[1].confidence,
                item[1].rating_difference,
            ),

            reverse=True,
        )

        for match, prediction in predictions:

            if prediction.confidence == "LOW":
                continue

            await self.telegram.send_message(

                settings.channel,

                f"""🟢 GoalVision AI

🏆 {match.league_name}

⚽ {match.home_team_name}
vs
{match.away_team_name}

🏅 Winner
{prediction.winner}

📈 Home
{prediction.home_probability:.1f}%

📉 Away
{prediction.away_probability:.1f}%

🔥 Confidence
{prediction.confidence}
"""
            )

        logger.info(
            "%d predictions published.",
            len(predictions),
        )
