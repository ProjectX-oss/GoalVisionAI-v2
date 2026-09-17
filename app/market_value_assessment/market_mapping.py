"""Centralized immutable mapping from bookmaker markets to calibrated targets."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.prediction_inference import PredictionTarget

from .exceptions import IncompatibleMarketError
from .models import (
    MarketMapping,
    MarketSelection,
    MarketType,
    ProbabilitySourceType,
)


MAPPING_VERSION = "market-mapping-v1"
VALID_PROBABILITY_RANGE = (Decimal("0.001"), Decimal("0.999"))


def _mapping(
    market_type: MarketType,
    selection: MarketSelection,
    market_line: Decimal | None,
    source_type: ProbabilitySourceType,
    *targets: PredictionTarget,
) -> MarketMapping:
    formula = " + ".join(target.value for target in targets)
    return MarketMapping(
        market_type=market_type,
        selection=selection,
        market_line=market_line,
        probability_source_type=source_type,
        source_targets=targets,
        derivation_formula=formula,
        valid_probability_range=VALID_PROBABILITY_RANGE,
        version_introduced=MAPPING_VERSION,
        description=f"{market_type.value} / {selection.value}",
    )


MAPPINGS = (
    _mapping(
        MarketType.MATCH_WINNER,
        MarketSelection.HOME,
        None,
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.HOME_WIN,
    ),
    _mapping(
        MarketType.MATCH_WINNER,
        MarketSelection.DRAW,
        None,
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.DRAW,
    ),
    _mapping(
        MarketType.MATCH_WINNER,
        MarketSelection.AWAY,
        None,
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.AWAY_WIN,
    ),
    _mapping(
        MarketType.DOUBLE_CHANCE,
        MarketSelection.HOME_DRAW,
        None,
        ProbabilitySourceType.DERIVED_DOUBLE_CHANCE,
        PredictionTarget.HOME_WIN,
        PredictionTarget.DRAW,
    ),
    _mapping(
        MarketType.DOUBLE_CHANCE,
        MarketSelection.HOME_AWAY,
        None,
        ProbabilitySourceType.DERIVED_DOUBLE_CHANCE,
        PredictionTarget.HOME_WIN,
        PredictionTarget.AWAY_WIN,
    ),
    _mapping(
        MarketType.DOUBLE_CHANCE,
        MarketSelection.DRAW_AWAY,
        None,
        ProbabilitySourceType.DERIVED_DOUBLE_CHANCE,
        PredictionTarget.DRAW,
        PredictionTarget.AWAY_WIN,
    ),
    _mapping(
        MarketType.TOTALS,
        MarketSelection.OVER,
        Decimal("1.5"),
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.OVER_1_5,
    ),
    _mapping(
        MarketType.TOTALS,
        MarketSelection.UNDER,
        Decimal("1.5"),
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.UNDER_1_5,
    ),
    _mapping(
        MarketType.TOTALS,
        MarketSelection.OVER,
        Decimal("2.5"),
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.OVER_2_5,
    ),
    _mapping(
        MarketType.TOTALS,
        MarketSelection.UNDER,
        Decimal("2.5"),
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.UNDER_2_5,
    ),
    _mapping(
        MarketType.TOTALS,
        MarketSelection.OVER,
        Decimal("3.5"),
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.OVER_3_5,
    ),
    _mapping(
        MarketType.TOTALS,
        MarketSelection.UNDER,
        Decimal("3.5"),
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.UNDER_3_5,
    ),
    _mapping(
        MarketType.BTTS,
        MarketSelection.YES,
        None,
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.BTTS_YES,
    ),
    _mapping(
        MarketType.BTTS,
        MarketSelection.NO,
        None,
        ProbabilitySourceType.CALIBRATED_TARGET,
        PredictionTarget.BTTS_NO,
    ),
)


@dataclass(frozen=True, slots=True)
class MarketMappingRegistry:
    version: str = MAPPING_VERSION
    mappings: tuple[MarketMapping, ...] = MAPPINGS

    def __post_init__(self) -> None:
        identities = tuple(
            (item.market_type, item.selection, item.market_line)
            for item in self.mappings
        )
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate market mapping identity.")
        if any(item.version_introduced != self.version for item in self.mappings):
            raise ValueError("Mapping definition version is incompatible with registry.")
        for item in self.mappings:
            lower, upper = item.valid_probability_range
            if not Decimal(0) < lower <= upper < Decimal(1):
                raise ValueError("Market mapping probability range is invalid.")

    def resolve(
        self,
        market_type: MarketType,
        selection: MarketSelection,
        market_line: Decimal | None,
    ) -> MarketMapping:
        identity = (market_type, selection, market_line)
        mapping = next(
            (
                item
                for item in self.mappings
                if (item.market_type, item.selection, item.market_line) == identity
            ),
            None,
        )
        if mapping is None:
            raise IncompatibleMarketError(
                "Market, selection, or line is unsupported."
            )
        return mapping
