import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.bankroll import (
    DEFAULT_OFFICIAL_BANKROLL_CONFIG,
    BankrollProduct,
    BankrollTransaction,
    OfficialBankrollSettlementEngine,
    OfficialResultBankrollSettlementService,
    ProductBankrollMismatchError,
    StakeTier,
)
from app.database import (
    Database,
    SQLiteOfficialBankrollRepository,
    SQLitePredictionResultRepository,
)
from app.results import (
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
    SettlementReasonCode,
)


class PersistentOfficialBankrollTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = (
            Path("tests") / f".official-bankroll-{uuid4().hex}.db"
        )
        self.database: Database | None = None
        self.addCleanup(self._cleanup_database)
        self.now = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
        self._open()

    def _open(self) -> None:
        self.database = Database(self.database_path)
        self.repository = SQLiteOfficialBankrollRepository(
            self.database,
            DEFAULT_OFFICIAL_BANKROLL_CONFIG,
            clock=lambda: self.now,
        )
        self.engine = OfficialBankrollSettlementEngine(
            DEFAULT_OFFICIAL_BANKROLL_CONFIG,
            self.repository,
        )
        self.integration = OfficialResultBankrollSettlementService(self.engine)

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

    def result(
        self,
        status: ResolutionStatus,
        prediction_id: str = "prediction-1",
        fixture_id: int = 500,
        resolved_at: datetime | None = None,
    ) -> ResolvedPredictionResult:
        terminal = status in {
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        }
        reason = {
            ResolutionStatus.WON: SettlementReasonCode.MATCH_RESULT_SETTLED,
            ResolutionStatus.LOST: SettlementReasonCode.MATCH_RESULT_SETTLED,
            ResolutionStatus.VOID: SettlementReasonCode.FIXTURE_CANCELLED,
            ResolutionStatus.PENDING: SettlementReasonCode.MATCH_PENDING,
            ResolutionStatus.UNRESOLVED: SettlementReasonCode.MATCH_DATA_MISSING,
        }[status]
        return ResolvedPredictionResult(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            status=status,
            resolved_at=(resolved_at or self.now) if terminal else None,
            home_score=2 if status in {ResolutionStatus.WON, ResolutionStatus.LOST} else None,
            away_score=1 if status in {ResolutionStatus.WON, ResolutionStatus.LOST} else None,
            settlement_rule_version="match-winner-v1",
            reason_codes=(reason,),
        )

    def settle(
        self,
        status: ResolutionStatus,
        tier: StakeTier = StakeTier.STANDARD,
        odds: Decimal | None = Decimal("2.00"),
        prediction_id: str = "prediction-1",
        fixture_id: int = 500,
        resolved_at: datetime | None = None,
    ):
        return self.integration.settle_result(
            self.result(
                status,
                prediction_id,
                fixture_id,
                resolved_at,
            ),
            stake_tier=tier,
            odds=odds,
            evaluated_at=self.now,
        )

    def test_migration_creates_accounts_transactions_and_immutability(self):
        tables = {
            row["name"]
            for row in self.database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        triggers = {
            row["name"]
            for row in self.database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        versions = tuple(
            row["version"]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )

        self.assertIn("bankroll_accounts", tables)
        self.assertIn("bankroll_transactions", tables)
        self.assertIn("bankroll_transactions_no_update", triggers)
        self.assertIn("bankroll_transactions_no_delete", triggers)
        self.assertEqual(versions, tuple(range(1, 33)))

    def test_initializes_official_eur_10000_once(self):
        first = self.repository.load_account(BankrollProduct.OFFICIAL)
        first_created_at = self.database.connection.execute(
            "SELECT created_at FROM bankroll_accounts WHERE product_id = 'OFFICIAL'"
        ).fetchone()["created_at"]

        duplicate_repository = SQLiteOfficialBankrollRepository(
            self.database,
            DEFAULT_OFFICIAL_BANKROLL_CONFIG,
            clock=lambda: self.now + timedelta(days=1),
        )
        second = duplicate_repository.load_account(BankrollProduct.OFFICIAL)
        row = self.database.connection.execute(
            "SELECT COUNT(*) AS count, created_at FROM bankroll_accounts"
        ).fetchone()

        self.assertEqual(first.balance, Decimal("10000.00"))
        self.assertEqual(second, first)
        self.assertEqual(row["count"], 1)
        self.assertEqual(row["created_at"], first_created_at)

    def test_account_and_history_persist_across_repository_restart(self):
        expected = self.settle(ResolutionStatus.WON)

        self._restart()

        account = self.repository.load_account(BankrollProduct.OFFICIAL)
        history = self.repository.transaction_history(BankrollProduct.OFFICIAL)
        self.assertEqual(account.balance, Decimal("10100.00"))
        self.assertEqual(history, (expected.transaction,))
        self.assertTrue(
            self.repository.has_settlement(
                BankrollProduct.OFFICIAL,
                "prediction-1",
            )
        )

    def test_persists_winning_result_settlement(self):
        settlement = self.settle(
            ResolutionStatus.WON,
            StakeTier.STRONG,
            Decimal("1.85"),
        )

        self.assertEqual(settlement.transaction.stake, Decimal("200.00"))
        self.assertEqual(settlement.transaction.profit_loss, Decimal("170.00"))
        self.assertEqual(settlement.snapshot.balance, Decimal("10170.00"))
        row = self.database.connection.execute(
            "SELECT public_star_rating FROM bankroll_transactions"
        ).fetchone()
        self.assertEqual(row["public_star_rating"], 4)

    def test_persists_losing_result_settlement(self):
        settlement = self.settle(
            ResolutionStatus.LOST,
            StakeTier.ELITE,
            Decimal("1.90"),
        )

        self.assertEqual(settlement.transaction.profit_loss, Decimal("-300.00"))
        self.assertEqual(settlement.snapshot.balance, Decimal("9700.00"))
        self._restart()
        self.assertEqual(
            self.repository.load_account(BankrollProduct.OFFICIAL).balance,
            Decimal("9700.00"),
        )

    def test_persists_void_result_without_profit_or_loss(self):
        settlement = self.settle(
            ResolutionStatus.VOID,
            StakeTier.ELITE,
            Decimal("2.10"),
        )

        self.assertEqual(settlement.transaction.profit_loss, Decimal("0.00"))
        self.assertEqual(settlement.snapshot.balance, Decimal("10000.00"))
        self.assertEqual(len(self.repository.transaction_history(
            BankrollProduct.OFFICIAL
        )), 1)

    def test_pending_and_unresolved_create_no_financial_transactions(self):
        for index, status in enumerate(
            (ResolutionStatus.PENDING, ResolutionStatus.UNRESOLVED)
        ):
            response = self.settle(
                status,
                odds=None,
                prediction_id=f"prediction-{index}",
                fixture_id=500 + index,
            )
            self.assertFalse(response.applied)
            self.assertIsNone(response.transaction)

        self.assertEqual(
            self.repository.load_account(BankrollProduct.OFFICIAL).balance,
            Decimal("10000.00"),
        )
        self.assertEqual(
            self.repository.transaction_history(BankrollProduct.OFFICIAL),
            (),
        )

    def test_duplicate_settlement_is_prevented_after_restart(self):
        first = self.settle(ResolutionStatus.WON)
        self._restart()

        duplicate = self.settle(ResolutionStatus.WON)

        self.assertTrue(first.applied)
        self.assertFalse(duplicate.applied)
        self.assertEqual(duplicate.transaction, first.transaction)
        self.assertEqual(duplicate.snapshot.balance, Decimal("10100.00"))
        self.assertEqual(len(self.repository.transaction_history(
            BankrollProduct.OFFICIAL
        )), 1)

    def test_decimal_values_round_trip_as_text_without_precision_loss(self):
        settlement = self.settle(
            ResolutionStatus.WON,
            odds=Decimal("1.333"),
        )
        self._restart()
        transaction = self.repository.get_transaction(
            BankrollProduct.OFFICIAL,
            "prediction-1",
        )
        row = self.database.connection.execute(
            """
            SELECT typeof(decimal_odds) AS storage_type, decimal_odds,
                   profit_loss, closing_balance
            FROM bankroll_transactions
            """
        ).fetchone()

        self.assertEqual(transaction, settlement.transaction)
        self.assertEqual(row["storage_type"], "text")
        self.assertEqual(row["decimal_odds"], "1.333")
        self.assertEqual(row["profit_loss"], "33.30")
        self.assertEqual(row["closing_balance"], "10033.30")

    def test_transaction_history_is_ordered_by_settlement_time(self):
        later = self.now + timedelta(hours=2)
        earlier = self.now + timedelta(hours=1)
        self.settle(
            ResolutionStatus.WON,
            prediction_id="later",
            fixture_id=501,
            resolved_at=later,
        )
        self.settle(
            ResolutionStatus.LOST,
            prediction_id="earlier",
            fixture_id=502,
            resolved_at=earlier,
        )

        history = self.repository.transaction_history(BankrollProduct.OFFICIAL)

        self.assertEqual(
            tuple(transaction.prediction_id for transaction in history),
            ("earlier", "later"),
        )

    def test_invalid_settlement_rolls_back_account_and_history(self):
        invalid = BankrollTransaction(
            product_id=BankrollProduct.OFFICIAL,
            prediction_id="invalid",
            fixture_id=500,
            opening_balance=Decimal("10000.00"),
            stake=Decimal("100.00"),
            odds=Decimal("2.00"),
            gross_return=Decimal("200.00"),
            profit_loss=Decimal("100.00"),
            closing_balance=Decimal("10001.00"),
            settlement_status=ResolutionStatus.WON,
            stake_tier=StakeTier.STANDARD,
            settled_at=self.now,
            currency="EUR",
            rule_version="official-bankroll-v1",
        )

        with self.assertRaises(ValueError):
            self.repository.store_transaction(invalid)

        self.assertEqual(
            self.repository.load_account(BankrollProduct.OFFICIAL).balance,
            Decimal("10000.00"),
        )
        self.assertEqual(
            self.repository.transaction_history(BankrollProduct.OFFICIAL),
            (),
        )

    def test_database_rejects_silent_transaction_changes(self):
        self.settle(ResolutionStatus.WON)

        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection:
                self.database.connection.execute(
                    "UPDATE bankroll_transactions SET profit_loss = '0.00'"
                )

        stored = self.repository.get_transaction(
            BankrollProduct.OFFICIAL,
            "prediction-1",
        )
        self.assertEqual(stored.profit_loss, Decimal("100.00"))

    def test_only_official_product_is_enabled(self):
        for product in (
            BankrollProduct.LIVE,
            BankrollProduct.HIGH_RISK,
            BankrollProduct.COMBO,
            BankrollProduct.LAB,
        ):
            with self.subTest(product=product):
                with self.assertRaises(ProductBankrollMismatchError):
                    self.repository.load_account(product)
        rows = self.database.connection.execute(
            "SELECT product_id FROM bankroll_accounts"
        ).fetchall()
        self.assertEqual(tuple(row["product_id"] for row in rows), ("OFFICIAL",))

    def test_existing_prediction_result_history_is_preserved(self):
        result_repository = SQLitePredictionResultRepository(self.database)
        prediction = PublishedPredictionReference(
            prediction_id="prediction-1",
            fixture_id=500,
            market="Match Winner",
            selection="HOME",
            published_at=self.now - timedelta(hours=2),
            odds=2.0,
            stake=100.0,
        )
        resolved = self.result(ResolutionStatus.WON)
        result_repository.save_published(prediction)
        result_repository.store_if_absent(resolved)

        self.settle(ResolutionStatus.WON)

        self.assertEqual(result_repository.get_resolved("prediction-1"), resolved)
        self.assertEqual(len(result_repository.load_history()), 1)
        self.assertEqual(len(self.repository.transaction_history(
            BankrollProduct.OFFICIAL
        )), 1)


if __name__ == "__main__":
    unittest.main()
