"""Deterministic cross-market, competition, season, and temporal stability."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal

from .fingerprint import canonical_json, sha256_fingerprint, stability_fingerprint
from .models import StabilityGroup, StabilityStatus


GROUP_CATEGORIES = (
    "MARKET",
    "COMPETITION",
    "SEASON",
    "CALENDAR_MONTH",
    "ODDS_BUCKET",
    "PROBABILITY_BUCKET",
    "EV_BUCKET",
    "STAKE_CLASSIFICATION",
)


def calculate_stability(champion_run, challenger_run, policy):
    champion = _groups(champion_run)
    challenger = _groups(challenger_run)
    total_challenger_profit = {
        category: sum(
            (
                values["net_profit"]
                for (group_category, _), values in challenger.items()
                if group_category == category and values["net_profit"] > 0
            ),
            Decimal(0),
        )
        for category in GROUP_CATEGORIES
    }
    total_challenger_loss = {
        category: sum(
            (
                abs(values["net_profit"])
                for (group_category, _), values in challenger.items()
                if group_category == category and values["net_profit"] < 0
            ),
            Decimal(0),
        )
        for category in GROUP_CATEGORIES
    }
    result = []
    for category, identity in sorted(set(champion) | set(challenger)):
        c = champion.get((category, identity), _empty())
        h = challenger.get((category, identity), _empty())
        minimum = min(c["bets"], h["bets"])
        delta = h["roi"] - c["roi"]
        if minimum < policy.minimum_group_sample_size:
            status = StabilityStatus.INSUFFICIENT_SAMPLE
        elif delta >= policy.material_improvement:
            status = StabilityStatus.IMPROVED
        elif delta <= -max(policy.material_improvement * 3, Decimal("0.10")):
            status = StabilityStatus.SEVERELY_DEGRADED
        elif delta <= -policy.material_improvement:
            status = StabilityStatus.DEGRADED
        else:
            status = StabilityStatus.STABLE
        concentration = (
            h["net_profit"] / total_challenger_profit[category]
            if h["net_profit"] > 0 and total_challenger_profit[category] > 0
            else Decimal(0)
        )
        loss_concentration = (
            abs(h["net_profit"]) / total_challenger_loss[category]
            if h["net_profit"] < 0 and total_challenger_loss[category] > 0
            else Decimal(0)
        )
        material = {
            "category": category,
            "identity": identity,
            "champion": c,
            "challenger": h,
            "delta": {"roi": delta, "net_profit": h["net_profit"] - c["net_profit"]},
            "status": status,
            "concentration": concentration,
            "loss_concentration": loss_concentration,
            "policy": policy.stability_score_policy_version,
        }
        fingerprint = stability_fingerprint(material, policy.stability_score_policy_version)
        result.append(
            StabilityGroup(
                stability_row_id=f"model-comparison-stability-{sha256_fingerprint((fingerprint, len(result)))}",
                group_category=category,
                group_identity=identity,
                champion_sample_count=c["bets"],
                challenger_sample_count=h["bets"],
                champion_metric_snapshot=canonical_json(c),
                challenger_metric_snapshot=canonical_json(h),
                delta_snapshot=canonical_json(material["delta"]),
                stability_status=status,
                concentration_evidence_snapshot=canonical_json(
                    {
                        "profit_concentration": concentration,
                        "loss_concentration": loss_concentration,
                    }
                ),
                stability_fingerprint=fingerprint,
                deterministic_order=len(result),
            )
        )
    return tuple(result)


def summarize_stability(groups):
    eligible = tuple(
        item
        for item in groups
        if item.stability_status is not StabilityStatus.INSUFFICIENT_SAMPLE
    )
    if not eligible:
        return {
            "profitable_group_ratio": Decimal(0),
            "degraded_group_ratio": Decimal(0),
            "severe_degradation_count": Decimal(0),
            "maximum_profit_concentration": Decimal(0),
            "maximum_loss_concentration": Decimal(0),
            "temporal_consistency_score": Decimal(0),
            "cross_market_consistency_score": Decimal(0),
            "cross_competition_consistency_score": Decimal(0),
        }
    stable = {
        StabilityStatus.IMPROVED,
        StabilityStatus.STABLE,
    }
    degraded = {
        StabilityStatus.DEGRADED,
        StabilityStatus.SEVERELY_DEGRADED,
    }
    snapshots = [
        _snapshot(item.concentration_evidence_snapshot)
        for item in eligible
    ]
    concentrations = [
        item.get(
            "profit_concentration", Decimal(0)
        )
        for item in snapshots
    ]
    loss_concentrations = [
        item.get("loss_concentration", Decimal(0))
        for item in snapshots
    ]

    def ratio(category):
        values = tuple(item for item in eligible if item.group_category == category)
        return (
            Decimal(sum(item.stability_status in stable for item in values))
            / Decimal(len(values))
            if values
            else Decimal(0)
        )

    return {
        "profitable_group_ratio": Decimal(
            sum(
                Decimal(
                    json.loads(item.challenger_metric_snapshot)["net_profit"]
                )
                > 0
                for item in eligible
            )
        )
        / Decimal(len(eligible)),
        "degraded_group_ratio": Decimal(sum(item.stability_status in degraded for item in eligible)) / Decimal(len(eligible)),
        "severe_degradation_count": Decimal(sum(item.stability_status is StabilityStatus.SEVERELY_DEGRADED for item in eligible)),
        "maximum_profit_concentration": max(concentrations, default=Decimal(0)),
        "maximum_loss_concentration": max(
            loss_concentrations, default=Decimal(0)
        ),
        "temporal_consistency_score": ratio("CALENDAR_MONTH"),
        "cross_market_consistency_score": ratio("MARKET"),
        "cross_competition_consistency_score": ratio("COMPETITION"),
    }


def reproduce_stability(champion_run, challenger_run, policy):
    return calculate_stability(champion_run, challenger_run, policy)


def _groups(run):
    predictions = {item.historical_match_id: item for item in run.predictions}
    settlements = {item.selection_id: item for item in run.settlements}
    grouped = defaultdict(list)
    for selection in run.selections:
        prediction = predictions.get(selection.historical_match_id)
        settlement = settlements.get(selection.selection_id)
        if prediction is None or settlement is None:
            continue
        identities = (
            ("MARKET", selection.market_identity.value),
            ("COMPETITION", prediction.competition),
            ("SEASON", prediction.season),
            ("CALENDAR_MONTH", prediction.kickoff_utc[:7]),
            ("ODDS_BUCKET", _bucket(selection.decimal_odds, (Decimal("1.6"), Decimal("2"), Decimal("3"), Decimal("5")))),
            ("PROBABILITY_BUCKET", _bucket(selection.calibrated_probability, (Decimal(".5"), Decimal(".6"), Decimal(".7"), Decimal(".8")))),
            ("EV_BUCKET", _bucket(selection.expected_value, (Decimal(".02"), Decimal(".05"), Decimal(".10"), Decimal(".20")))),
            ("STAKE_CLASSIFICATION", selection.stake_classification),
        )
        for key in identities:
            grouped[key].append((selection, settlement))
    result = {}
    for key, items in grouped.items():
        stake = sum((selection.applied_stake_amount for selection, _ in items), Decimal(0))
        net = sum((settlement.net_profit_loss for _, settlement in items), Decimal(0))
        wins = sum(settlement.net_profit_loss > 0 for _, settlement in items)
        losses = sum(settlement.net_profit_loss < 0 for _, settlement in items)
        result[key] = {
            "sample_count": len(items),
            "bets": len(items),
            "wins": wins,
            "losses": losses,
            "roi": net / stake if stake else Decimal(0),
            "yield": net / stake if stake else Decimal(0),
            "net_profit": net,
            "average_ev": sum((selection.expected_value for selection, _ in items), Decimal(0)) / Decimal(len(items)),
            "maximum_drawdown": _maximum_group_drawdown(
                tuple(settlement.net_profit_loss for _, settlement in items)
            ),
        }
    return result


def _empty():
    return {
        "sample_count": 0,
        "bets": 0,
        "wins": 0,
        "losses": 0,
        "roi": Decimal(0),
        "yield": Decimal(0),
        "net_profit": Decimal(0),
        "average_ev": Decimal(0),
        "maximum_drawdown": Decimal(0),
    }


def _bucket(value, boundaries):
    for boundary in boundaries:
        if value < boundary:
            return f"LT_{boundary}"
    return f"GTE_{boundaries[-1]}"


def _snapshot(value):
    return {
        key: Decimal(item) if key == "profit_concentration" else item
        for key, item in json.loads(value).items()
    }


def _maximum_group_drawdown(returns):
    bankroll = peak = Decimal(0)
    maximum = Decimal(0)
    for value in returns:
        bankroll += value
        peak = max(peak, bankroll)
        maximum = max(maximum, peak - bankroll)
    return maximum
