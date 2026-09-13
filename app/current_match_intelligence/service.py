"""Bounded, cached and deterministic current-match enrichment service."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from app.current_odds_forward_test.input import (
    CurrentOddsValidationError,
    normalize_api_football_current_odds,
    parse_current_odds,
)

from .features import derive_features
from .models import (
    ApiCallEvidence,
    DataClass,
    EnrichmentResult,
    FieldProvenance,
    FreshnessEvidence,
    FreshnessStatus,
    IntelligenceField,
    SCHEMA_VERSION,
)
from .normalization import (
    aggregate_fixture_statistics,
    fixture_identity,
    history_context,
    normalize_fixture_fields,
    normalize_injuries,
    normalize_lineups,
    normalize_team_statistics,
    recent_starting_sets,
)
from .policy import IntelligenceBudgetPolicy, IntelligenceFreshnessPolicy
from .provider import CurrentMatchProvider, retrieved_at
from .repository import SQLiteCurrentMatchIntelligenceRepository


class CurrentMatchIntelligenceService:
    """Collect one strongest candidate after cheap discovery has survived."""

    def __init__(
        self,
        repository: SQLiteCurrentMatchIntelligenceRepository,
        provider: CurrentMatchProvider,
        *,
        freshness: IntelligenceFreshnessPolicy = IntelligenceFreshnessPolicy(),
        budget: IntelligenceBudgetPolicy = IntelligenceBudgetPolicy(),
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.freshness = freshness
        self.budget = budget
        self.calls: list[ApiCallEvidence] = []

    async def collect(
        self,
        fixture_id: int,
        *,
        evaluated_at: datetime,
        force_refresh: frozenset[str] = frozenset(),
    ) -> EnrichmentResult:
        """Collect one snapshot, optionally bypassing selected source caches.

        ``force_refresh`` accepts source names from the collection plan, not
        endpoint names.  This keeps a final-review fixture refresh independent
        from the slower team-history and team-statistics clocks.
        """
        self.calls = []
        now = _utc(evaluated_at)
        supported_refresh = {"fixture", "lineup", "injuries", "odds"}
        if not force_refresh <= supported_refresh:
            raise ValueError("UNSUPPORTED_CURRENT_INTELLIGENCE_REFRESH_SOURCE")
        if self.provider.request_count > self.budget.maximum_api_calls:
            raise ValueError("API_FOOTBALL_REQUEST_LIMIT_ALREADY_EXCEEDED")
        self.provider.restrict_requests(self.budget.maximum_api_calls, daily_reserve=20)
        start_count = self.provider.request_count
        fixture_source = await self._fetch(
            "/fixtures", {"id": fixture_id}, self.freshness.fixture,
            lambda: self.provider.fixture(fixture_id), now=now, required=True,
            force_refresh="fixture" in force_refresh,
        )
        if fixture_source is None:
            raise ValueError("CURRENT_FIXTURE_UNAVAILABLE")
        identity = fixture_identity(fixture_source["payload"])
        if identity["fixture_id"] != str(fixture_id):
            raise ValueError("FIXTURE_IDENTITY_MISMATCH")
        kickoff = identity["kickoff_utc"]
        if kickoff <= now:
            raise ValueError("FIXTURE_ALREADY_STARTED")

        fields = normalize_fixture_fields(
            identity, self._provenance(fixture_source, str(fixture_id), "/fixtures")
        )
        sources: dict[str, dict | None] = {"fixture": fixture_source}
        required_specs = (
            ("lineup", "/fixtures/lineups", {"fixture": fixture_id}, self.freshness.confirmed_lineup, lambda: self.provider.lineup(fixture_id)),
            ("injuries", "/injuries", {"fixture": fixture_id}, self.freshness.injuries, lambda: self.provider.injuries(fixture_id)),
            ("home_stats", "/teams/statistics", {"team": identity["home_team_id"], "league": identity["competition_id"], "season": identity["season"]}, self.freshness.team_statistics, lambda: self.provider.team_statistics(identity["home_team_id"], identity["competition_id"], identity["season"])),
            ("away_stats", "/teams/statistics", {"team": identity["away_team_id"], "league": identity["competition_id"], "season": identity["season"]}, self.freshness.team_statistics, lambda: self.provider.team_statistics(identity["away_team_id"], identity["competition_id"], identity["season"])),
            ("home_history", "/fixtures", {"team": identity["home_team_id"], "league": identity["competition_id"], "season": identity["season"], "last": self.budget.recent_match_window}, self.freshness.team_history, lambda: self.provider.last_matches(identity["home_team_id"], last=self.budget.recent_match_window, league_id=identity["competition_id"], season=identity["season"])),
            ("away_history", "/fixtures", {"team": identity["away_team_id"], "league": identity["competition_id"], "season": identity["season"], "last": self.budget.recent_match_window}, self.freshness.team_history, lambda: self.provider.last_matches(identity["away_team_id"], last=self.budget.recent_match_window, league_id=identity["competition_id"], season=identity["season"])),
            ("odds", "/odds", {"fixture": fixture_id}, self.freshness.odds, lambda: self.provider.current_odds(fixture_id)),
        )
        uncached = sum(
            name in force_refresh or self.repository.cached(endpoint, query, now=now) is None
            for name, endpoint, query, _, _ in required_specs
        )
        blockers: list[str] = []
        if self._remaining() < uncached:
            blockers.append("INTELLIGENCE_REQUIRED_STAGE_BUDGET_INSUFFICIENT")
        else:
            for name, endpoint, query, ttl, operation in required_specs:
                sources[name] = await self._fetch(
                    endpoint, query, ttl, operation, now=now, required=True,
                    force_refresh=name in force_refresh,
                )

        current_starters = {"home": set(), "away": set()}
        injured = {"home": set(), "away": set()}; suspended = {"home": set(), "away": set()}
        lineup = sources.get("lineup")
        if lineup:
            values, current_starters = normalize_lineups(
                lineup["payload"], identity=identity,
                provenance=self._provenance(lineup, str(fixture_id), "/fixtures/lineups"),
            )
            fields.extend(values)
        injury = sources.get("injuries")
        if injury:
            values, injured, suspended = normalize_injuries(
                injury["payload"], identity=identity,
                provenance=self._provenance(injury, str(fixture_id), "/injuries"),
            )
            fields.extend(values)
        for side in ("home", "away"):
            stats = sources.get(f"{side}_stats")
            if stats:
                fields.extend(normalize_team_statistics(
                    stats["payload"], side=side, team_id=identity[f"{side}_team_id"],
                    provenance=self._provenance(stats, str(fixture_id), "/teams/statistics"),
                ))

        recent_fixture_ids: dict[str, list[int]] = {"home": [], "away": []}
        for side in ("home", "away"):
            history = sources.get(f"{side}_history")
            if history:
                values, recent_fixture_ids[side] = history_context(
                    history["payload"], side=side, team_id=identity[f"{side}_team_id"],
                    kickoff=kickoff,
                    provenance=self._provenance(history, str(fixture_id), "/fixtures"),
                )
                fields.extend(values)
        detailed_stats: dict[int, dict] = {}
        historical_lineups: dict[int, dict] = {}
        optional_ids = []
        for side in ("home", "away"):
            optional_ids.extend(recent_fixture_ids[side][: self.budget.detailed_match_window])
        for past_id in dict.fromkeys(optional_ids):
            stat = await self._fetch(
                "/fixtures/statistics", {"fixture": past_id},
                self.freshness.historical_fixture_statistics,
                lambda value=past_id: self.provider.fixture_statistics(value),
                now=now, required=False,
            )
            if stat:
                detailed_stats[past_id] = stat
            needs_lineup = any(
                current_starters[side] and past_id in recent_fixture_ids[side]
                for side in ("home", "away")
            )
            if needs_lineup:
                old_lineup = await self._fetch(
                    "/fixtures/lineups", {"fixture": past_id}, self.freshness.historical_lineup,
                    lambda value=past_id: self.provider.lineup(value), now=now, required=False,
                )
                if old_lineup:
                    historical_lineups[past_id] = old_lineup
            if self._remaining() == 0:
                break

        prior_sets: dict[str, list[set[str]]] = {"home": [], "away": []}
        for side in ("home", "away"):
            ids = recent_fixture_ids[side][: self.budget.detailed_match_window]
            stat_inputs = [(detailed_stats[value]["payload"], self._provenance(detailed_stats[value], str(fixture_id), "/fixtures/statistics"))
                           for value in ids if value in detailed_stats]
            fields.extend(aggregate_fixture_statistics(
                stat_inputs, side=side, team_id=identity[f"{side}_team_id"]
            ))
            prior_sets[side] = recent_starting_sets(
                [historical_lineups[value]["payload"] for value in ids if value in historical_lineups],
                identity[f"{side}_team_id"],
            )
            usage = Counter(player for starting in prior_sets[side] for player in starting)
            for player_id in sorted(usage):
                evidence = []
                for value in ids:
                    source = historical_lineups.get(value)
                    if source and player_id in set().union(
                        *recent_starting_sets([source["payload"]], identity[f"{side}_team_id"])
                    ):
                        evidence.append(FieldProvenance(
                            "API-FOOTBALL", "/fixtures/lineups", source["retrieved_at"],
                            source.get("provider_timestamp"), str(fixture_id),
                            str(identity[f"{side}_team_id"]), player_id,
                        ))
                fields.append(IntelligenceField(
                    f"{side}.player_usage.{player_id}.recent_starts",
                    DataClass.LINEUP_SENSITIVE, usage[player_id], tuple(evidence),
                ))
        evidence_sources = [
            item for item in (
                *sources.values(), *detailed_stats.values(),
                *historical_lineups.values(),
            )
            if item is not None
        ]
        evidence_at = max(
            (item["retrieved_at"] for item in evidence_sources), default=now
        )
        evidence_at = max(now, evidence_at)
        self._normalize_odds(fields, sources.get("odds"), identity, evidence_at)
        fields.extend(derive_features(
            fields, current_starters=current_starters, recent_starting_sets=prior_sets,
            injured=injured, suspended=suspended,
        ))
        fields = sorted(fields, key=lambda item: item.name)
        missing = self._missing(fields)
        if not current_starters["home"] or not current_starters["away"]:
            blockers.append("CONFIRMED_LINEUPS_NOT_AVAILABLE")
        freshness = self._freshness(sources, fields, evidence_at)
        material = {
            "schema_version": SCHEMA_VERSION, "fixture_id": str(fixture_id),
            "kickoff_utc": kickoff.isoformat(), "evaluated_at": evidence_at.isoformat(),
            "fields": [asdict(item) for item in fields],
            "freshness": [asdict(item) for item in freshness],
            "missing_data": sorted(set(missing)), "blockers": sorted(set(blockers)),
            "api_calls": [asdict(item) for item in self.calls],
        }
        snapshot = self.repository.append_snapshot(material)
        used = self.provider.request_count - start_count
        return EnrichmentResult(snapshot, used, self.budget.maximum_api_calls,
                                sum(item.cache_status == "HIT" for item in self.calls),
                                sum(item.cache_status == "MISS" for item in self.calls))

    async def _fetch(self, endpoint: str, query: dict[str, object], ttl: timedelta,
                     operation: Callable[[], Awaitable[object]], *, now: datetime,
                     required: bool, force_refresh: bool = False) -> dict | None:
        cached = None if force_refresh else self.repository.cached(endpoint, query, now=now)
        query_text = "&".join(f"{key}={query[key]}" for key in sorted(query))
        if cached is not None:
            self.calls.append(ApiCallEvidence(endpoint, query_text, "HIT", 0, required, "AVAILABLE"))
            return cached
        if self._remaining() <= 0:
            self.calls.append(ApiCallEvidence(endpoint, query_text, "MISS", 0, required, "SKIPPED_BUDGET"))
            return None
        cache_status = "REFRESH" if force_refresh else "MISS"
        before = self.provider.request_count
        try:
            payload = await operation()
        except Exception as exc:
            used = self.provider.request_count - before
            self.calls.append(ApiCallEvidence(endpoint, query_text, cache_status, used, required,
                                              "FAILED_" + type(exc).__name__.upper()))
            return None
        used = self.provider.request_count - before
        observed = retrieved_at(self.provider, now)
        outcome = "PROVIDER_ERROR" if isinstance(payload, dict) and payload.get("errors") else "AVAILABLE"
        self.calls.append(ApiCallEvidence(endpoint, query_text, cache_status, used, required, outcome))
        if outcome == "PROVIDER_ERROR":
            return None
        provider_time = _provider_timestamp(payload) if endpoint == "/odds" else None
        effective_ttl = ttl
        if endpoint == "/fixtures/lineups":
            rows = payload.get("response") if isinstance(payload, dict) else None
            if not isinstance(rows, list) or not rows:
                effective_ttl = self.freshness.unavailable_lineup
        self.repository.append_cache(
            provider="API-FOOTBALL", endpoint=endpoint, query=query,
            retrieved_at=observed, expires_at=observed + effective_ttl,
            provider_timestamp=provider_time, payload=payload,
        )
        return {"payload": payload, "retrieved_at": observed,
                "expires_at": observed + effective_ttl, "provider_timestamp": provider_time}

    def _remaining(self) -> int:
        return max(0, self.budget.maximum_api_calls - self.provider.request_count)

    @staticmethod
    def _provenance(source: dict, fixture_id: str, endpoint: str) -> FieldProvenance:
        return FieldProvenance("API-FOOTBALL", endpoint, source["retrieved_at"],
                               source.get("provider_timestamp"), fixture_id)

    def _normalize_odds(self, fields, source, identity, now) -> None:
        if source is None:
            return
        try:
            contract = normalize_api_football_current_odds(
                source["payload"], fixture_id=identity["fixture_id"],
                kickoff_utc=identity["kickoff_utc"].isoformat(),
                retrieved_at_utc=source["retrieved_at"].isoformat(),
                source_selected_at_utc=source["retrieved_at"].isoformat(),
            )
            snapshot = parse_current_odds(contract, now=now)
        except CurrentOddsValidationError:
            return
        for quote in snapshot.quotes:
            p = FieldProvenance("API-FOOTBALL", "/odds", source["retrieved_at"],
                                quote.provider_origin_timestamp_utc, identity["fixture_id"])
            fields.extend((
                IntelligenceField(f"market.{quote.market}.decimal_odds", DataClass.PRE_MATCH_DYNAMIC, str(quote.decimal_odds), (p,)),
                IntelligenceField(f"market.{quote.market}.implied_probability", DataClass.PRE_MATCH_DYNAMIC,
                                  str(1 / quote.decimal_odds), (p,)),
                IntelligenceField(f"market.{quote.market}.bookmaker", DataClass.PRE_MATCH_DYNAMIC, snapshot.bookmaker_name, (p,)),
                IntelligenceField(f"feature.current_odds_{quote.market.lower()}", DataClass.PRE_MATCH_DYNAMIC,
                                  str(quote.decimal_odds), (p,)),
                IntelligenceField(f"feature.implied_market_probability_{quote.market.lower()}", DataClass.PRE_MATCH_DYNAMIC,
                                  str(1 / quote.decimal_odds), (p,)),
            ))

    def _freshness(
        self,
        sources: dict[str, dict | None],
        fields: list[IntelligenceField],
        now: datetime,
    ) -> tuple[FreshnessEvidence, ...]:
        by_name = {item.name: item for item in fields}
        groups = {
            "fixture_context": ((sources.get("fixture"),), self.freshness.fixture),
            "confirmed_lineups": ((sources.get("lineup"),), self.freshness.confirmed_lineup),
            "injuries": ((sources.get("injuries"),), self.freshness.injuries),
            "team_statistics": ((sources.get("home_stats"), sources.get("away_stats")), self.freshness.team_statistics),
            "team_history": ((sources.get("home_history"), sources.get("away_history")), self.freshness.team_history),
            "odds": ((sources.get("odds"),), self.freshness.odds),
        }
        result = []
        for name, (items, policy) in groups.items():
            present = [item for item in items if item]
            newest = max((item["retrieved_at"] for item in present), default=None)
            expires = min((item["expires_at"] for item in present), default=None)
            normalized = self._normalized_signal_available(name, by_name)
            status = FreshnessStatus.MISSING if len(present) != len(items) or not normalized else (
                FreshnessStatus.FRESH if expires and now <= expires else FreshnessStatus.STALE
            )
            result.append(FreshnessEvidence(name, status, now, newest, expires, int(policy.total_seconds())))
        return tuple(result)

    @staticmethod
    def _normalized_signal_available(
        signal: str, fields: dict[str, IntelligenceField]
    ) -> bool:
        if signal == "confirmed_lineups":
            return all(f"{side}.lineup.confirmed" in fields for side in ("home", "away"))
        if signal == "injuries":
            return all(f"{side}.availability.injury_count" in fields for side in ("home", "away"))
        if signal == "team_statistics":
            return all(f"{side}.season.matches_played" in fields for side in ("home", "away"))
        if signal == "team_history":
            return all(
                (item := fields.get(f"{side}.recent.match_count")) is not None
                and int(item.value) > 0
                for side in ("home", "away")
            )
        if signal == "odds":
            return any(
                name.startswith("market.") and name.endswith(".decimal_odds")
                for name in fields
            )
        if signal == "fixture_context":
            return all(
                name in fields
                for name in ("fixture.id", "fixture.kickoff_utc", "competition.id")
            )
        return False

    @staticmethod
    def _missing(fields: list[IntelligenceField]) -> list[str]:
        names = {item.name for item in fields}
        expected = (
            "home.lineup.confirmed", "away.lineup.confirmed",
            "feature.home_form_strength", "feature.away_form_strength",
            "feature.rest_days_home", "feature.rest_days_away",
            "feature.lineup_continuity_home", "feature.lineup_continuity_away",
            "home.recent_shots_per_match", "away.recent_shots_per_match",
            "home.recent_shots_on_target_per_match", "away.recent_shots_on_target_per_match",
            "home.recent_possession_per_match", "away.recent_possession_per_match",
            "home.recent_corners_per_match", "away.recent_corners_per_match",
            "home.recent_xg_per_match", "away.recent_xg_per_match",
            "fixture.weather", "fixture.travel_context",
        )
        return [name for name in expected if name not in names]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evaluated_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _provider_timestamp(payload: object) -> datetime | None:
    rows = payload.get("response") if isinstance(payload, dict) else None
    stamps = []
    for row in rows if isinstance(rows, list) else []:
        value = row.get("update") if isinstance(row, dict) else None
        if isinstance(value, str):
            try:
                stamps.append(datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc))
            except ValueError:
                pass
    return max(stamps, default=None)


async def enrich_discovery_result(
    discovery: dict,
    service: CurrentMatchIntelligenceService,
    *,
    evaluated_at: datetime,
) -> tuple[EnrichmentResult, ...]:
    """Enrich only the strongest already-ordered discovery survivors."""

    candidates = discovery.get("selected_fixtures")
    if not isinstance(candidates, list):
        selected = discovery.get("selected_fixture")
        candidates = [selected] if isinstance(selected, dict) else []
    results = []
    for candidate in candidates[: service.budget.maximum_enriched_fixtures]:
        fixture_id = candidate.get("provider_fixture_id")
        if fixture_id is None:
            continue
        results.append(await service.collect(int(fixture_id), evaluated_at=evaluated_at))
    return tuple(results)
