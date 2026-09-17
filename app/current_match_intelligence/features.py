"""Deterministic derived features for the future intelligence contract."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from app.real_match_lab_analysis.policy import SUPPORTED_MARKETS

from .canonical import fingerprint
from .models import (
    DataClass,
    FieldProvenance,
    FutureFeatureVector,
    IntelligenceField,
    CurrentMatchIntelligenceSnapshot,
    FUTURE_FEATURE_CONTRACT,
)


FEATURE_ORDER = (
    "home_form_strength", "away_form_strength",
    "rest_days_home", "rest_days_away",
    "schedule_congestion_home", "schedule_congestion_away",
    "confirmed_starters_count_home", "confirmed_starters_count_away",
    "missing_recent_starters_count_home", "missing_recent_starters_count_away",
    "lineup_continuity_home", "lineup_continuity_away",
    "injury_count_home", "injury_count_away",
    "suspension_count_home", "suspension_count_away",
    "home_recent_goals_for_per_match", "home_recent_goals_against_per_match",
    "away_recent_goals_for_per_match", "away_recent_goals_against_per_match",
    *tuple(f"current_odds_{market.lower()}" for market in SUPPORTED_MARKETS),
    *tuple(f"implied_market_probability_{market.lower()}" for market in SUPPORTED_MARKETS),
)


def derive_features(
    fields: list[IntelligenceField],
    *,
    current_starters: dict[str, set[str]],
    recent_starting_sets: dict[str, list[set[str]]],
    injured: dict[str, set[str]],
    suspended: dict[str, set[str]],
) -> list[IntelligenceField]:
    by_name = {item.name: item for item in fields}
    derived: list[IntelligenceField] = []

    def add(name: str, value: object | None, sources: tuple[str, ...], data_class: DataClass = DataClass.PRE_MATCH_DYNAMIC) -> None:
        if value is None:
            return
        provenance = _provenance(by_name, sources)
        if provenance:
            derived.append(IntelligenceField("feature." + name, data_class, _plain(value), provenance))

    for side in ("home", "away"):
        count = _number(by_name, f"{side}.recent.match_count")
        points = _number(by_name, f"{side}.recent.points")
        goals_for = _number(by_name, f"{side}.recent.goals_for")
        goals_against = _number(by_name, f"{side}.recent.goals_against")
        if count and count > 0:
            add(f"{side}_form_strength", points / (Decimal(3) * count),
                (f"{side}.recent.points", f"{side}.recent.match_count"))
            add(f"{side}_recent_goals_for_per_match", goals_for / count,
                (f"{side}.recent.goals_for", f"{side}.recent.match_count"))
            add(f"{side}_recent_goals_against_per_match", goals_against / count,
                (f"{side}.recent.goals_against", f"{side}.recent.match_count"))
        rest = by_name.get(f"{side}.rest_days")
        congestion = by_name.get(f"{side}.matches_previous_7_days")
        if rest:
            add(f"rest_days_{side}", rest.value, (rest.name,))
        if congestion:
            add(f"schedule_congestion_{side}", congestion.value, (congestion.name,))
        lineup_sources = tuple(
            item.name for item in fields if item.name.startswith(f"{side}.lineup.starters.")
        )
        usage_sources = tuple(
            item.name for item in fields if item.name.startswith(f"{side}.player_usage.")
        )
        if current_starters[side]:
            add(f"confirmed_starters_count_{side}", len(current_starters[side]), lineup_sources,
                DataClass.LINEUP_SENSITIVE)
            prior = recent_starting_sets[side]
            if prior:
                continuity = Decimal(len(current_starters[side] & prior[0])) / Decimal(max(1, len(prior[0])))
                usage = Counter(player for lineup in prior for player in lineup)
                expected = {player for player, starts in usage.items() if starts >= min(2, len(prior))}
                missing = expected - current_starters[side]
                combined_sources = (*lineup_sources, *usage_sources)
                add(f"lineup_continuity_{side}", continuity, combined_sources, DataClass.LINEUP_SENSITIVE)
                add(f"missing_recent_starters_count_{side}", len(missing), combined_sources,
                    DataClass.LINEUP_SENSITIVE)
                missing_provenance = _provenance(by_name, combined_sources)
                for player_id in sorted(missing):
                    derived.append(IntelligenceField(
                        f"{side}.lineup.missing_recent_starters.{player_id}",
                        DataClass.LINEUP_SENSITIVE,
                        "MISSING_FROM_CONFIRMED_XI",
                        missing_provenance,
                    ))
        availability_sources = tuple(
            item.name for item in fields if item.name.startswith(f"{side}.availability.")
        )
        if availability_sources:
            add(f"injury_count_{side}", len(injured[side]), availability_sources)
            add(f"suspension_count_{side}", len(suspended[side]), availability_sources)
    return derived


def future_feature_vector(
    snapshot: CurrentMatchIntelligenceSnapshot,
) -> FutureFeatureVector:
    """Project a snapshot into the separate, fixed future feature contract."""
    values = {item.name.removeprefix("feature."): item.value
              for item in snapshot.fields if item.name.startswith("feature.")}
    ordered = tuple(values.get(name) for name in FEATURE_ORDER)
    missing = tuple(name for name, value in zip(FEATURE_ORDER, ordered) if value is None)
    material = (FUTURE_FEATURE_CONTRACT, snapshot.snapshot_id, FEATURE_ORDER, ordered, missing)
    return FutureFeatureVector(FUTURE_FEATURE_CONTRACT, snapshot.snapshot_id,
                               FEATURE_ORDER, ordered, missing, fingerprint(material))


def _number(values: dict[str, IntelligenceField], name: str) -> Decimal | None:
    item = values.get(name)
    return Decimal(str(item.value)) if item is not None else None


def _provenance(values: dict[str, IntelligenceField], sources: tuple[str, ...]) -> tuple[FieldProvenance, ...]:
    unique = {}
    for source in sources:
        item = values.get(source)
        for p in item.provenance if item else ():
            key = (p.provider, p.endpoint, p.retrieved_at, p.provider_timestamp,
                   p.fixture_id, p.team_id, p.player_id)
            unique[key] = p
    return tuple(unique[key] for key in sorted(unique, key=lambda item: tuple("" if x is None else str(x) for x in item)))


def _plain(value: object) -> object:
    return format(value.normalize(), "f") if isinstance(value, Decimal) else value
