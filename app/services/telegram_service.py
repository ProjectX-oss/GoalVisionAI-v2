from telegram import Bot


class TelegramService:
    def __init__(self, token: str) -> None:
        self.bot = Bot(token)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = None,
    ) -> int | None:
        arguments: dict[str, str] = {"chat_id": chat_id, "text": text}
        if parse_mode is not None:
            arguments["parse_mode"] = parse_mode
        message = await self.bot.send_message(**arguments)
        return getattr(message, "message_id", None)
