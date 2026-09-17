import unittest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.bankroll import (
    DEFAULT_OFFICIAL_BANKROLL_CONFIG,
    BankrollProduct,
    OfficialBankrollSettlementEngine,
    OfficialResultBankrollSettlementService,
    StakeTier,
)
from app.database import (
    Database,
    SQLiteOfficialBankrollRepository,
    SQLitePredictionResultRepository,
)
from app.results import (
    DEFAULT_FIXTURE_STATUS_POLICY,
    DEFAULT_MARKET_SETTLEMENT_REGISTRY,
    FinishedMatchResult,
    PredictionResultResolutionService,
    PredictionResultResolver,
    PublishedPredictionReference,
)
from app.settlement import (
    AutomaticPredictionSettlementOrchestrator,
    SettlementBatchRequest,
    SettlementFailureReasonCode,
    SettlementOutcomeState,
)


class FakeFixtureResultProvider:
    def __init__(self) -> None:
        self.responses: dict[int, tuple[FinishedMatchResult, ...] | Exception] = {}
        self.calls: list[int] = []

    def load_fixture(self, fixture_id: int) -> tuple[FinishedMatchResult, ...]:
        self.calls.append(fixture_id)
        response = self.responses.get(fixture_id, ())
        if isinstance(response, Exception):
            raise response
        return response


class DelegatingResultRepository:
    def __init__(self, inner: SQLitePredictionResultRepository) -> None:
        self.inner = inner

    def save_published(self, prediction):
        return self.inner.save_published(prediction)

    def load_pending(self):
        return self.inner.load_pending()

    def get_published(self, prediction_id):
        return self.inner.get_published(prediction_id)

    def get_resolved(self, prediction_id):
        return self.inner.get_resolved(prediction_id)

    def store_if_absent(self, result):
        return self.inner.store_if_absent(result)

    def load_history(self):
        return self.inner.load_history()


class DuplicatePendingResultRepository(DelegatingResultRepository):
    def load_pending(self):
        pending = self.inner.load_pending()
        return pending + pending[:1]


class FailingResultRepository(DelegatingResultRepository):
    def __init__(
        self,
        inner: SQLitePredictionResultRepository,
        prediction_id: str,
    ) -> None:
        super().__init__(inner)
        self.prediction_id = prediction_id

    def store_if_absent(self, result):
        if result.prediction_id == self.prediction_id:
            raise RuntimeError("forced result persistence failure")
        return self.inner.store_if_absent(result)


class FailOnceBankrollRepository:
    def __init__(self, inner: SQLiteOfficialBankrollRepository) -> None:
        self.inner = inner
        self.failed = False

    def load_account(self, product_id):
        return self.inner.load_account(product_id)

    def has_settlement(self, product_id, prediction_id):
        return self.inner.has_settlement(product_id, prediction_id)

    def get_transaction(self, product_id, prediction_id):
        return self.inner.get_transaction(product_id, prediction_id)

    def store_transaction(self, transaction):
        if not self.failed:
            self.failed = True
            raise RuntimeError("forced bankroll persistence failure")
        return self.inner.store_transaction(transaction)

    def transaction_history(self, product_id):
        return self.inner.transaction_history(product_id)


class AutomaticSettlementOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = (
            Path("tests") / f".settlement-orchestrator-{uuid4().hex}.db"
        )
        self.database: Database | None = None
        self.addCleanup(self._cleanup_database)
        self.now = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
        self.completed_at = self.now + timedelta(seconds=1)
        self.provider = FakeFixtureResultProvider()
        self._open()

    def _open(self) -> None:
        self.database = Database(self.database_path)
        self.result_repository = SQLitePredictionResultRepository(self.database)
        self.bankroll_repository = SQLiteOfficialBankrollRepository(
            self.database,
            DEFAULT_OFFICIAL_BANKROLL_CONFIG,
            clock=lambda: self.now,
        )
        self._compose(
            self.result_repository,
            self.bankroll_repository,
        )

    def _compose(self, result_repository, bankroll_repository) -> None:
        resolution = PredictionResultResolutionService(
            resolver=PredictionResultResolver(
                DEFAULT_FIXTURE_STATUS_POLICY,
                DEFAULT_MARKET_SETTLEMENT_REGISTRY,
            ),
            repository=result_repository,
            clock=lambda: self.now,
        )
        bankroll = OfficialResultBankrollSettlementService(
            OfficialBankrollSettlementEngine(
                DEFAULT_OFFICIAL_BANKROLL_CONFIG,
                bankroll_repository,
            )
        )
        self.orchestrator = AutomaticPredictionSettlementOrchestrator(
            result_repository=result_repository,
            result_resolution=resolution,
            bankroll_repository=bankroll_repository,
            bankroll_settlement=bankroll,
            fixture_results=self.provider,
            clock=lambda: self.completed_at,
        )

    def _restart(self) -> None:
        if self.database is not None:
            self.database.close()
        self._open()

    def _cleanup_database(self) -> None:
        if self.database is not None:
            self.database.close()
        for suffix in ("", "-journal", "-shm", "-wal"):
            path = Path(f"{self.database_path}{suffix}")
            if path.exists():
                path.unlink()

    def publish(
        self,
        prediction_id: str = "prediction-1",
        fixture_id: int = 500,
        selection: str = "HOME",
        odds: float = 2.0,
    ) -> PublishedPredictionReference:
        prediction = PublishedPredictionReference(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            market="Match Winner",
            selection=selection,
            published_at=self.now - timedelta(hours=2),
            odds=odds,
            stake=None,
        )
        self.result_repository.save_published(prediction)
        return prediction

    def request(self, *prediction_ids: str) -> SettlementBatchRequest:
        return SettlementBatchRequest(
            requested_at=self.now,
            stake_tiers=tuple(
                (prediction_id, StakeTier.STANDARD)
                for prediction_id in prediction_ids
            ),
        )

    @staticmethod
    def fixture(
        fixture_id: int,
        home_score: int | None,
        away_score: int | None,
        status: str = "FT",
    ) -> FinishedMatchResult:
        return FinishedMatchResult(
            fixture_id=fixture_id,
            status=status,
            home_score=home_score,
            away_score=away_score,
        )

    def test_successful_won_settlement(self):
        self.publish()
        self.provider.responses[500] = (self.fixture(500, 2, 1),)

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.processed_count, 1)
        self.assertEqual(report.settled_count, 1)
        self.assertEqual(report.won_count, 1)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(report.outcomes[0].state, SettlementOutcomeState.SETTLED)
        self.assertEqual(
            self.bankroll_repository.load_account(
                BankrollProduct.OFFICIAL
            ).balance,
            10100,
        )
        self.assertEqual(report.rule_version, "automatic-settlement-v1")
        self.assertEqual(report.completed_at, self.completed_at)

    def test_successful_lost_settlement(self):
        self.publish()
        self.provider.responses[500] = (self.fixture(500, 0, 1),)

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.lost_count, 1)
        self.assertEqual(
            self.bankroll_repository.load_account(
                BankrollProduct.OFFICIAL
            ).balance,
            9900,
        )

    def test_successful_void_settlement(self):
        self.publish()
        self.provider.responses[500] = (
            self.fixture(500, None, None, "CANC"),
        )

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.void_count, 1)
        self.assertEqual(
            self.bankroll_repository.load_account(
                BankrollProduct.OFFICIAL
            ).balance,
            10000,
        )

    def test_unfinished_fixture_remains_pending(self):
        self.publish()
        self.provider.responses[500] = (
            self.fixture(500, None, None, "NS"),
        )

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.pending_count, 1)
        self.assertEqual(report.settled_count, 0)
        self.assertEqual(len(self.result_repository.load_pending()), 1)
        self.assertEqual(
            self.bankroll_repository.transaction_history(
                BankrollProduct.OFFICIAL
            ),
            (),
        )

    def test_missing_fixture_result_remains_unresolved(self):
        self.publish()

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.unresolved_count, 1)
        self.assertIn(
            SettlementFailureReasonCode.FIXTURE_RESULT_MISSING,
            report.outcomes[0].reason_codes,
        )
        self.assertEqual(len(self.result_repository.load_pending()), 1)

    def test_duplicate_prediction_input_is_skipped(self):
        self.publish()
        self.provider.responses[500] = (self.fixture(500, 2, 1),)
        duplicate_repository = DuplicatePendingResultRepository(
            self.result_repository
        )
        self._compose(duplicate_repository, self.bankroll_repository)

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.settled_count, 1)
        self.assertEqual(report.skipped_duplicates, 1)
        self.assertEqual(
            sum(
                outcome.state is SettlementOutcomeState.SKIPPED
                for outcome in report.outcomes
            ),
            1,
        )
        self.assertEqual(self.provider.calls, [500])

    def test_duplicate_fixture_response_is_deduplicated(self):
        self.publish()
        fixture = self.fixture(500, 2, 1)
        self.provider.responses[500] = (fixture, fixture)

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.settled_count, 1)
        self.assertEqual(report.skipped_duplicates, 1)
        self.assertIn(
            SettlementFailureReasonCode.DUPLICATE_FIXTURE_RESPONSE,
            report.outcomes[0].reason_codes,
        )
        self.assertEqual(self.provider.calls, [500])

    def test_repeated_batch_execution_is_idempotent(self):
        self.publish()
        self.provider.responses[500] = (self.fixture(500, 2, 1),)
        first = self.orchestrator.settle_pending(self.request("prediction-1"))

        repeated = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(first.settled_count, 1)
        self.assertEqual(repeated.processed_count, 0)
        self.assertEqual(len(self.bankroll_repository.transaction_history(
            BankrollProduct.OFFICIAL
        )), 1)

    def test_result_persistence_failure_prevents_bankroll_settlement(self):
        self.publish()
        self.provider.responses[500] = (self.fixture(500, 2, 1),)
        failing_repository = FailingResultRepository(
            self.result_repository,
            "prediction-1",
        )
        self._compose(failing_repository, self.bankroll_repository)

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.failed_count, 1)
        self.assertIn(
            SettlementFailureReasonCode.RESULT_PERSISTENCE_FAILED,
            report.outcomes[0].reason_codes,
        )
        self.assertIsNone(self.result_repository.get_resolved("prediction-1"))
        self.assertEqual(
            self.bankroll_repository.transaction_history(
                BankrollProduct.OFFICIAL
            ),
            (),
        )

    def test_bankroll_failure_after_result_persistence_recovers_next_run(self):
        self.publish()
        self.provider.responses[500] = (self.fixture(500, 2, 1),)
        failing_bankroll = FailOnceBankrollRepository(
            self.bankroll_repository
        )
        self._compose(self.result_repository, failing_bankroll)

        failed = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(failed.failed_count, 1)
        self.assertIsNotNone(self.result_repository.get_resolved("prediction-1"))
        self.assertEqual(
            self.bankroll_repository.transaction_history(
                BankrollProduct.OFFICIAL
            ),
            (),
        )

        self._compose(self.result_repository, self.bankroll_repository)
        recovered = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(recovered.settled_count, 1)
        self.assertEqual(len(self.bankroll_repository.transaction_history(
            BankrollProduct.OFFICIAL
        )), 1)

    def test_mixed_successful_and_failed_batch_is_isolated(self):
        for prediction_id, fixture_id in (
            ("won", 500),
            ("provider-failure", 501),
            ("missing", 502),
        ):
            self.publish(prediction_id, fixture_id)
        self.provider.responses[500] = (self.fixture(500, 2, 1),)
        self.provider.responses[501] = RuntimeError("fixture unavailable")

        report = self.orchestrator.settle_pending(
            self.request("won", "provider-failure", "missing")
        )

        self.assertEqual(report.settled_count, 1)
        self.assertEqual(report.failed_count, 1)
        self.assertEqual(report.unresolved_count, 1)
        self.assertEqual(
            self.bankroll_repository.load_account(
                BankrollProduct.OFFICIAL
            ).balance,
            10100,
        )

    def test_restart_idempotency_preserves_single_settlement(self):
        self.publish()
        self.provider.responses[500] = (self.fixture(500, 2, 1),)
        self.orchestrator.settle_pending(self.request("prediction-1"))
        self._restart()

        report = self.orchestrator.settle_pending(self.request("prediction-1"))

        self.assertEqual(report.processed_count, 0)
        self.assertEqual(
            self.bankroll_repository.load_account(
                BankrollProduct.OFFICIAL
            ).balance,
            10100,
        )
        self.assertEqual(len(self.result_repository.load_history()), 1)
        self.assertEqual(len(self.bankroll_repository.transaction_history(
            BankrollProduct.OFFICIAL
        )), 1)

    def test_no_network_or_telegram_calls(self):
        self.publish()
        self.provider.responses[500] = (self.fixture(500, 2, 1),)

        with (
            patch("telegram.Bot.send_message") as send_message,
            patch("httpx.Client.get") as sync_get,
            patch("httpx.AsyncClient.get") as async_get,
        ):
            report = self.orchestrator.settle_pending(
                self.request("prediction-1")
            )

        self.assertEqual(report.settled_count, 1)
        send_message.assert_not_called()
        sync_get.assert_not_called()
        async_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
