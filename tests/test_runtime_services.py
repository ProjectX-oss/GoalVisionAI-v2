import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.application import GoalVisionApp
from app.database import Database
from app.models import Match
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

    def test_incomplete_predictions_are_not_published(self):
        application = GoalVisionApp.__new__(GoalVisionApp)
        match = Match(
            fixture_id=1,
            league_id=1,
            league_name="Test League",
            season=2026,
            home_team_id=10,
            home_team_name="Home",
            away_team_id=20,
            away_team_name="Away",
            kickoff=datetime.now(timezone.utc),
            status="NS",
        )
        application.football = SimpleNamespace(
            get_today_matches=AsyncMock(return_value=[match]),
            cached_team_form=lambda team_id: [],
        )
        application.history_collector = SimpleNamespace(collect=lambda data: [])
        application.standings = SimpleNamespace(load=AsyncMock())
        application.repository = TeamRepository()
        application.pipeline = SimpleNamespace(
            assess=lambda match, home, away, supporting_data: SimpleNamespace(
                prediction=SimpleNamespace(
                    winner="Home",
                    home_probability=60.0,
                    away_probability=40.0,
                    confidence="HIGH",
                    rating_difference=20.0,
                ),
            )
        )
        application.telegram = SimpleNamespace(send_message=AsyncMock())

        async def build_team(match, team_id, is_home):
            application.repository.save(SimpleNamespace(team_id=team_id))

        application.build_team = build_team

        asyncio.run(application._run())

        application.telegram.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
