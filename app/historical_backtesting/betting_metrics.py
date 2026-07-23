"""Betting, risk, grouping, value, and optional CLV diagnostics."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .drawdown import longest_streak, maximum_drawdown_duration
from .fingerprint import canonical_json, sha256_fingerprint
from .market_mapping import probability_for
from .models import BacktestMetric, SettlementStatus


def calculate_betting_metrics(
    predictions, assessments, selections, settlements, ledger,
    initial_bankroll, closing_odds=(), start_order=0, *, run_namespace="",
):
    values = _overall(assessments, selections, settlements, ledger, initial_bankroll)
    rows = _rows("BETTING", "OVERALL", values, start_order, run_namespace)
    rows.extend(_group_rows(predictions, selections, settlements, start_order + len(rows), run_namespace))
    clv = _clv_values(selections, closing_odds)
    rows.extend(_rows("CLV", "OVERALL", clv, start_order + len(rows), run_namespace))
    aggregate = dict(values)
    aggregate.update({f"clv_{key}": value for key, value in clv.items()})
    return tuple(rows), tuple(sorted(aggregate.items()))


def reproduce_betting_metrics(*args, **kwargs):
    return calculate_betting_metrics(*args, **kwargs)


def _overall(assessments, selections, settlements, ledger, initial):
    wins = sum(item.status is SettlementStatus.WON for item in settlements)
    losses = sum(item.status is SettlementStatus.LOST for item in settlements)
    voids = sum(item.status is SettlementStatus.VOID for item in settlements)
    pushes = sum(item.status is SettlementStatus.PUSH for item in settlements)
    unsettled = sum(item.status is SettlementStatus.UNSETTLED for item in settlements)
    stakes = tuple(item.applied_stake_amount for item in selections)
    odds = tuple(item.decimal_odds for item in selections)
    probabilities = tuple(item.calibrated_probability for item in selections)
    evs = tuple(item.expected_value for item in selections)
    total_stake = sum(stakes, Decimal(0))
    gross = sum((item.gross_return for item in settlements), Decimal(0))
    net = sum((item.net_profit_loss for item in settlements), Decimal(0))
    final = ledger[-1].bankroll_after if ledger else initial
    returns = tuple(
        item.net_profit_loss / selection.applied_stake_amount
        for item, selection in zip(settlements, selections)
        if selection.applied_stake_amount > 0
    )
    mean_return = _mean(returns)
    variance = _mean(tuple((item - mean_return) ** 2 for item in returns))
    maximum_abs = max((item.absolute_drawdown for item in ledger), default=Decimal(0))
    maximum_pct = max((item.percentage_drawdown for item in ledger), default=Decimal(0))
    selected_brier = _mean(
        tuple((selection.calibrated_probability - Decimal(int(settlement.status is SettlementStatus.WON))) ** 2
              for selection, settlement in zip(selections, settlements))
    )
    selected_calibration_error = abs(
        _mean(probabilities) - (Decimal(wins) / Decimal(len(settlements)) if settlements else Decimal(0))
    )
    return {
        "assessed_markets": Decimal(len(assessments)),
        "eligible_markets": Decimal(sum(item.eligible for item in assessments)),
        "selected_bets": Decimal(len(selections)),
        "rejected_bets": Decimal(sum(not item.eligible for item in assessments)),
        "wins": Decimal(wins), "losses": Decimal(losses), "voids": Decimal(voids),
        "pushes": Decimal(pushes), "unsettled": Decimal(unsettled),
        "strike_rate": Decimal(wins) / Decimal(wins + losses) if wins + losses else Decimal(0),
        "total_stake": total_stake, "gross_return": gross, "net_profit": net,
        "roi": net / total_stake if total_stake else Decimal(0),
        "yield": net / total_stake if total_stake else Decimal(0),
        "average_odds": _mean(odds), "median_odds": _median(odds),
        "average_calibrated_probability": _mean(probabilities),
        "average_expected_value": _mean(evs), "realized_return_per_bet": _mean(returns),
        "final_bankroll": final, "bankroll_growth_percentage": (final - initial) / initial,
        "peak_bankroll": max((item.running_peak for item in ledger), default=initial),
        "minimum_bankroll": min((item.bankroll_after for item in ledger), default=initial),
        "maximum_absolute_drawdown": maximum_abs,
        "maximum_percentage_drawdown": maximum_pct,
        "longest_losing_streak": Decimal(longest_streak(tuple(item.net_profit_loss for item in settlements), False)),
        "longest_winning_streak": Decimal(longest_streak(tuple(item.net_profit_loss for item in settlements), True)),
        "maximum_consecutive_drawdown_duration": Decimal(maximum_drawdown_duration(tuple(item.bankroll_after for item in ledger))),
        "bankroll_volatility": variance.sqrt() if variance >= 0 else Decimal(0),
        "return_variance": variance, "return_standard_deviation": variance.sqrt() if variance >= 0 else Decimal(0),
        "expected_profit": sum((item.expected_value * item.applied_stake_amount for item in selections), Decimal(0)),
        "realized_profit": net,
        "expected_realized_difference": net - sum((item.expected_value * item.applied_stake_amount for item in selections), Decimal(0)),
        "selected_bet_brier_score": selected_brier,
        "selected_bet_calibration_error": selected_calibration_error,
    }


def _group_rows(predictions, selections, settlements, start, run_namespace):
    prediction_by_match = {item.historical_match_id: item for item in predictions}
    settlement_by_id = {item.selection_id: item for item in settlements}
    groups = defaultdict(list)
    for selection in selections:
        prediction = prediction_by_match[selection.historical_match_id]
        settlement = settlement_by_id[selection.selection_id]
        identities = (
            ("TARGET", selection.market_identity.value),
            ("COMPETITION", prediction.competition),
            ("SEASON", prediction.season),
            ("ODDS_BUCKET", _bucket(selection.decimal_odds, (Decimal("1.6"), Decimal("2"), Decimal("3"), Decimal("5")))),
            ("PROBABILITY_BUCKET", _bucket(selection.calibrated_probability, (Decimal(".5"), Decimal(".6"), Decimal(".7"), Decimal(".8")))),
            ("EV_BUCKET", _bucket(selection.expected_value, (Decimal(".02"), Decimal(".05"), Decimal(".10"), Decimal(".20")))),
            ("STAKE_CLASSIFICATION", selection.stake_classification),
            ("CALENDAR_MONTH", prediction.kickoff_utc[:7]),
        )
        for category, identity in identities:
            groups[(category, identity)].append((selection, settlement))
    rows = []
    for (category, identity), items in sorted(groups.items()):
        stake = sum((item[0].applied_stake_amount for item in items), Decimal(0))
        net = sum((item[1].net_profit_loss for item in items), Decimal(0))
        values = {
            "bets": Decimal(len(items)),
            "wins": Decimal(sum(item[1].status is SettlementStatus.WON for item in items)),
            "total_stake": stake, "net_profit": net,
            "roi": net / stake if stake else Decimal(0),
        }
        rows.extend(_rows("MARKET_LEVEL", f"{category}:{identity}", values, start + len(rows), run_namespace))
    return rows


def _clv_values(selections, closing):
    by_key = defaultdict(list)
    for item in closing:
        by_key[(item.snapshot.historical_match_id, item.market_identity)].append(item)
    values = []
    for selection in selections:
        candidates = by_key.get((selection.historical_match_id, selection.market_identity), ())
        if not candidates:
            continue
        chosen = sorted(candidates, key=lambda item: (item.normalized_snapshot_timestamp_utc, item.snapshot.bookmaker_identity))[-1]
        close = chosen.snapshot.decimal_odds
        ratio = selection.decimal_odds / close
        movement = (Decimal(1) / close) - (Decimal(1) / selection.decimal_odds)
        values.append((ratio - Decimal(1), movement))
    clvs = tuple(item[0] for item in values)
    return {
        "available_count": Decimal(len(values)),
        "missing_count": Decimal(len(selections) - len(values)),
        "positive_count": Decimal(sum(item > 0 for item in clvs)),
        "average": _mean(clvs), "median": _median(clvs),
        "average_implied_probability_movement": _mean(tuple(item[1] for item in values)),
    }


def _rows(category, grouping, values, start, run_namespace):
    return [
        BacktestMetric(
            metric_row_id=f"historical-backtest-metric-{sha256_fingerprint((run_namespace, category, grouping, name, value))}",
            category=category, grouping_identity=grouping, metric_name=name,
            metric_value=value, metric_snapshot=canonical_json({"value": value}),
            deterministic_order=start + index,
        )
        for index, (name, value) in enumerate(values.items())
    ]


def _mean(values):
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else Decimal(0)


def _median(values):
    if not values:
        return Decimal(0)
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _bucket(value, boundaries):
    for boundary in boundaries:
        if value < boundary:
            return f"LT_{boundary}"
    return f"GTE_{boundaries[-1]}"
