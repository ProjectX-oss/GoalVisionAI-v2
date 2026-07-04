from dataclasses import dataclass

from app.config import BOT_TOKEN


@dataclass
class Settings:
    bot_token: str = BOT_TOKEN
    channel: str = "@GoalVisionAI"


settings = Settings()