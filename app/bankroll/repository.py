from typing import Protocol

from .exceptions import (
    ConcurrentBankrollUpdateError,
    ProductBankrollMismatchError,
)
from .models import BankrollAccount, BankrollProduct, BankrollTransaction


class BankrollRepository(Protocol):
    def load_account(self, product_id: BankrollProduct) -> BankrollAccount:
        ...

    def has_settlement(
        self,
        product_id: BankrollProduct,
        prediction_id: str,
    ) -> bool:
        ...

    def get_transaction(
        self,
        product_id: BankrollProduct,
        prediction_id: str,
    ) -> BankrollTransaction | None:
        ...

    def store_transaction(self, transaction: BankrollTransaction) -> bool:
        """Atomically update the account and store a new transaction."""
        ...

    def transaction_history(
        self,
        product_id: BankrollProduct,
    ) -> tuple[BankrollTransaction, ...]:
        ...


class InMemoryBankrollRepository:
    def __init__(self, accounts: tuple[BankrollAccount, ...]) -> None:
        self._accounts: dict[BankrollProduct, BankrollAccount] = {}
        for account in accounts:
            if account.product_id in self._accounts:
                raise ValueError("Each product may have only one bankroll account.")
            self._accounts[account.product_id] = account
        self._transactions: dict[
            tuple[BankrollProduct, str],
            BankrollTransaction,
        ] = {}

    def load_account(self, product_id: BankrollProduct) -> BankrollAccount:
        try:
            return self._accounts[product_id]
        except KeyError as error:
            raise ProductBankrollMismatchError(
                f"No bankroll account exists for {product_id.value}."
            ) from error

    def has_settlement(
        self,
        product_id: BankrollProduct,
        prediction_id: str,
    ) -> bool:
        return (product_id, prediction_id) in self._transactions

    def get_transaction(
        self,
        product_id: BankrollProduct,
        prediction_id: str,
    ) -> BankrollTransaction | None:
        return self._transactions.get((product_id, prediction_id))

    def store_transaction(self, transaction: BankrollTransaction) -> bool:
        key = (transaction.product_id, transaction.prediction_id)
        if key in self._transactions:
            return False
        account = self.load_account(transaction.product_id)
        if account.currency != transaction.currency:
            raise ProductBankrollMismatchError("Transaction currency is incorrect.")
        if account.balance != transaction.opening_balance:
            raise ConcurrentBankrollUpdateError(
                "Bankroll changed before the transaction could be stored."
            )
        if account.balance + transaction.profit_loss != transaction.closing_balance:
            raise ValueError("Transaction balances do not reconcile.")
        self._accounts[transaction.product_id] = BankrollAccount(
            product_id=account.product_id,
            currency=account.currency,
            starting_balance=account.starting_balance,
            balance=transaction.closing_balance,
        )
        self._transactions[key] = transaction
        return True

    def transaction_history(
        self,
        product_id: BankrollProduct,
    ) -> tuple[BankrollTransaction, ...]:
        return tuple(
            transaction
            for (stored_product, _), transaction in self._transactions.items()
            if stored_product is product_id
        )
