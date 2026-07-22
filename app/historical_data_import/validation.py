"""Fail-closed validation primitives for historical provider records."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .exceptions import HistoricalDatasetValidationError
from .models import (
    FullTimeResult,
    HistoricalDataset,
    HistoricalLineupInput,
    HistoricalTeamStatisticsInput,
)
from .policy import HISTORICAL_DATASET_SCHEMA, HistoricalImportPolicy


_FORMATION = re.compile(r"^[1-9](?:-[1-9]){1,4}$")
_RESULTS = {
    "H": FullTimeResult.HOME_WIN,
    "HOME": FullTimeResult.HOME_WIN,
    "HOME_WIN": FullTimeResult.HOME_WIN,
    "D": FullTimeResult.DRAW,
    "DRAW": FullTimeResult.DRAW,
    "A": FullTimeResult.AWAY_WIN,
    "AWAY": FullTimeResult.AWAY_WIN,
    "AWAY_WIN": FullTimeResult.AWAY_WIN,
}


def validate_dataset(dataset: HistoricalDataset, policy: HistoricalImportPolicy) -> None:
    if type(dataset) is not HistoricalDataset:
        raise HistoricalDatasetValidationError("A typed HistoricalDataset is required.")
    if dataset.schema_version != HISTORICAL_DATASET_SCHEMA:
        raise HistoricalDatasetValidationError(
            f"Unsupported historical dataset schema: {dataset.schema_version!r}."
        )
    require_text(dataset.provider, "provider")
    require_text(dataset.dataset_id, "dataset_id")
    require_text(dataset.dataset_version, "dataset_version")
    if type(dataset.matches) is not tuple or not dataset.matches:
        raise HistoricalDatasetValidationError("A dataset must contain at least one match.")
    if len(dataset.matches) > policy.maximum_matches_per_import:
        raise HistoricalDatasetValidationError("The dataset exceeds the bounded import size.")


def require_text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise HistoricalDatasetValidationError(f"{label} must be a non-empty string.")
    if "\x00" in value:
        raise HistoricalDatasetValidationError(f"{label} contains a null character.")
    return value


def optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return require_text(value, label)


def require_integer(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise HistoricalDatasetValidationError(f"{label} must be an integer.")
    if value < minimum or (maximum is not None and value > maximum):
        upper = f" and <= {maximum}" if maximum is not None else ""
        raise HistoricalDatasetValidationError(f"{label} must be >= {minimum}{upper}.")
    return value


def optional_integer(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int | None:
    if value is None:
        return None
    return require_integer(value, label, minimum=minimum, maximum=maximum)


def parse_decimal(value: object, label: str) -> Decimal:
    if type(value) not in {str, int, Decimal}:
        raise HistoricalDatasetValidationError(
            f"{label} must use a Decimal-safe string, integer, or Decimal."
        )
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise HistoricalDatasetValidationError(f"{label} is not a valid Decimal.") from exc
    if not parsed.is_finite():
        raise HistoricalDatasetValidationError(f"{label} must be finite.")
    return parsed


def optional_decimal(
    value: object,
    label: str,
    *,
    minimum: Decimal,
    maximum: Decimal,
) -> Decimal | None:
    if value is None:
        return None
    parsed = parse_decimal(value, label)
    if parsed < minimum or parsed > maximum:
        raise HistoricalDatasetValidationError(
            f"{label} must be between {minimum} and {maximum}."
        )
    return parsed


def derive_result(home_score: int, away_score: int) -> FullTimeResult:
    if home_score > away_score:
        return FullTimeResult.HOME_WIN
    if home_score < away_score:
        return FullTimeResult.AWAY_WIN
    return FullTimeResult.DRAW


def normalize_supplied_result(value: FullTimeResult | str | None) -> FullTimeResult | None:
    if value is None:
        return None
    if isinstance(value, FullTimeResult):
        return value
    if type(value) is not str or value.strip().upper() not in _RESULTS:
        raise HistoricalDatasetValidationError("full_time_result is unsupported.")
    return _RESULTS[value.strip().upper()]


def validate_statistics_input(
    value: HistoricalTeamStatisticsInput,
    label: str,
    policy: HistoricalImportPolicy,
) -> None:
    if type(value) is not HistoricalTeamStatisticsInput:
        raise HistoricalDatasetValidationError(f"{label} must be typed statistics.")
    fields = (
        value.possession,
        value.shots,
        value.shots_on_target,
        value.expected_goals,
        value.corners,
        value.yellow_cards,
        value.red_cards,
        value.fouls,
        value.offsides,
    )
    if all(item is None for item in fields):
        raise HistoricalDatasetValidationError(f"{label} cannot be an empty statistics object.")
    optional_decimal(value.possession, f"{label}.possession", minimum=Decimal("0"), maximum=Decimal("100"))
    optional_decimal(
        value.expected_goals,
        f"{label}.expected_goals",
        minimum=Decimal("0"),
        maximum=policy.maximum_expected_goals,
    )
    shots = optional_integer(value.shots, f"{label}.shots", maximum=policy.maximum_shots)
    on_target = optional_integer(
        value.shots_on_target,
        f"{label}.shots_on_target",
        maximum=policy.maximum_shots_on_target,
    )
    if shots is not None and on_target is not None and on_target > shots:
        raise HistoricalDatasetValidationError(f"{label}.shots_on_target cannot exceed shots.")
    optional_integer(value.corners, f"{label}.corners", maximum=policy.maximum_corners)
    optional_integer(
        value.yellow_cards,
        f"{label}.yellow_cards",
        maximum=policy.maximum_yellow_cards,
    )
    optional_integer(value.red_cards, f"{label}.red_cards", maximum=policy.maximum_red_cards)
    optional_integer(value.fouls, f"{label}.fouls", maximum=policy.maximum_fouls)
    optional_integer(value.offsides, f"{label}.offsides", maximum=policy.maximum_offsides)


def validate_lineup_input(
    value: HistoricalLineupInput,
    label: str,
    policy: HistoricalImportPolicy,
) -> None:
    if type(value) is not HistoricalLineupInput:
        raise HistoricalDatasetValidationError(f"{label} must be a typed lineup.")
    if type(value.starting_xi) is not tuple or len(value.starting_xi) != 11:
        raise HistoricalDatasetValidationError(f"{label}.starting_xi must contain exactly 11 players.")
    if type(value.substitutes) is not tuple or len(value.substitutes) > policy.maximum_substitutes:
        raise HistoricalDatasetValidationError(
            f"{label}.substitutes must contain at most {policy.maximum_substitutes} players."
        )
    for index, player in enumerate((*value.starting_xi, *value.substitutes)):
        require_text(player, f"{label}.player[{index}]")
    if value.formation is not None:
        formation = require_text(value.formation, f"{label}.formation").replace(" ", "")
        if not _FORMATION.fullmatch(formation):
            raise HistoricalDatasetValidationError(f"{label}.formation is invalid.")
        if sum(int(part) for part in formation.split("-")) != 10:
            raise HistoricalDatasetValidationError(
                f"{label}.formation must describe ten outfield players."
            )
