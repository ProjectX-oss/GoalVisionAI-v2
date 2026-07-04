from telegram import Bot


class TelegramService:
    def __init__(self, token: str):
        self.bot = Bot(token)

    async def send_message(self, chat_id: str, text: str):
        await self.bot.send_message(
            chat_id=chat_id,
            text=text
        )