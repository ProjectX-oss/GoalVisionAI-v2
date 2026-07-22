"""Bounded validation policy for explicitly supplied historical datasets."""

from dataclasses import dataclass
from decimal import Decimal


HISTORICAL_DATASET_SCHEMA = "goalvision_historical_dataset_v1"


@dataclass(frozen=True, slots=True)
class HistoricalImportPolicy:
    version: str = "historical-match-import-policy-v1"
    metadata_version: str = "v1"
    maximum_matches_per_import: int = 100_000
    maximum_score: int = 30
    maximum_shots: int = 200
    maximum_shots_on_target: int = 100
    maximum_expected_goals: Decimal = Decimal("20")
    maximum_corners: int = 50
    maximum_yellow_cards: int = 20
    maximum_red_cards: int = 5
    maximum_fouls: int = 100
    maximum_offsides: int = 30
    maximum_substitutes: int = 20
    possession_total_tolerance: Decimal = Decimal("1")


DEFAULT_HISTORICAL_IMPORT_POLICY = HistoricalImportPolicy()
