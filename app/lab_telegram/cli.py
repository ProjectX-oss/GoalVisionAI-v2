from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Callable, Sequence

from app.services.telegram_service import TelegramService

from .models import LabTelegramStatus
from .service import (
    load_lab_telegram_config,
    send_manual_lab_test,
    validate_lab_telegram_config,
)


_EXIT_CODES = {
    LabTelegramStatus.SUCCESS: 0,
    LabTelegramStatus.MISSING_TOKEN: 2,
    LabTelegramStatus.MISSING_CHAT_ID: 2,
    LabTelegramStatus.OFFICIAL_DESTINATION_REJECTED: 3,
    LabTelegramStatus.WRONG_CHAT_ID: 3,
    LabTelegramStatus.TELEGRAM_TIMEOUT: 4,
    LabTelegramStatus.TELEGRAM_API_FAILED: 4,
    LabTelegramStatus.INVALID_TELEGRAM_RESPONSE: 5,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goalvision-lab-telegram",
        description="Manual one-message GoalVision AI Lab Telegram test.",
    )
    parser.add_subparsers(dest="command", required=True).add_parser(
        "send-test",
        help="Send exactly one hard-coded technical test message to the Lab channel.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    env_file: Path = Path(".env"),
    transport_factory: Callable[[str], TelegramService] = TelegramService,
) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "send-test":
        raise AssertionError("Unknown Lab Telegram command.")

    config = load_lab_telegram_config(env_file)
    validation = validate_lab_telegram_config(config)
    if validation is not None:
        outcome = validation
    else:
        assert config.token is not None
        outcome = asyncio.run(
            send_manual_lab_test(config, transport_factory(config.token))
        )
    print(outcome.to_human())
    return _EXIT_CODES[outcome.status]


if __name__ == "__main__":
    sys.exit(main())
