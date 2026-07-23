"""Deterministic isolated-bankroll ledger for chronological kickoff groups."""

from __future__ import annotations

from decimal import Decimal

from .drawdown import drawdown_state
from .fingerprint import sha256_fingerprint
from .models import BankrollLedgerEntry


def build_ledger(initial_bankroll, selections, settlements, *, run_namespace=""):
    settlement_by_selection = {item.selection_id: item for item in settlements}
    bankroll = initial_bankroll
    peak = initial_bankroll
    previous_fingerprint = "0" * 64
    result = []
    for order, selection in enumerate(sorted(selections, key=lambda item: item.deterministic_order)):
        settlement = settlement_by_selection[selection.selection_id]
        before = bankroll
        bankroll = before + settlement.net_profit_loss
        if bankroll < 0:
            raise ValueError("Historical bankroll cannot become negative.")
        peak = max(peak, bankroll)
        absolute, percentage = drawdown_state(bankroll, peak)
        cumulative_profit = bankroll - initial_bankroll
        cumulative_return = cumulative_profit / initial_bankroll
        fingerprint = sha256_fingerprint(
            {
                "previous_ledger_fingerprint": previous_fingerprint,
                "bankroll_before": before, "stake": selection.applied_stake_amount,
                "gross_return": settlement.gross_return, "bankroll_after": bankroll,
                "drawdown": (peak, absolute, percentage), "deterministic_order": order,
            }
        )
        result.append(
            BankrollLedgerEntry(
                ledger_entry_id=f"historical-backtest-ledger-{sha256_fingerprint((run_namespace, fingerprint))}",
                selection_id=selection.selection_id,
                kickoff_group_id=selection.kickoff_group_id,
                bankroll_before=before, stake_reserved=selection.applied_stake_amount,
                gross_return=settlement.gross_return,
                net_result=settlement.net_profit_loss, bankroll_after=bankroll,
                cumulative_profit=cumulative_profit, cumulative_return=cumulative_return,
                running_peak=peak, absolute_drawdown=absolute,
                percentage_drawdown=percentage, ledger_fingerprint=fingerprint,
                deterministic_order=order,
            )
        )
        previous_fingerprint = fingerprint
    return tuple(result)


def verify_bankroll_ledger(initial_bankroll, selections, settlements, ledger, *, run_namespace="") -> tuple[str, ...]:
    try:
        expected = build_ledger(initial_bankroll, selections, settlements, run_namespace=run_namespace)
    except Exception as exc:
        return (str(exc),)
    return () if expected == ledger else ("BANKROLL_LEDGER_MISMATCH",)


def reproduce_final_bankroll(initial_bankroll, settlements):
    return initial_bankroll + sum((item.net_profit_loss for item in settlements), Decimal(0))
