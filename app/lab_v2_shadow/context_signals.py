"""Opponent-adjusted form and conservative player-availability signals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Iterable, Mapping

from .pi_ratings import MatchResult, PiRatingAdapter


@dataclass(frozen=True, slots=True)
class OpponentAdjustedForm:
    state: str
    team_id: int
    score: Decimal | None
    observations: int
    components: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class PlayerUsage:
    player_id: str
    starts: int | None = None
    minutes: int | None = None
    recent_start_frequency: Decimal | None = None
    position: str | None = None
    goals: int | None = None
    assists: int | None = None


@dataclass(frozen=True, slots=True)
class AvailabilityImpact:
    state: str
    absent_count: int
    injury_count: int
    suspension_count: int
    impact: Decimal
    weighted_players: tuple[dict[str, object], ...]
    explanation: str


def opponent_adjusted_form(
    team_id: int,
    matches: Iterable[MatchResult],
    ratings: PiRatingAdapter,
    *,
    window: int = 8,
) -> OpponentAdjustedForm:
    """Reward results relative to current same-league opponent strength."""
    relevant = [item for item in matches if team_id in (item.home_team_id, item.away_team_id)]
    relevant.sort(key=lambda item: (item.kickoff_utc, item.fixture_id), reverse=True)
    components = []
    for match in relevant[:window]:
        home = match.home_team_id == team_id
        opponent = match.away_team_id if home else match.home_team_id
        scored = match.home_goals if home else match.away_goals
        conceded = match.away_goals if home else match.home_goals
        team_rating = ratings.rating(team_id).home if home else ratings.rating(team_id).away
        opponent_rating = ratings.rating(opponent).away if home else ratings.rating(opponent).home
        expected = _logistic(team_rating - opponent_rating)
        actual = Decimal(1) if scored > conceded else Decimal("0.5") if scored == conceded else Decimal(0)
        goal_adjustment = max(Decimal("-0.10"), min(Decimal("0.10"), Decimal(scored - conceded) * Decimal("0.025")))
        performance = max(Decimal(0), min(Decimal(1), Decimal("0.5") + (actual - expected) + goal_adjustment))
        components.append({
            "fixture_id": match.fixture_id,
            "opponent_team_id": opponent,
            "venue": "HOME" if home else "AWAY",
            "score": f"{scored}-{conceded}",
            "expected_result": expected,
            "actual_result": actual,
            "goal_margin_adjustment": goal_adjustment,
            "performance": performance,
        })
    if len(components) < 3:
        return OpponentAdjustedForm("INSUFFICIENT", int(team_id), None, len(components), tuple(components))
    weights = [Decimal(index) for index in range(len(components), 0, -1)]
    score = sum((item["performance"] * weight for item, weight in zip(components, weights, strict=True)), Decimal(0)) / sum(weights)
    return OpponentAdjustedForm("AVAILABLE", int(team_id), score, len(components), tuple(components))


def availability_impact(
    absences: Iterable[Mapping[str, object]],
    usage: Mapping[str, PlayerUsage] | None = None,
) -> AvailabilityImpact:
    """Use objective usage when present, otherwise expose a count-only fallback."""
    unique: dict[str, Mapping[str, object]] = {}
    for row in absences:
        player_id = str(row.get("player_id") or "").strip()
        if player_id:
            unique[player_id] = row
    injuries = sum(str(item.get("status") or "").upper() == "INJURED" for item in unique.values())
    suspensions = sum(str(item.get("status") or "").upper() == "SUSPENDED" for item in unique.values())
    usage = usage or {}
    weighted = []
    for player_id, absence in sorted(unique.items()):
        player = usage.get(player_id)
        if player is None:
            continue
        importance, evidence = _importance(player)
        if importance is not None:
            weighted.append({
                "player_id": player_id,
                "status": str(absence.get("status") or "UNKNOWN"),
                "objective_importance": importance,
                "evidence": evidence,
            })
    if weighted:
        impact = min(Decimal("0.50"), sum((item["objective_importance"] for item in weighted), Decimal(0)) * Decimal("0.20"))
        return AvailabilityImpact(
            "USAGE_WEIGHTED", len(unique), injuries, suspensions, impact,
            tuple(weighted), "Impact derives from provider usage; no subjective key-player label.",
        )
    impact = min(Decimal("0.20"), Decimal(len(unique)) * Decimal("0.025"))
    return AvailabilityImpact(
        "COUNT_FALLBACK", len(unique), injuries, suspensions, impact, (),
        "Provider usage unavailable; conservative absence-count fallback applied.",
    )


def _importance(player: PlayerUsage) -> tuple[Decimal | None, dict[str, object]]:
    components = []
    if player.recent_start_frequency is not None:
        components.append((Decimal("0.50"), _clamp(player.recent_start_frequency), "recent_start_frequency"))
    if player.minutes is not None and player.minutes >= 0:
        components.append((Decimal("0.30"), min(Decimal(1), Decimal(player.minutes) / Decimal(900)), "minutes_per_10_matches"))
    if player.starts is not None and player.starts >= 0:
        components.append((Decimal("0.15"), min(Decimal(1), Decimal(player.starts) / Decimal(10)), "starts_per_10_matches"))
    if player.goals is not None or player.assists is not None:
        contributions = max(0, (player.goals or 0) + (player.assists or 0))
        components.append((Decimal("0.05"), min(Decimal(1), Decimal(contributions) / Decimal(5)), "goal_contributions"))
    if not components:
        return None, {}
    total_weight = sum((weight for weight, _, _ in components), Decimal(0))
    score = sum((weight * value for weight, value, _ in components), Decimal(0)) / total_weight
    return score, {name: value for _, value, name in components} | {"position": player.position}


def _logistic(value: Decimal) -> Decimal:
    # A bounded rational approximation is deterministic and sufficient for an
    # interpretable form adjustment; it is not represented as calibrated odds.
    with localcontext() as context:
        context.prec = 28
        return Decimal("0.5") + value / (Decimal(2) * (Decimal(1) + abs(value)))


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal(0), min(Decimal(1), value))


def decimal_or_none(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None
