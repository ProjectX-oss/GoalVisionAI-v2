"""API-Football league/season capability tiers with a static metadata cache."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
import json
from pathlib import Path

from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint


CACHE_SCHEMA = "goalvision-lab-v2-league-capabilities-v1"
CACHE_TTL = timedelta(days=7)


class CapabilityTier(StrEnum):
    TIER_A_FULL = "TIER_A_FULL"
    TIER_B_GOOD = "TIER_B_GOOD"
    TIER_C_BASIC = "TIER_C_BASIC"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class LeagueCapability:
    league_id: int
    season: int
    country: str
    competition_name: str
    competition_type: str
    season_start: str
    season_end: str
    fixtures: bool
    standings: bool
    lineups: bool
    fixture_statistics: bool
    player_statistics: bool
    injuries: bool
    predictions: bool
    odds: bool
    tier: CapabilityTier
    reasons: tuple[str, ...]

    @classmethod
    def from_api_row(cls, row: object, season: object) -> "LeagueCapability | None":
        if not isinstance(row, dict) or not isinstance(season, dict):
            return None
        league = row.get("league") if isinstance(row.get("league"), dict) else {}
        country = row.get("country") if isinstance(row.get("country"), dict) else {}
        coverage = season.get("coverage") if isinstance(season.get("coverage"), dict) else {}
        fixture = coverage.get("fixtures") if isinstance(coverage.get("fixtures"), dict) else {}
        try:
            league_id, year = int(league["id"]), int(season["year"])
        except (KeyError, TypeError, ValueError):
            return None
        fixtures = any(bool(value) for value in fixture.values()) if fixture else bool(coverage.get("fixtures"))
        lineups = bool(fixture.get("lineups"))
        fixture_statistics = bool(fixture.get("statistics_fixtures"))
        player_statistics = bool(fixture.get("statistics_players") or coverage.get("players"))
        standings = bool(coverage.get("standings"))
        injuries = bool(coverage.get("injuries"))
        predictions = bool(coverage.get("predictions"))
        odds = bool(coverage.get("odds"))
        tier, reasons = classify_capability(
            fixtures=fixtures,
            odds=odds,
            standings=standings,
            lineups=lineups,
            fixture_statistics=fixture_statistics,
            player_statistics=player_statistics,
            injuries=injuries,
        )
        return cls(
            league_id=league_id,
            season=year,
            country=str(country.get("name") or "UNKNOWN"),
            competition_name=str(league.get("name") or "UNKNOWN"),
            competition_type=str(league.get("type") or "UNKNOWN"),
            season_start=str(season.get("start") or ""),
            season_end=str(season.get("end") or ""),
            fixtures=fixtures,
            standings=standings,
            lineups=lineups,
            fixture_statistics=fixture_statistics,
            player_statistics=player_statistics,
            injuries=injuries,
            predictions=predictions,
            odds=odds,
            tier=tier,
            reasons=reasons,
        )

    def covers(self, day: date) -> bool:
        try:
            return date.fromisoformat(self.season_start) <= day <= date.fromisoformat(self.season_end)
        except ValueError:
            return False


def classify_capability(
    *, fixtures: bool, odds: bool, standings: bool, lineups: bool,
    fixture_statistics: bool, player_statistics: bool, injuries: bool,
) -> tuple[CapabilityTier, tuple[str, ...]]:
    """Classify data ability, never league prestige or geography."""
    if not fixtures or not odds:
        missing = tuple(name for name, value in (("FIXTURES", fixtures), ("CURRENT_ODDS", odds)) if not value)
        return CapabilityTier.UNSUPPORTED, tuple(f"MISSING_{name}" for name in missing)
    if all((lineups, injuries, fixture_statistics, player_statistics)):
        return CapabilityTier.TIER_A_FULL, ("FULL_CURRENT_MATCH_INTELLIGENCE",)
    if standings or fixture_statistics:
        missing = tuple(
            name for name, value in (
                ("LINEUPS", lineups), ("INJURIES", injuries),
                ("PLAYER_STATISTICS", player_statistics),
            ) if not value
        )
        return CapabilityTier.TIER_B_GOOD, tuple(f"OPTIONAL_{name}_UNAVAILABLE" for name in missing)
    return CapabilityTier.TIER_C_BASIC, (
        "RESULT_HISTORY_AND_CURRENT_ODDS_ONLY",
        "ADVANCED_CONTEXT_NOT_REQUIRED_FOR_PI_OR_CURRENT_MARKET",
    )


@dataclass(frozen=True, slots=True)
class LeagueCapabilityCache:
    retrieved_at_utc: datetime
    expires_at_utc: datetime
    records: tuple[LeagueCapability, ...]
    content_fingerprint: str

    @classmethod
    def from_api_payload(cls, payload: object, *, retrieved_at: datetime) -> "LeagueCapabilityCache":
        observed = _utc(retrieved_at)
        rows = payload.get("response") if isinstance(payload, dict) else None
        records: dict[tuple[int, int], LeagueCapability] = {}
        for row in rows if isinstance(rows, list) else ():
            seasons = row.get("seasons") if isinstance(row, dict) and isinstance(row.get("seasons"), list) else ()
            for season in seasons:
                if not isinstance(season, dict) or season.get("current") is not True:
                    continue
                record = LeagueCapability.from_api_row(row, season)
                if record is not None:
                    records[(record.league_id, record.season)] = record
        ordered = tuple(records[key] for key in sorted(records))
        expires = observed + CACHE_TTL
        material = _material(observed, expires, ordered)
        return cls(observed, expires, ordered, fingerprint(material))

    def current(self, league_id: int, season: int, *, day: date) -> LeagueCapability | None:
        return next((item for item in self.records
                     if item.league_id == league_id and item.season == season and item.covers(day)), None)

    def save(self, path: Path) -> None:
        target = path.resolve()
        root = (Path.cwd() / "var").resolve()
        if root not in target.parents:
            raise ValueError("LAB_V2_CAPABILITY_CACHE_MUST_BE_BENEATH_VAR")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(self.document()) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path, *, now: datetime) -> "LeagueCapabilityCache | None":
        if not path.is_file():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != CACHE_SCHEMA:
            return None
        retrieved, expires = _parse_time(document.get("retrieved_at_utc")), _parse_time(document.get("expires_at_utc"))
        records = tuple(
            LeagueCapability(
                **{**item, "tier": CapabilityTier(item["tier"]), "reasons": tuple(item["reasons"])}
            ) for item in document.get("records", ())
        )
        expected = fingerprint(_material(retrieved, expires, records))
        if expected != document.get("content_fingerprint"):
            raise ValueError("LAB_V2_CAPABILITY_CACHE_FINGERPRINT_MISMATCH")
        cache = cls(retrieved, expires, records, expected)
        return cache if _utc(now) <= expires else None

    def document(self) -> dict[str, object]:
        return {
            "schema_version": CACHE_SCHEMA,
            "retrieved_at_utc": self.retrieved_at_utc.isoformat(),
            "expires_at_utc": self.expires_at_utc.isoformat(),
            "records": [{**asdict(item), "tier": item.tier.value} for item in self.records],
            "content_fingerprint": self.content_fingerprint,
            "contains_credentials": False,
        }


def _material(retrieved: datetime, expires: datetime, records: tuple[LeagueCapability, ...]) -> dict[str, object]:
    return {
        "schema_version": CACHE_SCHEMA,
        "retrieved_at_utc": retrieved.isoformat(),
        "expires_at_utc": expires.isoformat(),
        "records": [{**asdict(item), "tier": item.tier.value} for item in records],
        "contains_credentials": False,
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("CAPABILITY_TIMESTAMP_REQUIRES_OFFSET")
    return value.astimezone(timezone.utc)


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("LAB_V2_CAPABILITY_CACHE_TIME_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed)
