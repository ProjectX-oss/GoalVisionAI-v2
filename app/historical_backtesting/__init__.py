"""Deterministic, immutable, TEST-only historical backtesting foundation."""

from .bankroll import (
    build_ledger,
    reproduce_final_bankroll,
    verify_bankroll_ledger,
)
from .betting_metrics import calculate_betting_metrics, reproduce_betting_metrics
from .factory import build_historical_backtesting_service
from .inspection import (
    inspect_backtest_prediction,
    inspect_backtest_selection,
    inspect_backtest_settlement,
    inspect_bankroll_entry,
    inspect_market_assessment,
    reproduce_all_betting_metrics,
    reproduce_all_predictive_metrics,
    summarize_backtest_run,
    verify_backtest_fingerprints,
    verify_backtest_read_model,
    verify_calibration_reproduction,
    verify_equal_kickoff_group_handling,
    verify_prediction_reproduction,
)
from .models import *
from .odds import (
    create_odds_dataset,
    odds_source_fingerprint,
    verify_and_select_odds,
    verify_odds_temporal_safety,
)
from .policy import *
from .predictive_metrics import (
    calculate_predictive_metrics,
    reproduce_predictive_metrics,
)
from .repository import SQLiteHistoricalBacktestingRepository
from .selection import verify_selection_policy_alignment
from .service import HistoricalBacktestingService, run_historical_backtest
from .settlement import (
    SQLiteHistoricalFinalScoreReader,
    settle_selection,
    verify_settlement_consistency,
)
from .source_verification import verify_test_partition_only

__all__ = [name for name in globals() if not name.startswith("_")]
