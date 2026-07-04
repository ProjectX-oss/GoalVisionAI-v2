from app.logger import logger
from app.core.settings import settings
from app.services.telegram_service import TelegramService
from app.ai.service import AIService
from app.football.service import FootballService


class GoalVisionApp:
    def __init__(self):
        self.telegram = TelegramService(settings.bot_token)
        self.ai = AIService()
        self.football = FootballService()

        logger.info("GoalVision Engine initialized.")

    async def start(self):
        matches = await self.football.get_today_matches()

        logger.info(f"{len(matches)} TOP matches loaded.")

        for match in matches[:10]:
            print(f"{match.league} | {match.home_team} vs {match.away_team}")

        await self.telegram.send_message(
            settings.channel,
            f"✅ Loaded {len(matches)} TOP matches."
        )

        logger.info("Done.")