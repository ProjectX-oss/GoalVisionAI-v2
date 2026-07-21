"""Pure Decimal calculations and deterministic classifications."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .models import FreshnessState, ValueClassification
from .policy import MarketValueAssessmentPolicy


@dataclass(frozen=True, slots=True)
class ValueMetrics:
    fair_probability: Decimal
    fair_decimal_odds: Decimal
    bookmaker_decimal_odds: Decimal
    implied_probability: Decimal
    break_even_probability: Decimal
    absolute_probability_edge: Decimal
    relative_probability_edge: Decimal
    expected_value: Decimal
    expected_return: Decimal
    potential_profit: Decimal


def calculate(
    fair_probability: Decimal,
    decimal_odds: Decimal,
    policy: MarketValueAssessmentPolicy,
) -> ValueMetrics:
    """Calculate all values at high precision, then quantize once at output."""

    with localcontext() as context:
        context.prec = 50
        implied_probability = Decimal(1) / decimal_odds
        fair_decimal_odds = Decimal(1) / fair_probability
        absolute_edge = fair_probability - implied_probability
        relative_edge = (fair_probability / implied_probability) - Decimal(1)
        expected_return = fair_probability * decimal_odds
        expected_value = expected_return - Decimal(1)
        potential_profit = decimal_odds - Decimal(1)

    def quantize(value: Decimal, quantum: Decimal) -> Decimal:
        return value.quantize(quantum, rounding=policy.rounding)
    implied = quantize(implied_probability, policy.probability_quantum)
    return ValueMetrics(
        fair_probability=quantize(fair_probability, policy.probability_quantum),
        fair_decimal_odds=quantize(fair_decimal_odds, policy.fair_odds_quantum),
        bookmaker_decimal_odds=quantize(decimal_odds, policy.odds_quantum),
        implied_probability=implied,
        break_even_probability=implied,
        absolute_probability_edge=quantize(absolute_edge, policy.edge_quantum),
        relative_probability_edge=quantize(relative_edge, policy.edge_quantum),
        expected_value=quantize(expected_value, policy.ev_quantum),
        expected_return=quantize(expected_return, policy.ev_quantum),
        potential_profit=quantize(potential_profit, policy.odds_quantum),
    )


def classify_odds_freshness(
    age_seconds: int, policy: MarketValueAssessmentPolicy
) -> FreshnessState:
    if age_seconds <= policy.odds_fresh_seconds:
        return FreshnessState.FRESH
    if age_seconds <= policy.odds_aging_seconds:
        return FreshnessState.AGING
    if age_seconds <= policy.odds_stale_seconds:
        return FreshnessState.STALE
    return FreshnessState.EXPIRED


def classify_calibrated_freshness(
    age_seconds: int, policy: MarketValueAssessmentPolicy
) -> FreshnessState:
    if age_seconds <= policy.calibrated_fresh_seconds:
        return FreshnessState.FRESH
    if age_seconds <= policy.calibrated_aging_seconds:
        return FreshnessState.AGING
    return FreshnessState.STALE


def worst_freshness(*states: FreshnessState) -> FreshnessState:
    rank = {
        FreshnessState.FRESH: 0,
        FreshnessState.AGING: 1,
        FreshnessState.STALE: 2,
        FreshnessState.EXPIRED: 3,
    }
    return max(states, key=rank.__getitem__)


def classify_value(
    expected_value: Decimal, policy: MarketValueAssessmentPolicy
) -> ValueClassification:
    if expected_value < 0:
        return ValueClassification.NEGATIVE_VALUE
    if expected_value < policy.positive_value_threshold:
        return ValueClassification.NEUTRAL_VALUE
    if expected_value < policy.strong_value_threshold:
        return ValueClassification.POSITIVE_VALUE
    return ValueClassification.STRONG_VALUE


def classify_market_value(
    fair_probability: Decimal,
    decimal_odds: Decimal,
    policy: MarketValueAssessmentPolicy,
) -> ValueClassification:
    """Classify using unquantized EV so display rounding cannot cross a threshold."""

    with localcontext() as context:
        context.prec = 50
        expected_value = (fair_probability * decimal_odds) - Decimal(1)
    return classify_value(expected_value, policy)
