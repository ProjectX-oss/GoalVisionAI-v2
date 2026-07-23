import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.database import (
    Database,
    MigrationManager,
    SQLitePredictionResultRepository,
)
from app.results import (
    DEFAULT_FIXTURE_STATUS_POLICY,
    DEFAULT_MARKET_SETTLEMENT_REGISTRY,
    FinishedMatchResult,
    PredictionResultResolutionService,
    PredictionResultResolver,
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
    SettlementReasonCode,
)


class DatabaseResultRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = (
            Path("tests") / f".prediction-results-{uuid4().hex}.db"
        )
        self.database: Database | None = None
        self.addCleanup(self._cleanup_database)
        self.database = Database(self.database_path)
        self.database.connection.execute(
            "CREATE TABLE existing_history (value TEXT NOT NULL)"
        )
        self.database.connection.execute(
            "INSERT INTO existing_history (value) VALUES ('keep-me')"
        )
        self.database.commit()
        self.repository = SQLitePredictionResultRepository(self.database)
        self.published_at = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)
        self.resolved_at = datetime(2026, 7, 13, 20, tzinfo=timezone.utc)

    def _cleanup_database(self) -> None:
        if self.database is not None:
            self.database.close()
        for suffix in ("", "-journal", "-shm", "-wal"):
            path = Path(f"{self.database_path}{suffix}")
            if path.exists():
                path.unlink()

    def prediction(
        self,
        prediction_id: str = "prediction-1",
        fixture_id: int = 500,
        selection: str = "HOME",
    ) -> PublishedPredictionReference:
        return PublishedPredictionReference(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            market="Match Winner",
            selection=selection,
            published_at=self.published_at,
            odds=1.85,
            stake=2.5,
        )

    def result(
        self,
        status: ResolutionStatus,
        prediction_id: str = "prediction-1",
        fixture_id: int = 500,
        resolved_offset: int = 0,
    ) -> ResolvedPredictionResult:
        score = {
            ResolutionStatus.WON: (2, 1),
            ResolutionStatus.LOST: (0, 1),
            ResolutionStatus.VOID: (None, None),
        }[status]
        reason = (
            SettlementReasonCode.FIXTURE_CANCELLED
            if status is ResolutionStatus.VOID
            else SettlementReasonCode.MATCH_RESULT_SETTLED
        )
        return ResolvedPredictionResult(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            status=status,
            resolved_at=self.resolved_at + timedelta(seconds=resolved_offset),
            home_score=score[0],
            away_score=score[1],
            settlement_rule_version="match-winner-v1",
            reason_codes=(reason,),
        )

    def test_migration_creates_versioned_result_schema(self):
        tables = {
            row["name"]
            for row in self.database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        columns = {
            row["name"]
            for row in self.database.connection.execute(
                "PRAGMA table_info(published_predictions)"
            )
        }

        self.assertIn("schema_migrations", tables)
        self.assertIn("published_predictions", tables)
        self.assertTrue(
            {
                "prediction_id",
                "fixture_id",
                "market",
                "pick",
                "odds",
                "stake",
                "published_at",
                "settlement_status",
                "home_score",
                "away_score",
                "settlement_reason_codes",
                "settlement_rule_version",
                "resolved_at",
            }.issubset(columns)
        )
        self.assertEqual(
            self.database.connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()[0]["version"],
            1,
        )

    def test_migration_is_idempotent_and_preserves_existing_data(self):
        MigrationManager(self.database.connection).migrate()
        MigrationManager(self.database.connection).migrate()

        value = self.database.connection.execute(
            "SELECT value FROM existing_history"
        ).fetchone()["value"]
        migration_count = self.database.connection.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations"
        ).fetchone()["count"]
        self.assertEqual(value, "keep-me")
        self.assertEqual(migration_count, 30)

    def test_saves_published_prediction_idempotently(self):
        prediction = self.prediction()

        first = self.repository.save_published(prediction)
        second = self.repository.save_published(prediction)

        self.assertEqual(first, prediction)
        self.assertEqual(second, prediction)
        row = self.database.connection.execute(
            "SELECT * FROM published_predictions WHERE prediction_id = ?",
            (prediction.prediction_id,),
        ).fetchone()
        self.assertEqual(row["fixture_id"], 500)
        self.assertEqual(row["market"], "Match Winner")
        self.assertEqual(row["pick"], "HOME")
        self.assertEqual(row["odds"], 1.85)
        self.assertEqual(row["stake"], 2.5)
        self.assertEqual(row["settlement_status"], "PENDING")

    def test_loads_pending_predictions(self):
        first = self.prediction()
        second = self.prediction("prediction-2", 501, "AWAY")
        self.repository.save_published(first)
        self.repository.save_published(second)

        pending = self.repository.load_pending()

        self.assertEqual(pending, (first, second))

    def test_saves_won_result(self):
        self.repository.save_published(self.prediction())
        expected = self.result(ResolutionStatus.WON)

        stored = self.repository.store_if_absent(expected)

        self.assertEqual(stored, expected)
        self.assertEqual(self.repository.get_resolved("prediction-1"), expected)
        self.assertEqual(self.repository.load_pending(), ())

    def test_saves_lost_result(self):
        self.repository.save_published(self.prediction())
        expected = self.result(ResolutionStatus.LOST)

        stored = self.repository.store_if_absent(expected)

        self.assertEqual(stored.status, ResolutionStatus.LOST)
        self.assertEqual((stored.home_score, stored.away_score), (0, 1))

    def test_saves_void_result(self):
        self.repository.save_published(self.prediction())
        expected = self.result(ResolutionStatus.VOID)

        stored = self.repository.store_if_absent(expected)

        self.assertEqual(stored.status, ResolutionStatus.VOID)
        self.assertEqual(
            stored.reason_codes,
            (SettlementReasonCode.FIXTURE_CANCELLED,),
        )

    def test_duplicate_settlement_preserves_first_result(self):
        self.repository.save_published(self.prediction())
        first = self.repository.store_if_absent(
            self.result(ResolutionStatus.WON)
        )

        duplicate = self.repository.store_if_absent(
            self.result(ResolutionStatus.LOST)
        )

        self.assertEqual(duplicate, first)
        self.assertEqual(
            self.repository.get_resolved("prediction-1").status,
            ResolutionStatus.WON,
        )

    def test_results_persist_across_repository_reinitialization(self):
        self.repository.save_published(self.prediction())
        expected = self.repository.store_if_absent(
            self.result(ResolutionStatus.WON)
        )
        self.database.close()
        self.database = Database(self.database_path)

        reinitialized = SQLitePredictionResultRepository(self.database)

        self.assertEqual(reinitialized.get_resolved("prediction-1"), expected)

    def test_resolution_service_persists_result_across_reinitialization(self):
        prediction = self.prediction()
        self.repository.save_published(prediction)
        service = PredictionResultResolutionService(
            resolver=PredictionResultResolver(
                status_policy=DEFAULT_FIXTURE_STATUS_POLICY,
                market_registry=DEFAULT_MARKET_SETTLEMENT_REGISTRY,
            ),
            repository=self.repository,
            clock=lambda: self.resolved_at,
        )

        resolved = service.resolve_one(
            prediction,
            FinishedMatchResult(
                fixture_id=prediction.fixture_id,
                status="FT",
                home_score=2,
                away_score=0,
            ),
        )
        self.database.close()
        self.database = Database(self.database_path)
        reinitialized = SQLitePredictionResultRepository(self.database)

        self.assertEqual(resolved.status, ResolutionStatus.WON)
        self.assertEqual(
            reinitialized.get_resolved(prediction.prediction_id),
            resolved,
        )

    def test_history_retrieval_returns_all_terminal_results(self):
        predictions = (
            self.prediction("prediction-1", 500),
            self.prediction("prediction-2", 501, "AWAY"),
            self.prediction("prediction-3", 502, "DRAW"),
        )
        statuses = (
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        )
        for index, (prediction, status) in enumerate(
            zip(predictions, statuses, strict=True)
        ):
            self.repository.save_published(prediction)
            self.repository.store_if_absent(
                self.result(
                    status,
                    prediction.prediction_id,
                    prediction.fixture_id,
                    resolved_offset=index,
                )
            )

        history = self.repository.load_history()

        self.assertEqual(tuple(result.status for result in history), statuses)
        self.assertEqual(len(history), 3)

    def test_invalid_settlement_rolls_back_without_changing_pending_data(self):
        prediction = self.prediction()
        self.repository.save_published(prediction)
        mismatched = self.result(
            ResolutionStatus.WON,
            fixture_id=999,
        )

        with self.assertRaises(ValueError):
            self.repository.store_if_absent(mismatched)

        self.assertEqual(self.repository.load_pending(), (prediction,))
        self.assertEqual(self.repository.load_history(), ())


if __name__ == "__main__":
    unittest.main()
