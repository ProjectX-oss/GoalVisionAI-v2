"""Pure API-Football normalization with no subjective football claims."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

from app.form_features import (
    ExistingFootballHistoricalAdapter,
    FormFeaturePolicy,
    FormSnapshotBuilder,
    VenueSplit,
)
from app.team_availability.normalization import (
    normalize_formation,
    normalize_player,
    normalize_position,
)

from .models import DataClass, FieldProvenance, IntelligenceField


def fixture_identity(payload: object) -> dict[str, object]:
    """Extract one complete upcoming-fixture identity from API-Football."""
    rows = _rows(payload)
    if len(rows) != 1:
        raise ValueError("FIXTURE_IDENTITY_NOT_UNIQUE")
    row = rows[0]
    fixture = _dict(row.get("fixture"))
    league = _dict(row.get("league"))
    teams = _dict(row.get("teams"))
    home, away = _dict(teams.get("home")), _dict(teams.get("away"))
    venue = _dict(fixture.get("venue"))
    kickoff = _time(fixture.get("date"))
    required = (fixture.get("id"), league.get("id"), league.get("season"), home.get("id"), away.get("id"))
    if any(value is None for value in required):
        raise ValueError("FIXTURE_IDENTITY_INCOMPLETE")
    return {
        "fixture_id": str(fixture["id"]), "kickoff_utc": kickoff,
        "competition_id": int(league["id"]), "competition": str(league.get("name") or "UNKNOWN"),
        "competition_country": league.get("country"), "competition_round": league.get("round"),
        "season": int(league["season"]), "home_team_id": int(home["id"]),
        "home_team": str(home.get("name") or home["id"]), "away_team_id": int(away["id"]),
        "away_team": str(away.get("name") or away["id"]), "venue_id": venue.get("id"),
        "venue": venue.get("name"), "venue_city": venue.get("city"),
        "referee": fixture.get("referee"), "raw": row,
    }


def normalize_fixture_fields(identity: dict, provenance: FieldProvenance) -> list[IntelligenceField]:
    """Normalize stable fixture identity and context fields."""
    mapping = {
        "fixture.id": "fixture_id", "fixture.kickoff_utc": "kickoff_utc",
        "competition.id": "competition_id", "competition.name": "competition",
        "competition.country": "competition_country", "competition.round": "competition_round",
        "competition.season": "season", "home.team_id": "home_team_id", "home.team_name": "home_team",
        "away.team_id": "away_team_id", "away.team_name": "away_team", "fixture.venue_id": "venue_id",
        "fixture.venue": "venue", "fixture.venue_city": "venue_city", "fixture.referee": "referee",
    }
    return [
        IntelligenceField(name, DataClass.PRE_MATCH_STABLE, _json_value(identity.get(key)), (provenance,))
        for name, key in mapping.items() if identity.get(key) is not None
    ]


def normalize_lineups(payload: object, *, identity: dict, provenance: FieldProvenance) -> tuple[list[IntelligenceField], dict[str, set[str]]]:
    """Normalize actual lineup rows; an empty response never implies a lineup."""
    fields: list[IntelligenceField] = []
    starters: dict[str, set[str]] = {"home": set(), "away": set()}
    team_side = {str(identity["home_team_id"]): "home", str(identity["away_team_id"]): "away"}
    for row in _rows(payload):
        team = _dict(row.get("team")); side = team_side.get(str(team.get("id")))
        if side is None:
            continue
        team_id = str(team["id"])
        base = _with(provenance, team_id=team_id)
        formation = row.get("formation")
        if formation:
            fields.append(IntelligenceField(f"{side}.formation", DataClass.LINEUP_SENSITIVE, normalize_formation(str(formation)), (base,)))
        for group, is_starting in (("startXI", True), ("substitutes", False)):
            for order, wrapped in enumerate(row.get(group) if isinstance(row.get(group), list) else []):
                player = _dict(_dict(wrapped).get("player")); player_id = player.get("id")
                if player_id is None:
                    continue
                normalized_player = normalize_player(player_id, str(player.get("name") or ""))
                key = str(normalized_player.player_id); player_prov = _with(base, player_id=key)
                prefix = f"{side}.lineup.{'starters' if is_starting else 'substitutes'}.{key}"
                fields.extend((
                    IntelligenceField(prefix + ".player_id", DataClass.LINEUP_SENSITIVE, key, (player_prov,)),
                    IntelligenceField(prefix + ".name", DataClass.LINEUP_SENSITIVE, normalized_player.player_name, (player_prov,)),
                    IntelligenceField(prefix + ".position", DataClass.LINEUP_SENSITIVE, normalize_position(str(player.get("pos") or "UNKNOWN")), (player_prov,)),
                    IntelligenceField(prefix + ".order", DataClass.LINEUP_SENSITIVE, order, (player_prov,)),
                ))
                if is_starting:
                    starters[side].add(key)
        fields.append(IntelligenceField(f"{side}.lineup.confirmed", DataClass.LINEUP_SENSITIVE, True, (base,)))
    return fields, starters


def normalize_injuries(payload: object, *, identity: dict, provenance: FieldProvenance) -> tuple[list[IntelligenceField], dict[str, set[str]], dict[str, set[str]]]:
    """Normalize fixture absences without assigning subjective importance."""
    fields: list[IntelligenceField] = []
    injured = {"home": set(), "away": set()}; suspended = {"home": set(), "away": set()}
    team_side = {str(identity["home_team_id"]): "home", str(identity["away_team_id"]): "away"}
    for row in _rows(payload):
        team, player = _dict(row.get("team")), _dict(row.get("player"))
        side = team_side.get(str(team.get("id"))); player_id = player.get("id")
        if side is None or player_id is None:
            continue
        key = str(player_id); team_id = str(team["id"])
        reason = str(player.get("reason") or "UNKNOWN")
        provider_type = str(player.get("type") or "UNKNOWN")
        suspension_words = ("suspension", "suspended", "red card", "yellow cards")
        status = "SUSPENDED" if any(word in reason.casefold() for word in suspension_words) else "INJURED"
        (suspended if status == "SUSPENDED" else injured)[side].add(key)
        p = _with(provenance, team_id=team_id, player_id=key)
        prefix = f"{side}.availability.{key}"
        for suffix, value in (("player_id", key), ("name", str(player.get("name") or key)),
                              ("status", status), ("availability", "UNAVAILABLE"),
                              ("provider_type", provider_type), ("reason", reason)):
            fields.append(IntelligenceField(prefix + "." + suffix, DataClass.PRE_MATCH_DYNAMIC, value, (p,)))
    for side, team_key in (("home", "home_team_id"), ("away", "away_team_id")):
        p = _with(provenance, team_id=str(identity[team_key]))
        fields.extend((
            IntelligenceField(f"{side}.availability.injury_count", DataClass.PRE_MATCH_DYNAMIC, len(injured[side]), (p,)),
            IntelligenceField(f"{side}.availability.suspension_count", DataClass.PRE_MATCH_DYNAMIC, len(suspended[side]), (p,)),
        ))
    return fields, injured, suspended


def normalize_team_statistics(payload: object, *, side: str, team_id: int, provenance: FieldProvenance) -> list[IntelligenceField]:
    root = _dict(_dict(payload).get("response"))
    fixtures, goals = _dict(root.get("fixtures")), _dict(root.get("goals"))
    played, wins, draws, losses = (_dict(fixtures.get(name)) for name in ("played", "wins", "draws", "loses"))
    gf, ga = _dict(goals.get("for")), _dict(goals.get("against"))
    p = _with(provenance, team_id=str(team_id))
    values = {
        "season.matches_played": played.get("total"), "season.wins": wins.get("total"),
        "season.draws": draws.get("total"), "season.losses": losses.get("total"),
        "season.goals_for": _dict(gf.get("total")).get("total"),
        "season.goals_against": _dict(ga.get("total")).get("total"),
        "season.home.matches_played": played.get("home"), "season.away.matches_played": played.get("away"),
        "season.home.wins": wins.get("home"), "season.away.wins": wins.get("away"),
        "season.home.goals_for": _dict(gf.get("total")).get("home"),
        "season.away.goals_for": _dict(gf.get("total")).get("away"),
        "season.home.goals_against": _dict(ga.get("total")).get("home"),
        "season.away.goals_against": _dict(ga.get("total")).get("away"),
    }
    return [IntelligenceField(f"{side}.{name}", DataClass.PRE_MATCH_STABLE, value, (p,))
            for name, value in values.items() if value is not None]


def history_context(rows: object, *, side: str, team_id: int, kickoff: datetime, provenance: FieldProvenance) -> tuple[list[IntelligenceField], list[int]]:
    raw_rows = tuple(rows) if isinstance(rows, list) else ()
    observations = ExistingFootballHistoricalAdapter(
        raw_rows, observed_at=provenance.retrieved_at
    ).historical_matches().observations
    snapshot = FormSnapshotBuilder().build(
        target_fixture_id=provenance.fixture_id, target_kickoff=kickoff,
        team_id=str(team_id), venue=VenueSplit.HOME if side == "home" else VenueSplit.AWAY,
        evaluation_timestamp=provenance.retrieved_at,
        historical_observations=observations,
        policy=FormFeaturePolicy(recent_window=10, missing_opponent_fallback=Decimal("1")),
    ).form
    selected = [item for item in observations if item.fixture_id in set(snapshot.selected_fixture_ids)]
    selected.sort(key=lambda item: (item.kickoff_time, item.fixture_id))
    recent = selected[-10:]
    metrics = snapshot.recent
    venue_metrics = snapshot.home if side == "home" else snapshot.away
    p = _with(provenance, team_id=str(team_id))
    complete_7 = len(recent) < 10 or bool(
        recent and recent[0].kickoff_time <= kickoff - timedelta(days=7)
    )
    complete_14 = len(recent) < 10 or bool(
        recent and recent[0].kickoff_time <= kickoff - timedelta(days=14)
    )
    competition_by_fixture = {
        str(_dict(row.get("fixture")).get("id")): str(
            _dict(row.get("league")).get("name") or ""
        )
        for row in raw_rows if isinstance(row, dict)
    }
    values = {
        "recent.match_count": metrics.matches_played, "recent.points": metrics.points,
        "recent.goals_for": metrics.goals_for, "recent.goals_against": metrics.goals_against,
        "venue_recent.match_count": venue_metrics.matches_played,
        "venue_recent.goals_for": venue_metrics.goals_for,
        "venue_recent.goals_against": venue_metrics.goals_against,
        "rest_days": max(0, int((kickoff - recent[-1].kickoff_time).total_seconds() // 86400)) if recent else None,
        "matches_previous_7_days": (sum(item.kickoff_time >= kickoff - timedelta(days=7) for item in recent)
                                    if complete_7 else None),
        "matches_previous_14_days": (sum(item.kickoff_time >= kickoff - timedelta(days=14) for item in recent)
                                     if complete_14 else None),
        "schedule_7_day_window_complete": complete_7,
        "schedule_14_day_window_complete": complete_14,
        "recent_cup_or_european_matches": sum(
            _cup_or_europe(competition_by_fixture.get(item.fixture_id, ""))
            for item in recent[-5:]
        ),
    }
    fields = [IntelligenceField(f"{side}.{name}", DataClass.PRE_MATCH_DYNAMIC, value, (p,))
              for name, value in values.items() if value is not None]
    return fields, [int(item.fixture_id) for item in reversed(recent[-3:])]


def aggregate_fixture_statistics(payloads: Iterable[tuple[object, FieldProvenance]], *, side: str, team_id: int) -> list[IntelligenceField]:
    values: dict[str, list[Decimal]] = {key: [] for key in ("shots", "shots_on_target", "possession", "corners", "yellow_cards", "red_cards", "xg", "xg_against")}
    provenances: list[FieldProvenance] = []
    aliases = {"total shots": "shots", "shots on goal": "shots_on_target", "ball possession": "possession",
               "corner kicks": "corners", "yellow cards": "yellow_cards", "red cards": "red_cards", "expected_goals": "xg"}
    for payload, p in payloads:
        fixture_xg: dict[str, Decimal] = {}
        for row in _rows(payload):
            for stat in row.get("statistics") if isinstance(row.get("statistics"), list) else []:
                if str(_dict(stat).get("type") or "").casefold() == "expected_goals":
                    value = _decimal(_dict(stat).get("value"))
                    identity = _dict(row.get("team")).get("id")
                    if value is not None and identity is not None:
                        fixture_xg[str(identity)] = value
        for row in _rows(payload):
            if str(_dict(row.get("team")).get("id")) != str(team_id):
                continue
            seen = False
            for stat in row.get("statistics") if isinstance(row.get("statistics"), list) else []:
                name = aliases.get(str(_dict(stat).get("type") or "").casefold())
                value = _decimal(_dict(stat).get("value"))
                if name and value is not None:
                    values[name].append(value); seen = True
            if seen:
                provenances.append(_with(p, team_id=str(team_id)))
                opponents = [value for identity, value in fixture_xg.items() if identity != str(team_id)]
                if len(opponents) == 1:
                    values["xg_against"].append(opponents[0])
    fields = []
    for name, items in values.items():
        if items:
            fields.append(IntelligenceField(f"{side}.recent_{name}_per_match", DataClass.PRE_MATCH_DYNAMIC,
                                            str(sum(items, Decimal(0)) / len(items)), tuple(provenances)))
    if provenances:
        fields.append(IntelligenceField(f"{side}.recent_detailed_statistics_sample_size",
                                        DataClass.PRE_MATCH_DYNAMIC, len(provenances), tuple(provenances)))
    return fields


def recent_starting_sets(payloads: Iterable[object], team_id: int) -> list[set[str]]:
    result = []
    for payload in payloads:
        for row in _rows(payload):
            if str(_dict(row.get("team")).get("id")) != str(team_id):
                continue
            result.append({str(_dict(_dict(item).get("player")).get("id")) for item in row.get("startXI", [])
                           if _dict(_dict(item).get("player")).get("id") is not None})
    return result


def _rows(payload: object) -> list[dict]:
    rows = _dict(payload).get("response")
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _time(value: object) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("TIMESTAMP_REQUIRES_OFFSET")
    return result.astimezone(timezone.utc)


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _with(value: FieldProvenance, *, team_id: str | None = None, player_id: str | None = None) -> FieldProvenance:
    return FieldProvenance(value.provider, value.endpoint, value.retrieved_at,
                           value.provider_timestamp, value.fixture_id,
                           team_id if team_id is not None else value.team_id,
                           player_id if player_id is not None else value.player_id)


def _json_value(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime) else value


def _cup_or_europe(name: str) -> bool:
    text = name.casefold()
    return any(word in text for word in ("cup", "champions league", "europa", "conference league"))
