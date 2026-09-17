from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


LAB_TELEGRAM_CHAT_ID = "-1003510920417"
LAB_TEST_MESSAGE = """🧪 GOALVISION AI LAB

✅ Lab Telegram savienojuma tests veiksmīgs.

Bots: @GoalVision_AI_Lab_Bot
Vide: LAB
Statuss: savienojums darbojas

Šī ir tikai tehniska testa ziņa.
Tā nav Official prognoze un neietekmē statistiku vai bankrollu."""


class LabTelegramStatus(str, Enum):
    SUCCESS = "SUCCESS"
    MISSING_TOKEN = "MISSING_TOKEN"
    MISSING_CHAT_ID = "MISSING_CHAT_ID"
    OFFICIAL_DESTINATION_REJECTED = "OFFICIAL_DESTINATION_REJECTED"
    WRONG_CHAT_ID = "WRONG_CHAT_ID"
    TELEGRAM_TIMEOUT = "TELEGRAM_TIMEOUT"
    TELEGRAM_API_FAILED = "TELEGRAM_API_FAILED"
    INVALID_TELEGRAM_RESPONSE = "INVALID_TELEGRAM_RESPONSE"


@dataclass(frozen=True)
class LabTelegramConfig:
    token: str | None
    chat_id: str | None
    automatic_enabled: bool
    official_destinations: frozenset[str] = frozenset()


@dataclass(frozen=True)
class LabTelegramOutcome:
    status: LabTelegramStatus
    destination_chat_id: str | None = None
    telegram_message_id: int | None = None

    @property
    def success(self) -> bool:
        return self.status is LabTelegramStatus.SUCCESS

    def to_human(self) -> str:
        if self.success:
            return (
                "Lab Telegram test accepted: "
                f"destination={self.destination_chat_id} "
                f"message_id={self.telegram_message_id}"
            )
        destination = (
            f" destination={self.destination_chat_id}"
            if self.destination_chat_id
            else ""
        )
        return f"Lab Telegram test not sent: status={self.status.value}{destination}"
