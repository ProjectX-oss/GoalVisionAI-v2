"""Immutable-score Official single-market settlement rules."""

from __future__ import annotations

from decimal import Decimal

from app.database import Database

from .exceptions import BacktestSettlementError
from .fingerprint import sha256_fingerprint
from .models import BacktestSettlement, SettlementStatus, SupportedMarket


class SQLiteHistoricalFinalScoreReader:
    def __init__(self, database: Database):
        self._connection = database.connection

    def load_final_score(self, historical_match_id: str) -> tuple[int, int] | None:
        row = self._connection.execute(
            "SELECT full_time_home_score,full_time_away_score FROM historical_matches WHERE historical_match_id=?",
            (historical_match_id,),
        ).fetchone()
        return (row[0], row[1]) if row else None


def settle_selection(selection, final_score, policy, settled_order, *, run_namespace=""):
    if final_score is None:
        raise BacktestSettlementError("Immutable final score is missing.")
    home, away = final_score
    if type(home) is not int or type(away) is not int or not 0 <= home <= 30 or not 0 <= away <= 30:
        raise BacktestSettlementError("Immutable final score is malformed.")
    won = _won(selection.market_identity, home, away)
    status = SettlementStatus.WON if won else SettlementStatus.LOST
    stake = selection.applied_stake_amount
    gross = stake * selection.decimal_odds if won else Decimal(0)
    net = gross - stake
    fingerprint = sha256_fingerprint(
        {
            "selection_fingerprint": selection.selection_fingerprint,
            "final_score": (home, away), "settlement_rule": policy.settlement_policy_version,
            "status": status, "gross_return": gross, "net_profit_loss": net,
        }
    )
    return BacktestSettlement(
        settlement_id=f"historical-backtest-settlement-{sha256_fingerprint((run_namespace, fingerprint))}",
        selection_id=selection.selection_id, final_home_score=home,
        final_away_score=away, status=status, gross_return=gross,
        net_profit_loss=net, settlement_reason=f"{selection.market_identity.value}_{status.value}",
        settlement_fingerprint=fingerprint, settled_order=settled_order,
    )


def verify_settlement_consistency(selections, settlements, policy, *, run_namespace="") -> tuple[str, ...]:
    by_id = {item.selection_id: item for item in selections}
    failures = []
    for item in settlements:
        selection = by_id.get(item.selection_id)
        if selection is None:
            failures.append(f"{item.settlement_id}:SELECTION_NOT_FOUND")
            continue
        expected = settle_selection(
            selection, (item.final_home_score, item.final_away_score), policy,
            item.settled_order, run_namespace=run_namespace,
        )
        if expected != item:
            failures.append(f"{item.settlement_id}:SETTLEMENT_MISMATCH")
    return tuple(failures)


def _won(market: SupportedMarket, home: int, away: int) -> bool:
    total = home + away
    mapping = {
        SupportedMarket.HOME_WIN: home > away,
        SupportedMarket.DRAW: home == away,
        SupportedMarket.AWAY_WIN: away > home,
        SupportedMarket.OVER_1_5: total > 1.5,
        SupportedMarket.UNDER_1_5: total < 1.5,
        SupportedMarket.OVER_2_5: total > 2.5,
        SupportedMarket.UNDER_2_5: total < 2.5,
        SupportedMarket.OVER_3_5: total > 3.5,
        SupportedMarket.UNDER_3_5: total < 3.5,
        SupportedMarket.BTTS_YES: home > 0 and away > 0,
        SupportedMarket.BTTS_NO: home == 0 or away == 0,
    }
    return mapping[market]
