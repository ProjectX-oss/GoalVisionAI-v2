import asyncio
import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import BadRequest

from app.lab_telegram import (
    LAB_TELEGRAM_CHAT_ID,
    LAB_TEST_MESSAGE,
    LabTelegramConfig,
    LabTelegramStatus,
    load_lab_telegram_config,
    send_manual_lab_test,
)
from app.lab_telegram.cli import main
from app.services.telegram_service import TelegramMessageReceipt, TelegramService


TOKEN = "123456789:never-print-this-secret"


class RecordingTransport:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result or TelegramMessageReceipt(42, LAB_TELEGRAM_CHAT_ID)
        self.error = error

    async def send_message_receipt(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def config(token=TOKEN, chat_id=LAB_TELEGRAM_CHAT_ID, enabled=False, official=()):
    return LabTelegramConfig(
        token=token,
        chat_id=chat_id,
        automatic_enabled=enabled,
        official_destinations=frozenset(value.casefold() for value in official),
    )


class LabTelegramTests(unittest.TestCase):
    def test_missing_token_refuses_without_send(self):
        transport = RecordingTransport()
        outcome = asyncio.run(send_manual_lab_test(config(token=None), transport))
        self.assertEqual(outcome.status, LabTelegramStatus.MISSING_TOKEN)
        self.assertEqual(transport.calls, [])

    def test_missing_chat_id_refuses_without_send(self):
        transport = RecordingTransport()
        outcome = asyncio.run(send_manual_lab_test(config(chat_id=None), transport))
        self.assertEqual(outcome.status, LabTelegramStatus.MISSING_CHAT_ID)
        self.assertEqual(transport.calls, [])

    def test_wrong_chat_id_refuses_without_send(self):
        transport = RecordingTransport()
        outcome = asyncio.run(send_manual_lab_test(config(chat_id="-1000000000000"), transport))
        self.assertEqual(outcome.status, LabTelegramStatus.WRONG_CHAT_ID)
        self.assertEqual(transport.calls, [])

    def test_official_destination_is_rejected(self):
        transport = RecordingTransport()
        outcome = asyncio.run(send_manual_lab_test(config(chat_id="@GoalVisionAI"), transport))
        self.assertEqual(
            outcome.status,
            LabTelegramStatus.OFFICIAL_DESTINATION_REJECTED,
        )
        self.assertEqual(transport.calls, [])

    def test_configured_official_destination_is_rejected(self):
        transport = RecordingTransport()
        outcome = asyncio.run(
            send_manual_lab_test(
                config(
                    chat_id=LAB_TELEGRAM_CHAT_ID,
                    official=(LAB_TELEGRAM_CHAT_ID,),
                ),
                transport,
            )
        )
        self.assertEqual(
            outcome.status,
            LabTelegramStatus.OFFICIAL_DESTINATION_REJECTED,
        )
        self.assertEqual(transport.calls, [])

    def test_disabled_automatic_mode_does_not_block_manual_test(self):
        transport = RecordingTransport()
        outcome = asyncio.run(send_manual_lab_test(config(enabled=False), transport))
        self.assertEqual(outcome.status, LabTelegramStatus.SUCCESS)
        self.assertEqual(len(transport.calls), 1)

    def test_exactly_one_send_call_with_exact_message_and_timeout(self):
        transport = RecordingTransport()
        outcome = asyncio.run(send_manual_lab_test(config(), transport))
        self.assertTrue(outcome.success)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(
            transport.calls[0],
            {
                "chat_id": LAB_TELEGRAM_CHAT_ID,
                "text": LAB_TEST_MESSAGE,
                "parse_mode": None,
                "timeout_seconds": 10.0,
            },
        )

    def test_telegram_api_failure_is_typed_and_secret_free(self):
        transport = RecordingTransport(error=BadRequest(f"failure {TOKEN}"))
        outcome = asyncio.run(send_manual_lab_test(config(), transport))
        self.assertEqual(outcome.status, LabTelegramStatus.TELEGRAM_API_FAILED)
        self.assertNotIn(TOKEN, outcome.to_human())

    def test_success_requires_matching_response_chat(self):
        transport = RecordingTransport(
            result=TelegramMessageReceipt(42, "-1000000000000")
        )
        outcome = asyncio.run(send_manual_lab_test(config(), transport))
        self.assertEqual(
            outcome.status,
            LabTelegramStatus.INVALID_TELEGRAM_RESPONSE,
        )

    def test_success_outcome_contains_only_safe_receipt(self):
        outcome = asyncio.run(send_manual_lab_test(config(), RecordingTransport()))
        self.assertEqual(outcome.status, LabTelegramStatus.SUCCESS)
        self.assertEqual(outcome.destination_chat_id, LAB_TELEGRAM_CHAT_ID)
        self.assertEqual(outcome.telegram_message_id, 42)
        self.assertNotIn(TOKEN, repr(outcome))
        self.assertNotIn(TOKEN, outcome.to_human())

    def test_env_loader_keeps_disabled_mode_manual(self):
        with patch(
            "app.lab_telegram.service.dotenv_values",
            return_value={
                "GOALVISION_LAB_TELEGRAM_BOT_TOKEN": TOKEN,
                "GOALVISION_LAB_TELEGRAM_CHAT_ID": LAB_TELEGRAM_CHAT_ID,
                "GOALVISION_LAB_TELEGRAM_ENABLED": "false",
            },
        ):
            loaded = load_lab_telegram_config()
        self.assertFalse(loaded.automatic_enabled)
        self.assertEqual(loaded.chat_id, LAB_TELEGRAM_CHAT_ID)

    def test_cli_never_prints_token_on_api_failure(self):
        class FailingTransport:
            async def send_message_receipt(self, **kwargs):
                raise BadRequest(f"failure {TOKEN}")

        with patch(
            "app.lab_telegram.cli.load_lab_telegram_config",
            return_value=config(),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    ["send-test"],
                    transport_factory=lambda token: FailingTransport(),
                )
        self.assertNotEqual(exit_code, 0)
        self.assertNotIn(TOKEN, output.getvalue())

    def test_existing_transport_returns_bounded_matching_receipt(self):
        service = TelegramService(TOKEN)
        service.bot = SimpleNamespace(
            send_message=AsyncMock(
                return_value=SimpleNamespace(
                    message_id=42,
                    chat=SimpleNamespace(id=int(LAB_TELEGRAM_CHAT_ID)),
                )
            )
        )
        receipt = asyncio.run(
            service.send_message_receipt(
                LAB_TELEGRAM_CHAT_ID,
                LAB_TEST_MESSAGE,
                timeout_seconds=10.0,
            )
        )
        self.assertEqual(receipt, TelegramMessageReceipt(42, LAB_TELEGRAM_CHAT_ID))
        service.bot.send_message.assert_awaited_once_with(
            chat_id=LAB_TELEGRAM_CHAT_ID,
            text=LAB_TEST_MESSAGE,
            read_timeout=10.0,
            write_timeout=10.0,
            connect_timeout=10.0,
            pool_timeout=10.0,
        )


if __name__ == "__main__":
    unittest.main()
