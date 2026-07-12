import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.database import Database
from app.repositories import TeamRepository
from app.services.telegram_service import TelegramService


class RuntimeServiceTests(unittest.TestCase):

    def test_database_initializes_and_closes(self):
        database = Database()

        self.assertEqual(database.cursor().execute("SELECT 1").fetchone()[0], 1)

        database.close()

    def test_team_repository_round_trip(self):
        repository = TeamRepository()
        context = SimpleNamespace(team_id=1)

        repository.save(context)

        self.assertTrue(repository.has(1))
        self.assertIs(repository.get(1), context)
        repository.clear()
        self.assertFalse(repository.has(1))

    def test_telegram_service_delegates_message(self):
        service = TelegramService("000000000:test-token")
        send_message = AsyncMock()
        service.bot = SimpleNamespace(send_message=send_message)

        asyncio.run(service.send_message("@test", "message"))

        send_message.assert_awaited_once_with(
            chat_id="@test",
            text="message",
        )


if __name__ == "__main__":
    unittest.main()
