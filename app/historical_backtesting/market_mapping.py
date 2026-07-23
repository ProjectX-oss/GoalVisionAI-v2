"""Canonical mapping between historical targets and Official single markets."""

from .models import SupportedMarket


CANONICAL_MARKET_ORDER = tuple(SupportedMarket)


def probability_for(probabilities, market: SupportedMarket):
    for item in probabilities.ordered_probabilities:
        if item.target.value == market.value:
            return item.probability
    raise KeyError(market.value)
