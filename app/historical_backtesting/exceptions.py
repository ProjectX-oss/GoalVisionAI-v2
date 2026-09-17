"""Typed failures at the historical-backtesting boundary."""


class HistoricalBacktestingError(Exception):
    pass


class BacktestRequestValidationError(HistoricalBacktestingError, ValueError):
    pass


class BacktestSourceError(HistoricalBacktestingError):
    pass


class BacktestPartitionSafetyError(BacktestSourceError):
    pass


class BacktestSchemaCompatibilityError(BacktestSourceError):
    pass


class BacktestOddsProvenanceError(HistoricalBacktestingError, ValueError):
    pass


class BacktestProbabilityContractError(HistoricalBacktestingError, ValueError):
    pass


class BacktestSettlementError(HistoricalBacktestingError, ValueError):
    pass


class BacktestConflictError(HistoricalBacktestingError):
    pass


class BacktestPersistenceError(HistoricalBacktestingError):
    pass
