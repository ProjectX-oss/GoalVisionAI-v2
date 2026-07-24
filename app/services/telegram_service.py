from dataclasses import dataclass

from telegram import Bot


@dataclass(frozen=True)
class TelegramMessageReceipt:
    """Minimal non-secret Telegram acknowledgement used by manual transports."""

    message_id: int
    chat_id: str


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

    async def send_message_receipt(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = None,
        *,
        timeout_seconds: float,
    ) -> TelegramMessageReceipt:
        """Send once with bounded HTTP timeouts and return Telegram's receipt."""
        if timeout_seconds <= 0:
            raise ValueError("Telegram timeout must be positive.")

        arguments: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "read_timeout": timeout_seconds,
            "write_timeout": timeout_seconds,
            "connect_timeout": timeout_seconds,
            "pool_timeout": timeout_seconds,
        }
        if parse_mode is not None:
            arguments["parse_mode"] = parse_mode

        message = await self.bot.send_message(**arguments)
        message_id = getattr(message, "message_id", None)
        accepted_chat_id = getattr(message, "chat_id", None)
        if accepted_chat_id is None:
            accepted_chat_id = getattr(getattr(message, "chat", None), "id", None)
        if not isinstance(message_id, int) or accepted_chat_id is None:
            raise ValueError("Telegram response did not contain a message receipt.")
        return TelegramMessageReceipt(
            message_id=message_id,
            chat_id=str(accepted_chat_id),
        )
