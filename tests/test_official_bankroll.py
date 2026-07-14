import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

from app.bankroll import (
    DEFAULT_OFFICIAL_BANKROLL_CONFIG,
    BankrollAccount,
    BankrollProduct,
    BankrollSettlementInput,
    InMemoryBankrollRepository,
    InsufficientBalanceError,
    InvalidOddsError,
    OfficialBankrollSettlementEngine,
    ProductBankrollMismatchError,
    StakeTier,
    create_official_account,
)
from app.results import ResolutionStatus


class OfficialBankrollSettlementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DEFAULT_OFFICIAL_BANKROLL_CONFIG
        self.official_account = create_official_account(self.config)
        self.repository = InMemoryBankrollRepository((self.official_account,))
        self.engine = OfficialBankrollSettlementEngine(
            self.config,
            self.repository,
        )
        self.settled_at = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)

    def settlement(
        self,
        status: ResolutionStatus,
        tier: StakeTier = StakeTier.STANDARD,
        odds: Decimal | None = Decimal("2.00"),
        prediction_id: str = "prediction-1",
        fixture_id: int = 500,
        product_id: BankrollProduct = BankrollProduct.OFFICIAL,
    ) -> BankrollSettlementInput:
        return BankrollSettlementInput(
            product_id=product_id,
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            status=status,
            stake_tier=tier,
            odds=odds,
            settled_at=self.settled_at,
        )

    def test_official_bankroll_starts_at_eur_10000(self):
        snapshot = self.engine.snapshot(self.settled_at)

        self.assertEqual(snapshot.product_id, BankrollProduct.OFFICIAL)
        self.assertEqual(snapshot.currency, "EUR")
        self.assertEqual(snapshot.starting_balance, Decimal("10000.00"))
        self.assertEqual(snapshot.balance, Decimal("10000.00"))
        self.assertEqual(snapshot.transaction_count, 0)

    def test_explicit_stake_tiers_calculate_one_two_and_three_percent(self):
        expected = {
            StakeTier.STANDARD: (Decimal("0.01"), Decimal("100.00"), 3),
            StakeTier.STRONG: (Decimal("0.02"), Decimal("200.00"), 4),
            StakeTier.ELITE: (Decimal("0.03"), Decimal("300.00"), 5),
        }

        for tier, (percentage, stake, stars) in expected.items():
            with self.subTest(tier=tier):
                recommendation = self.engine.recommend_stake(tier)
                self.assertEqual(recommendation.percentage, percentage)
                self.assertEqual(recommendation.stake, stake)
                self.assertEqual(recommendation.public_stars, stars)

    def test_winning_settlement_returns_stake_and_profit(self):
        result = self.engine.settle(
            self.settlement(ResolutionStatus.WON, odds=Decimal("1.85"))
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.transaction.stake, Decimal("100.00"))
        self.assertEqual(result.transaction.gross_return, Decimal("185.00"))
        self.assertEqual(result.transaction.profit_loss, Decimal("85.00"))
        self.assertEqual(result.snapshot.balance, Decimal("10085.00"))

    def test_losing_settlement_subtracts_stake(self):
        result = self.engine.settle(
            self.settlement(
                ResolutionStatus.LOST,
                tier=StakeTier.STRONG,
                odds=Decimal("1.80"),
            )
        )

        self.assertEqual(result.transaction.stake, Decimal("200.00"))
        self.assertEqual(result.transaction.gross_return, Decimal("0.00"))
        self.assertEqual(result.transaction.profit_loss, Decimal("-200.00"))
        self.assertEqual(result.snapshot.balance, Decimal("9800.00"))

    def test_void_settlement_returns_stake_without_profit_or_loss(self):
        result = self.engine.settle(
            self.settlement(
                ResolutionStatus.VOID,
                tier=StakeTier.ELITE,
                odds=Decimal("2.10"),
            )
        )

        self.assertEqual(result.transaction.stake, Decimal("300.00"))
        self.assertEqual(result.transaction.gross_return, Decimal("300.00"))
        self.assertEqual(result.transaction.profit_loss, Decimal("0.00"))
        self.assertEqual(result.snapshot.balance, Decimal("10000.00"))

    def test_pending_and_unresolved_do_not_change_bankroll(self):
        for index, status in enumerate(
            (ResolutionStatus.PENDING, ResolutionStatus.UNRESOLVED)
        ):
            with self.subTest(status=status):
                result = self.engine.settle(
                    self.settlement(
                        status,
                        odds=None,
                        prediction_id=f"prediction-{index}",
                    )
                )
                self.assertFalse(result.applied)
                self.assertIsNone(result.transaction)
                self.assertEqual(result.snapshot.balance, Decimal("10000.00"))
        self.assertEqual(
            self.repository.transaction_history(BankrollProduct.OFFICIAL),
            (),
        )

    def test_money_rounding_is_decimal_half_up(self):
        account = BankrollAccount(
            product_id=BankrollProduct.OFFICIAL,
            currency="EUR",
            starting_balance=Decimal("10000.00"),
            balance=Decimal("100.55"),
        )
        repository = InMemoryBankrollRepository((account,))
        engine = OfficialBankrollSettlementEngine(self.config, repository)

        recommendation = engine.recommend_stake(StakeTier.STANDARD)
        result = engine.settle(
            self.settlement(ResolutionStatus.WON, odds=Decimal("1.333"))
        )

        self.assertEqual(recommendation.stake, Decimal("1.01"))
        self.assertEqual(result.transaction.gross_return, Decimal("1.35"))
        self.assertEqual(result.transaction.profit_loss, Decimal("0.34"))
        self.assertEqual(result.snapshot.balance, Decimal("100.89"))

    def test_duplicate_settlement_does_not_update_twice(self):
        settlement = self.settlement(ResolutionStatus.WON)
        first = self.engine.settle(settlement)

        duplicate = self.engine.settle(
            self.settlement(
                ResolutionStatus.LOST,
                fixture_id=999,
            )
        )

        self.assertTrue(first.applied)
        self.assertFalse(duplicate.applied)
        self.assertEqual(duplicate.transaction, first.transaction)
        self.assertEqual(duplicate.status, ResolutionStatus.WON)
        self.assertEqual(duplicate.fixture_id, 500)
        self.assertEqual(duplicate.snapshot.balance, Decimal("10100.00"))
        self.assertEqual(len(self.repository.transaction_history(
            BankrollProduct.OFFICIAL
        )), 1)

    def test_insufficient_balance_is_rejected(self):
        account = BankrollAccount(
            product_id=BankrollProduct.OFFICIAL,
            currency="EUR",
            starting_balance=Decimal("10000.00"),
            balance=Decimal("0.01"),
        )
        engine = OfficialBankrollSettlementEngine(
            self.config,
            InMemoryBankrollRepository((account,)),
        )

        with self.assertRaises(InsufficientBalanceError):
            engine.recommend_stake(StakeTier.STANDARD)

    def test_invalid_terminal_odds_are_rejected_without_transaction(self):
        for odds in (None, Decimal("0"), Decimal("1.00")):
            with self.subTest(odds=odds):
                with self.assertRaises(InvalidOddsError):
                    self.engine.settle(
                        self.settlement(ResolutionStatus.WON, odds=odds)
                    )
        self.assertEqual(
            self.repository.transaction_history(BankrollProduct.OFFICIAL),
            (),
        )

    def test_transaction_history_is_immutable(self):
        result = self.engine.settle(self.settlement(ResolutionStatus.WON))
        history = self.repository.transaction_history(BankrollProduct.OFFICIAL)

        self.assertIsInstance(history, tuple)
        self.assertEqual(history, (result.transaction,))
        with self.assertRaises(FrozenInstanceError):
            history[0].closing_balance = Decimal("0.00")

    def test_product_bankrolls_remain_separate(self):
        high_risk = BankrollAccount(
            product_id=BankrollProduct.HIGH_RISK,
            currency="EUR",
            starting_balance=Decimal("500.00"),
            balance=Decimal("500.00"),
        )
        repository = InMemoryBankrollRepository(
            (self.official_account, high_risk)
        )
        engine = OfficialBankrollSettlementEngine(self.config, repository)

        engine.settle(self.settlement(ResolutionStatus.WON))

        self.assertEqual(
            repository.load_account(BankrollProduct.HIGH_RISK).balance,
            Decimal("500.00"),
        )
        self.assertEqual(
            repository.transaction_history(BankrollProduct.HIGH_RISK),
            (),
        )
        with self.assertRaises(ProductBankrollMismatchError):
            engine.settle(
                self.settlement(
                    ResolutionStatus.WON,
                    product_id=BankrollProduct.HIGH_RISK,
                )
            )

    def test_same_inputs_produce_deterministic_output(self):
        settlement = self.settlement(
            ResolutionStatus.WON,
            tier=StakeTier.ELITE,
            odds=Decimal("1.87"),
        )
        first_engine = OfficialBankrollSettlementEngine(
            self.config,
            InMemoryBankrollRepository((self.official_account,)),
        )
        second_engine = OfficialBankrollSettlementEngine(
            self.config,
            InMemoryBankrollRepository((self.official_account,)),
        )

        self.assertEqual(
            first_engine.settle(settlement),
            second_engine.settle(settlement),
        )


if __name__ == "__main__":
    unittest.main()
