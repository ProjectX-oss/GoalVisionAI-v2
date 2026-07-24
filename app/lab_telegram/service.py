from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Mapping, Protocol

from dotenv import dotenv_values
from telegram.error import TelegramError, TimedOut

from app.services.telegram_service import TelegramMessageReceipt

from .models import (
    LAB_TELEGRAM_CHAT_ID,
    LAB_TEST_MESSAGE,
    LabTelegramConfig,
    LabTelegramOutcome,
    LabTelegramStatus,
)


TELEGRAM_TIMEOUT_SECONDS = 10.0
_KNOWN_OFFICIAL_DESTINATIONS = frozenset({"@goalvisionai"})
_OFFICIAL_DESTINATION_KEYS = (
    "GOALVISION_OFFICIAL_TELEGRAM_CHAT_ID",
    "OFFICIAL_TELEGRAM_CHAT_ID",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_CHANNEL_ID",
)


class LabTelegramTransport(Protocol):
    async def send_message_receipt(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = None,
        *,
        timeout_seconds: float,
    ) -> TelegramMessageReceipt: ...


def load_lab_telegram_config(env_file: Path = Path(".env")) -> LabTelegramConfig:
    """Load only the manual Lab credentials and secret-free destination guards."""
    values = dotenv_values(env_file)
    token = _clean(values.get("GOALVISION_LAB_TELEGRAM_BOT_TOKEN"))
    chat_id = _clean(values.get("GOALVISION_LAB_TELEGRAM_CHAT_ID"))
    enabled = (_clean(values.get("GOALVISION_LAB_TELEGRAM_ENABLED")) or "").lower()
    official = frozenset(
        value.casefold()
        for key in _OFFICIAL_DESTINATION_KEYS
        if (value := _clean(values.get(key))) is not None
    )
    return LabTelegramConfig(
        token=token,
        chat_id=chat_id,
        automatic_enabled=enabled in {"1", "true", "yes", "on"},
        official_destinations=official,
    )


async def send_manual_lab_test(
    config: LabTelegramConfig,
    transport: LabTelegramTransport,
) -> LabTelegramOutcome:
    """Validate the Lab destination and make at most one bounded send call."""
    validation = validate_lab_telegram_config(config)
    if validation is not None:
        return validation

    assert config.chat_id is not None
    try:
        receipt = await asyncio.wait_for(
            transport.send_message_receipt(
                chat_id=config.chat_id,
                text=LAB_TEST_MESSAGE,
                parse_mode=None,
                timeout_seconds=TELEGRAM_TIMEOUT_SECONDS,
            ),
            timeout=TELEGRAM_TIMEOUT_SECONDS + 1.0,
        )
    except (TimeoutError, TimedOut):
        return LabTelegramOutcome(
            LabTelegramStatus.TELEGRAM_TIMEOUT,
            destination_chat_id=config.chat_id,
        )
    except TelegramError:
        return LabTelegramOutcome(
            LabTelegramStatus.TELEGRAM_API_FAILED,
            destination_chat_id=config.chat_id,
        )
    except Exception:
        return LabTelegramOutcome(
            LabTelegramStatus.INVALID_TELEGRAM_RESPONSE,
            destination_chat_id=config.chat_id,
        )

    if (
        receipt.chat_id != LAB_TELEGRAM_CHAT_ID
        or not isinstance(receipt.message_id, int)
        or receipt.message_id <= 0
    ):
        return LabTelegramOutcome(
            LabTelegramStatus.INVALID_TELEGRAM_RESPONSE,
            destination_chat_id=config.chat_id,
        )
    return LabTelegramOutcome(
        LabTelegramStatus.SUCCESS,
        destination_chat_id=receipt.chat_id,
        telegram_message_id=receipt.message_id,
    )


def validate_lab_telegram_config(
    config: LabTelegramConfig,
) -> LabTelegramOutcome | None:
    if not config.token:
        return LabTelegramOutcome(LabTelegramStatus.MISSING_TOKEN)
    if not config.chat_id:
        return LabTelegramOutcome(LabTelegramStatus.MISSING_CHAT_ID)

    normalized = config.chat_id.casefold()
    official_destinations = (
        _KNOWN_OFFICIAL_DESTINATIONS | config.official_destinations
    )
    if normalized in official_destinations:
        return LabTelegramOutcome(
            LabTelegramStatus.OFFICIAL_DESTINATION_REJECTED,
            destination_chat_id=config.chat_id,
        )
    if config.chat_id != LAB_TELEGRAM_CHAT_ID:
        return LabTelegramOutcome(
            LabTelegramStatus.WRONG_CHAT_ID,
            destination_chat_id=config.chat_id,
        )
    return None


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
