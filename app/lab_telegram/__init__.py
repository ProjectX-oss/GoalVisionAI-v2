"""Isolated, manual-only GoalVision AI Lab Telegram boundary."""

from .models import (
    LAB_TELEGRAM_CHAT_ID,
    LAB_TEST_MESSAGE,
    LabTelegramConfig,
    LabTelegramOutcome,
    LabTelegramStatus,
)
from .service import load_lab_telegram_config, send_manual_lab_test

__all__ = [
    "LAB_TELEGRAM_CHAT_ID",
    "LAB_TEST_MESSAGE",
    "LabTelegramConfig",
    "LabTelegramOutcome",
    "LabTelegramStatus",
    "load_lab_telegram_config",
    "send_manual_lab_test",
]
