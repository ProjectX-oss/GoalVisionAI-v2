"""Explicit later settlement; never polls or mutates bankroll."""

from __future__ import annotations

from decimal import Decimal

from .exceptions import ShadowSettlementError
from .fingerprint import sha256_fingerprint
from .models import SettlementOutcome, ShadowSettlement
from .validation import utc


def settle_selection(selection, home_score, away_score):
    if selection.market_identity is None:
        return SettlementOutcome.NO_SELECTION, Decimal(0)
    market = selection.market_identity
    total = home_score + away_score
    won = {
        "HOME_WIN": home_score > away_score,
        "DRAW": home_score == away_score,
        "AWAY_WIN": away_score > home_score,
        "OVER_1_5": total > 1.5, "UNDER_1_5": total < 1.5,
        "OVER_2_5": total > 2.5, "UNDER_2_5": total < 2.5,
        "OVER_3_5": total > 3.5, "UNDER_3_5": total < 3.5,
        "BTTS_YES": home_score > 0 and away_score > 0,
        "BTTS_NO": home_score == 0 or away_score == 0,
    }[market]
    return (SettlementOutcome.WON, selection.decimal_odds - Decimal(1)) if won else (SettlementOutcome.LOST, Decimal(-1))


def build_settlement(command, execution):
    if command.shadow_execution_fingerprint != execution.execution_fingerprint or command.match_id != execution.command.match_id:
        raise ShadowSettlementError("Settlement execution or match identity differs.")
    if type(command.final_home_score) is not int or type(command.final_away_score) is not int or min(command.final_home_score, command.final_away_score) < 0:
        raise ShadowSettlementError("Final scores must be non-negative integers.")
    timestamp = utc(command.settlement_timestamp_utc, "settlement timestamp")
    if timestamp <= utc(execution.command.kickoff_utc, "kickoff"):
        raise ShadowSettlementError("Settlement timestamp must be after kickoff.")
    champion, challenger = execution.selections
    champion_outcome, champion_profit = settle_selection(champion, command.final_home_score, command.final_away_score)
    challenger_outcome, challenger_profit = settle_selection(challenger, command.final_home_score, command.final_away_score)
    core = {
        "request": command.settlement_request_id, "execution": execution.execution_fingerprint,
        "match": command.match_id, "home": command.final_home_score, "away": command.final_away_score,
        "timestamp": timestamp, "source": command.source_fingerprint,
        "source_identity": command.source_identity, "source_version": command.source_version,
        "source_record_identity": command.source_record_identity,
        "policy": command.settlement_policy_version,
        "champion": champion_outcome, "challenger": challenger_outcome,
    }
    fingerprint = sha256_fingerprint(core)
    return ShadowSettlement(
        settlement_id=f"shadow-settlement-{fingerprint}", settlement_request_id=command.settlement_request_id,
        shadow_execution_id=execution.shadow_execution_id, champion_outcome=champion_outcome,
        challenger_outcome=challenger_outcome, champion_profit_per_unit=champion_profit,
        challenger_profit_per_unit=challenger_profit, final_home_score=command.final_home_score,
        final_away_score=command.final_away_score, source_fingerprint=command.source_fingerprint,
        settlement_timestamp_utc=timestamp, settlement_fingerprint=fingerprint,
    )
