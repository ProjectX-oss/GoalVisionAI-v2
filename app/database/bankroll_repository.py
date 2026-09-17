import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.bankroll import (
    BankrollAccount,
    BankrollConfig,
    BankrollProduct,
    BankrollTransaction,
    ConcurrentBankrollUpdateError,
    ProductBankrollMismatchError,
    StakeTier,
)
from app.results import ResolutionStatus

from .database import Database
from .migrations import MigrationManager


class SQLiteOfficialBankrollRepository:
    """Persists the single Official account and immutable transactions."""

    def __init__(
        self,
        database: Database,
        config: BankrollConfig,
        migrate: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._database = database
        self._connection = database.connection
        self._config = config
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if migrate:
            MigrationManager(self._connection).migrate()
        self._initialize_official_account()

    def load_account(self, product_id: BankrollProduct) -> BankrollAccount:
        self._validate_product(product_id)
        row = self._connection.execute(
            """
            SELECT product_id, currency, starting_balance, current_balance
            FROM bankroll_accounts
            WHERE product_id = ?
            """,
            (product_id.value,),
        ).fetchone()
        if row is None:
            raise ProductBankrollMismatchError("Official bankroll is missing.")
        account = BankrollAccount(
            product_id=BankrollProduct(row["product_id"]),
            currency=row["currency"],
            starting_balance=self._decimal(row["starting_balance"]),
            balance=self._decimal(row["current_balance"]),
        )
        if (
            account.currency != self._config.currency
            or account.starting_balance != self._config.starting_balance
        ):
            raise ProductBankrollMismatchError(
                "Stored Official bankroll does not match its configuration."
            )
        return account

    def has_settlement(
        self,
        product_id: BankrollProduct,
        prediction_id: str,
    ) -> bool:
        return self.get_transaction(product_id, prediction_id) is not None

    def get_transaction(
        self,
        product_id: BankrollProduct,
        prediction_id: str,
    ) -> BankrollTransaction | None:
        self._validate_product(product_id)
        row = self._connection.execute(
            """
            SELECT *
            FROM bankroll_transactions
            WHERE product_id = ? AND prediction_id = ?
            """,
            (product_id.value, prediction_id),
        ).fetchone()
        return self._transaction_from_row(row) if row is not None else None

    def store_transaction(self, transaction: BankrollTransaction) -> bool:
        self._validate_transaction(transaction)
        if self.has_settlement(transaction.product_id, transaction.prediction_id):
            return False
        try:
            with self._connection:
                account_update = self._connection.execute(
                    """
                    UPDATE bankroll_accounts
                    SET current_balance = ?, updated_at = ?, rule_version = ?
                    WHERE product_id = ? AND current_balance = ?
                    """,
                    (
                        self._encode_decimal(transaction.closing_balance),
                        self._timestamp(transaction.settled_at),
                        transaction.rule_version,
                        transaction.product_id.value,
                        self._encode_decimal(transaction.opening_balance),
                    ),
                )
                if account_update.rowcount != 1:
                    if self.has_settlement(
                        transaction.product_id,
                        transaction.prediction_id,
                    ):
                        return False
                    raise ConcurrentBankrollUpdateError(
                        "Official bankroll changed before settlement storage."
                    )
                self._connection.execute(
                    """
                    INSERT INTO bankroll_transactions (
                        product_id,
                        prediction_id,
                        fixture_id,
                        stake_tier,
                        public_star_rating,
                        opening_balance,
                        stake_amount,
                        decimal_odds,
                        gross_return,
                        profit_loss,
                        closing_balance,
                        settlement_status,
                        settled_at,
                        created_at,
                        rule_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transaction.product_id.value,
                        transaction.prediction_id,
                        transaction.fixture_id,
                        transaction.stake_tier.value,
                        self._config.stars_for(transaction.stake_tier),
                        self._encode_decimal(transaction.opening_balance),
                        self._encode_decimal(transaction.stake),
                        self._encode_decimal(transaction.odds),
                        self._encode_decimal(transaction.gross_return),
                        self._encode_decimal(transaction.profit_loss),
                        self._encode_decimal(transaction.closing_balance),
                        transaction.settlement_status.value,
                        self._timestamp(transaction.settled_at),
                        self._timestamp(self._now()),
                        transaction.rule_version,
                    ),
                )
        except sqlite3.IntegrityError as error:
            existing = self.get_transaction(
                transaction.product_id,
                transaction.prediction_id,
            )
            if existing is not None:
                return False
            raise ValueError("Bankroll transaction could not be stored.") from error
        return True

    def transaction_history(
        self,
        product_id: BankrollProduct,
    ) -> tuple[BankrollTransaction, ...]:
        self._validate_product(product_id)
        rows = self._connection.execute(
            """
            SELECT *
            FROM bankroll_transactions
            WHERE product_id = ?
            ORDER BY settled_at, transaction_id
            """,
            (product_id.value,),
        ).fetchall()
        return tuple(self._transaction_from_row(row) for row in rows)

    def _initialize_official_account(self) -> None:
        timestamp = self._timestamp(self._now())
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO bankroll_accounts (
                    product_id,
                    currency,
                    starting_balance,
                    current_balance,
                    created_at,
                    updated_at,
                    rule_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO NOTHING
                """,
                (
                    self._config.product_id.value,
                    self._config.currency,
                    self._encode_decimal(self._config.starting_balance),
                    self._encode_decimal(self._config.starting_balance),
                    timestamp,
                    timestamp,
                    self._config.rule_version,
                ),
            )
        self.load_account(BankrollProduct.OFFICIAL)

    def _validate_transaction(self, transaction: BankrollTransaction) -> None:
        self._validate_product(transaction.product_id)
        account = self.load_account(transaction.product_id)
        if transaction.currency != self._config.currency:
            raise ProductBankrollMismatchError("Transaction currency is incorrect.")
        if transaction.opening_balance != account.balance:
            raise ConcurrentBankrollUpdateError(
                "Transaction opening balance is not current."
            )
        if transaction.closing_balance != (
            transaction.opening_balance + transaction.profit_loss
        ):
            raise ValueError("Transaction balances do not reconcile.")

    def _transaction_from_row(self, row: sqlite3.Row) -> BankrollTransaction:
        product_id = BankrollProduct(row["product_id"])
        self._validate_product(product_id)
        tier = StakeTier(row["stake_tier"])
        if row["public_star_rating"] != self._config.stars_for(tier):
            raise ValueError("Stored public star rating is invalid.")
        return BankrollTransaction(
            product_id=product_id,
            prediction_id=row["prediction_id"],
            fixture_id=row["fixture_id"],
            opening_balance=self._decimal(row["opening_balance"]),
            stake=self._decimal(row["stake_amount"]),
            odds=self._decimal(row["decimal_odds"]),
            gross_return=self._decimal(row["gross_return"]),
            profit_loss=self._decimal(row["profit_loss"]),
            closing_balance=self._decimal(row["closing_balance"]),
            settlement_status=ResolutionStatus(row["settlement_status"]),
            stake_tier=tier,
            settled_at=datetime.fromisoformat(row["settled_at"]),
            currency=self._config.currency,
            rule_version=row["rule_version"],
        )

    def _validate_product(self, product_id: BankrollProduct) -> None:
        if product_id is not BankrollProduct.OFFICIAL:
            raise ProductBankrollMismatchError(
                "Persistent bankroll storage supports Official only."
            )

    def _now(self) -> datetime:
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            raise ValueError("Repository clock must be timezone-aware.")
        return timestamp

    @staticmethod
    def _timestamp(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("Stored timestamps must be timezone-aware.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _encode_decimal(value: Decimal) -> str:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise TypeError("Stored monetary values must be finite Decimals.")
        return format(value, "f")

    @staticmethod
    def _decimal(value: str) -> Decimal:
        try:
            decoded = Decimal(value)
        except (InvalidOperation, TypeError) as error:
            raise ValueError("Stored Decimal value is invalid.") from error
        if not decoded.is_finite():
            raise ValueError("Stored Decimal value must be finite.")
        return decoded
