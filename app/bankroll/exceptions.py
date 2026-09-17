class BankrollError(ValueError):
    """Base error for deterministic bankroll operations."""


class ProductBankrollMismatchError(BankrollError):
    pass


class InvalidOddsError(BankrollError):
    pass


class InsufficientBalanceError(BankrollError):
    pass


class ConcurrentBankrollUpdateError(BankrollError):
    pass
