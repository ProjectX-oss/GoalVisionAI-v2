"""Strict mapping from versioned JSON-compatible provider payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .exceptions import HistoricalDatasetValidationError
from .models import (
    HistoricalDataset,
    HistoricalLineupInput,
    HistoricalMatchInput,
    HistoricalTeamStatisticsInput,
)


_DATASET_FIELDS = {"schema_version", "provider", "dataset_id", "dataset_version", "matches"}
_MATCH_REQUIRED = {
    "source_match_id", "competition", "season", "round", "kickoff_utc",
    "home_team", "away_team", "full_time_home_score", "full_time_away_score",
    "venue",
}
_MATCH_OPTIONAL = {
    "half_time_home_score", "half_time_away_score", "full_time_result",
    "referee", "attendance", "home_statistics", "away_statistics",
    "home_lineup", "away_lineup",
}
_STAT_FIELDS = {
    "possession", "shots", "shots_on_target", "expected_goals", "corners",
    "yellow_cards", "red_cards", "fouls", "offsides",
}
_LINEUP_FIELDS = {"starting_xi", "substitutes", "formation"}


def map_provider_dataset(payload: Mapping[str, Any]) -> HistoricalDataset:
    root = _mapping(payload, "dataset")
    if set(root) != _DATASET_FIELDS:
        raise HistoricalDatasetValidationError("Dataset fields are missing or unsupported.")
    matches = root["matches"]
    if not _sequence(matches):
        raise HistoricalDatasetValidationError("matches must be a JSON array.")
    return HistoricalDataset(
        schema_version=root["schema_version"],
        provider=root["provider"],
        dataset_id=root["dataset_id"],
        dataset_version=root["dataset_version"],
        matches=tuple(_map_match(item, index) for index, item in enumerate(matches)),
    )


def _map_match(value: object, index: int) -> HistoricalMatchInput:
    item = _mapping(value, f"matches[{index}]")
    fields = set(item)
    if not _MATCH_REQUIRED <= fields or fields - (_MATCH_REQUIRED | _MATCH_OPTIONAL):
        raise HistoricalDatasetValidationError(f"matches[{index}] fields are missing or unsupported.")
    return HistoricalMatchInput(
        source_match_id=item["source_match_id"],
        competition=item["competition"],
        season=item["season"],
        round=item["round"],
        kickoff_utc=item["kickoff_utc"],
        home_team=item["home_team"],
        away_team=item["away_team"],
        full_time_home_score=item["full_time_home_score"],
        full_time_away_score=item["full_time_away_score"],
        venue=item["venue"],
        half_time_home_score=item.get("half_time_home_score"),
        half_time_away_score=item.get("half_time_away_score"),
        full_time_result=item.get("full_time_result"),
        referee=item.get("referee"),
        attendance=item.get("attendance"),
        home_statistics=_map_statistics(item.get("home_statistics"), f"matches[{index}].home_statistics"),
        away_statistics=_map_statistics(item.get("away_statistics"), f"matches[{index}].away_statistics"),
        home_lineup=_map_lineup(item.get("home_lineup"), f"matches[{index}].home_lineup"),
        away_lineup=_map_lineup(item.get("away_lineup"), f"matches[{index}].away_lineup"),
    )


def _map_statistics(value: object, label: str) -> HistoricalTeamStatisticsInput | None:
    if value is None:
        return None
    item = _mapping(value, label)
    if set(item) - _STAT_FIELDS:
        raise HistoricalDatasetValidationError(f"{label} contains unsupported fields.")
    return HistoricalTeamStatisticsInput(**{field: item.get(field) for field in _STAT_FIELDS})


def _map_lineup(value: object, label: str) -> HistoricalLineupInput | None:
    if value is None:
        return None
    item = _mapping(value, label)
    if "starting_xi" not in item or set(item) - _LINEUP_FIELDS:
        raise HistoricalDatasetValidationError(f"{label} fields are missing or unsupported.")
    starters = item["starting_xi"]
    substitutes = item.get("substitutes", ())
    if not _sequence(starters) or not _sequence(substitutes):
        raise HistoricalDatasetValidationError(f"{label} player collections must be JSON arrays.")
    return HistoricalLineupInput(
        starting_xi=tuple(starters),
        substitutes=tuple(substitutes),
        formation=item.get("formation"),
    )


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise HistoricalDatasetValidationError(f"{label} must be a JSON object with string keys.")
    return value


def _sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
