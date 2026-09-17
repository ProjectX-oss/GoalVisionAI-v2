"""Deterministic capability caching, run-local reuse, and request planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint


CAPABILITY_CACHE_SCHEMA = "goalvision-api-football-capability-cache-v1"
CAPABILITY_CACHE_TTL = timedelta(hours=6)
TEAM_HISTORY_TTL = timedelta(minutes=15)
SEASON_AGGREGATE_TTL = timedelta(hours=6)
INJURY_TTL = timedelta(hours=4)
LINEUP_TTL = timedelta(hours=1)


class CapabilityCacheError(ValueError):
    """Raised when persisted provider capabilities are conflicting or unsafe."""


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    league_id: int
    season: int
    country: str
    competition_name: str
    competition_type: str
    season_start: str
    season_end: str
    fixtures: bool
    standings: bool
    injuries: bool
    lineups: bool
    statistics: bool
    odds: bool
    source_provenance: str


@dataclass(frozen=True, slots=True)
class CompetitionCapabilityCache:
    retrieved_at_utc: datetime
    expires_at_utc: datetime
    records: tuple[CapabilityRecord, ...]
    cache_fingerprint: str

    @classmethod
    def from_provider_payload(
        cls, payload: object, *, retrieved_at_utc: datetime
    ) -> "CompetitionCapabilityCache":
        retrieved = retrieved_at_utc.astimezone(timezone.utc)
        rows = payload.get("response") if isinstance(payload, dict) else None
        by_key: dict[tuple[int, int], CapabilityRecord] = {}
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            league = row.get("league") if isinstance(row.get("league"), dict) else {}
            country = row.get("country") if isinstance(row.get("country"), dict) else {}
            for season in row.get("seasons") if isinstance(row.get("seasons"), list) else []:
                if not isinstance(season, dict) or season.get("current") is not True:
                    continue
                try:
                    league_id = int(league["id"])
                    year = int(season["year"])
                except (KeyError, TypeError, ValueError):
                    continue
                coverage = season.get("coverage") if isinstance(season.get("coverage"), dict) else {}
                fixtures = coverage.get("fixtures")
                fixture_flags = fixtures if isinstance(fixtures, dict) else {}
                record = CapabilityRecord(
                    league_id=league_id,
                    season=year,
                    country=str(country.get("name") or "UNKNOWN"),
                    competition_name=str(league.get("name") or "UNKNOWN"),
                    competition_type=str(league.get("type") or "UNKNOWN"),
                    season_start=str(season.get("start") or ""),
                    season_end=str(season.get("end") or ""),
                    fixtures=(any(bool(value) for value in fixture_flags.values()) if fixture_flags else bool(fixtures)),
                    standings=bool(coverage.get("standings")),
                    injuries=bool(coverage.get("injuries")),
                    lineups=bool(fixture_flags.get("lineups")),
                    statistics=bool(fixture_flags.get("statistics_fixtures")),
                    odds=bool(coverage.get("odds")),
                    source_provenance="API_FOOTBALL_/leagues?current=true",
                )
                key = (league_id, year)
                if key in by_key and by_key[key] != record:
                    raise CapabilityCacheError("API_FOOTBALL_CAPABILITY_CONFLICT")
                by_key[key] = record
        records = tuple(by_key[key] for key in sorted(by_key))
        expires = retrieved + CAPABILITY_CACHE_TTL
        material = _cache_material(retrieved, expires, records)
        return cls(retrieved, expires, records, fingerprint(material))

    @classmethod
    def load(cls, path: Path, *, now: datetime) -> "CompetitionCapabilityCache | None":
        if not path.exists():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        if _contains_secret_key(document):
            raise CapabilityCacheError("API_FOOTBALL_CAPABILITY_CACHE_SECRET_FIELD")
        if document.get("schema_version") != CAPABILITY_CACHE_SCHEMA:
            raise CapabilityCacheError("API_FOOTBALL_CAPABILITY_CACHE_SCHEMA_MISMATCH")
        records = tuple(CapabilityRecord(**item) for item in document.get("records", ()))
        retrieved = _time(document.get("retrieved_at_utc"))
        expires = _time(document.get("expires_at_utc"))
        expected = fingerprint(_cache_material(retrieved, expires, records))
        if document.get("cache_fingerprint") != expected:
            raise CapabilityCacheError("API_FOOTBALL_CAPABILITY_CACHE_FINGERPRINT_MISMATCH")
        cache = cls(retrieved, expires, records, expected)
        return cache if now.astimezone(timezone.utc) <= expires else None

    def save(self, path: Path) -> None:
        root = (Path.cwd() / "var").resolve()
        target = path.resolve()
        if target != root and root not in target.parents:
            raise CapabilityCacheError("Capability cache must be stored beneath var/.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(self.as_document()) + "\n", encoding="utf-8")

    def as_document(self) -> dict:
        return {
            "schema_version": CAPABILITY_CACHE_SCHEMA,
            "retrieved_at_utc": self.retrieved_at_utc.isoformat(),
            "expires_at_utc": self.expires_at_utc.isoformat(),
            "records": [asdict(record) for record in self.records],
            "cache_fingerprint": self.cache_fingerprint,
            "contains_credentials": False,
        }

    def get(self, league_id: int, season: int) -> CapabilityRecord | None:
        return next(
            (record for record in self.records if record.league_id == league_id and record.season == season),
            None,
        )


@dataclass(frozen=True, slots=True)
class CachedProviderValue:
    value: object
    retrieved_at_utc: datetime
    expires_at_utc: datetime
    source_provenance: str


class RunDataCache:
    """Context-bound data reuse for one explicit discovery execution."""

    def __init__(self) -> None:
        self._team_history: dict[tuple[int, int, int, str], CachedProviderValue] = {}
        self._standings: dict[tuple[int, int], CachedProviderValue] = {}
        self._season_aggregates: dict[tuple[int, int, int], CachedProviderValue] = {}
        self._injuries: dict[tuple[int, int], CachedProviderValue] = {}
        self._lineups: dict[int, CachedProviderValue] = {}

    def team_history(
        self, key: tuple[int, int, int, str], *, now: datetime
    ) -> CachedProviderValue | None:
        value = self._team_history.get(key)
        return value if value is not None and now <= value.expires_at_utc else None

    def save_team_history(
        self, key: tuple[int, int, int, str], value: object, *, retrieved_at: datetime
    ) -> CachedProviderValue:
        cached = CachedProviderValue(
            value, retrieved_at, retrieved_at + TEAM_HISTORY_TTL,
            "API_FOOTBALL_/fixtures?team+league+season+last",
        )
        self._team_history[key] = cached
        return cached

    def standings(
        self, key: tuple[int, int], *, now: datetime
    ) -> CachedProviderValue | None:
        value = self._standings.get(key)
        return value if value is not None and now <= value.expires_at_utc else None

    def save_standings(
        self, key: tuple[int, int], value: object, *, retrieved_at: datetime
    ) -> CachedProviderValue:
        cached = CachedProviderValue(
            value, retrieved_at, retrieved_at + TEAM_HISTORY_TTL,
            "API_FOOTBALL_/standings?league+season",
        )
        self._standings[key] = cached
        return cached

    def team_hit_count(self, fixture: dict, *, cutoff: datetime) -> int:
        return sum(
            self.team_history(
                (int(team_id), int(fixture["competition_id"]), int(fixture["season"]), cutoff.isoformat()),
                now=cutoff,
            )
            is not None
            for team_id in (fixture["home_team_id"], fixture["away_team_id"])
        )

    def season_aggregate(
        self, key: tuple[int, int, int], *, now: datetime
    ) -> CachedProviderValue | None:
        return _fresh(self._season_aggregates.get(key), now)

    def save_season_aggregate(
        self, key: tuple[int, int, int], value: object, *, retrieved_at: datetime
    ) -> CachedProviderValue:
        cached = CachedProviderValue(value, retrieved_at, retrieved_at + SEASON_AGGREGATE_TTL, "API_FOOTBALL_/teams/statistics?team+league+season")
        self._season_aggregates[key] = cached
        return cached

    def injuries(
        self, key: tuple[int, int], *, now: datetime
    ) -> CachedProviderValue | None:
        return _fresh(self._injuries.get(key), now)

    def save_injuries(
        self, key: tuple[int, int], value: object, *, retrieved_at: datetime
    ) -> CachedProviderValue:
        cached = CachedProviderValue(value, retrieved_at, retrieved_at + INJURY_TTL, "API_FOOTBALL_/injuries?fixture+team")
        self._injuries[key] = cached
        return cached

    def lineup(self, fixture_id: int, *, now: datetime) -> CachedProviderValue | None:
        return _fresh(self._lineups.get(fixture_id), now)

    def save_lineup(
        self, fixture_id: int, value: object, *, retrieved_at: datetime
    ) -> CachedProviderValue:
        cached = CachedProviderValue(value, retrieved_at, retrieved_at + LINEUP_TTL, "API_FOOTBALL_/fixtures/lineups?fixture")
        self._lineups[fixture_id] = cached
        return cached


@dataclass(frozen=True, slots=True)
class CandidateCostPlan:
    status: str
    baseline_calls: int
    odds_calls: int
    observation_calls: int
    total_mandatory_calls: int
    cache_hits: int
    cache_misses: int
    request_count_before: int
    effective_call_limit: int


def plan_candidate(
    fixture: dict, cache: RunDataCache, *, cutoff: datetime,
    request_count: int, effective_call_limit: int,
) -> CandidateCostPlan:
    hits = cache.team_hit_count(fixture, cutoff=cutoff)
    misses = 2 - hits
    odds_calls = 1
    total = misses + odds_calls
    status = (
        "CANDIDATE_EVALUATION_ALLOWED"
        if request_count + total <= effective_call_limit
        else "CANDIDATE_SKIPPED_QUOTA"
    )
    return CandidateCostPlan(status, misses, odds_calls, 0, total, hits, misses, request_count, effective_call_limit)


def empty_candidate_costs() -> dict:
    return {
        "fixture_list": 0,
        "team_history": 0,
        "standings": 0,
        "injuries": 0,
        "lineups": 0,
        "statistics": 0,
        "odds": 0,
        "retries": 0,
    }


def _cache_material(retrieved: datetime, expires: datetime, records) -> dict:
    return {
        "schema_version": CAPABILITY_CACHE_SCHEMA,
        "retrieved_at_utc": retrieved.isoformat(),
        "expires_at_utc": expires.isoformat(),
        "records": [asdict(record) for record in records],
        "contains_credentials": False,
    }


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise CapabilityCacheError("API_FOOTBALL_CAPABILITY_CACHE_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapabilityCacheError("API_FOOTBALL_CAPABILITY_CACHE_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise CapabilityCacheError("API_FOOTBALL_CAPABILITY_CACHE_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            (
                any(token in str(key).casefold() for token in ("secret", "token", "api_key", "credential"))
                and not (str(key) == "contains_credentials" and item is False)
            )
            or _contains_secret_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _fresh(value: CachedProviderValue | None, now: datetime) -> CachedProviderValue | None:
    return value if value is not None and now <= value.expires_at_utc else None
