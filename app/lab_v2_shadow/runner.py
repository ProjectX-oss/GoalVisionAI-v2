"""Adaptive broad-coverage current/upcoming Lab V2 selection cycle."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from itertools import combinations
from math import factorial
import json
from pathlib import Path
import re
import sqlite3

from app.current_match_intelligence.serialization import snapshot_from_document
from app.lab_combo.experimental import evaluate_snapshot
from app.real_match_lab_analysis.fingerprint import fingerprint

from .api_prediction import ApiPredictionSignal, normalize_api_prediction
from .bookmakers import CATALOGUE_CACHE_DAYS, catalogue_summary, review_bookmaker_catalogue
from .capability import CapabilityTier, LeagueCapability, LeagueCapabilityCache
from .context_signals import PlayerUsage, AvailabilityImpact, availability_impact, opponent_adjusted_form
from .ensemble import EnsembleDecision, EnsembleSignal, evaluate_ensemble
from .market_consensus import CurrentMarketConsensus, best_current_price, current_market_consensus
from .pi_ratings import MatchResult, PiAvailability, PiRatingAdapter, PiSignal, parse_api_fixture_results
from .quota import (
    DAILY_SAFETY_RESERVE,
    MAX_DISCOVERY_CALLS_PER_CYCLE,
    AdaptiveQuotaBudget,
    adaptive_quota_budget,
    projected_daily_usage,
)
from .repository import ShadowEvidenceRepository


SCHEMA_VERSION = "goalvision-lab-v2-broad-coverage-cycle-v3"
READINESS_POLICY_VERSION = "LAB_V2_FINAL_REVIEW_READINESS_V2"
MAXIMUM_CALLS = MAX_DISCOVERY_CALLS_PER_CYCLE
FINAL_REVIEW_WINDOW = timedelta(minutes=75)
FINAL_REVIEW_MAX_AGE = timedelta(minutes=5)
MINIMUM_KICKOFF_LEAD = timedelta(minutes=10)
FINAL_REVIEW_SHORTLIST_SIZE = 5
MAX_FINAL_REVIEW_CALLS_PER_FIXTURE = 4
LINEUP_SENSITIVE_MARKETS = frozenset({"HOME_WIN", "DRAW", "AWAY_WIN"})
EXCLUDED = re.compile(
    r"(?i)(\byouth\b|\bu[- ]?\d{2}\b|\breserves?\b|\bacademy\b|"
    r"\bvirtual\b|\besports?\b|\bfriendly\b)"
)
TIER_ORDER = {
    CapabilityTier.TIER_A_FULL: 0,
    CapabilityTier.TIER_B_GOOD: 1,
    CapabilityTier.TIER_C_BASIC: 2,
}


class LabV2ShadowRunner:
    """Run V2 deterministically; publication is a separate explicit boundary."""

    def __init__(
        self,
        client: object,
        repository: ShadowEvidenceRepository,
        *,
        capability_cache_path: Path,
        analysis_path: Path | None = None,
        maximum_calls: int = MAXIMUM_CALLS,
        daily_safety_reserve: int = DAILY_SAFETY_RESERVE,
    ) -> None:
        if not 1 <= maximum_calls <= MAXIMUM_CALLS:
            raise ValueError("LAB_V2_MAXIMUM_CALLS_MUST_BE_BETWEEN_1_AND_100")
        if daily_safety_reserve < DAILY_SAFETY_RESERVE:
            raise ValueError("LAB_V2_DAILY_SAFETY_RESERVE_CANNOT_BE_LOWERED")
        self.client = client
        self.repository = repository
        self.capability_cache_path = capability_cache_path
        self.analysis_path = analysis_path
        self.maximum_calls = maximum_calls
        self.daily_safety_reserve = daily_safety_reserve
        self.calls: list[dict[str, object]] = []
        self.quota_budget: AdaptiveQuotaBudget | None = None
        restrict = getattr(client, "restrict_requests", None)
        if restrict:
            restrict(maximum_calls, daily_reserve=daily_safety_reserve)

    async def run(
        self,
        *,
        now: datetime,
        horizon_days: int = 3,
        publication_requested: bool = False,
    ) -> dict[str, object]:
        """Produce and persist analysis evidence without crossing the send boundary.

        ``publication_requested`` records the controlling CLI intent only.  This
        runner never constructs Telegram transport or mutates the publication
        ledger; the outer controlled-cycle command owns that handoff.
        """
        clock = _utc(now)
        if not 1 <= horizon_days <= 7:
            raise ValueError("LAB_V2_HORIZON_OUTSIDE_1_TO_7_DAYS")

        await self._fetch(
            "/status", {}, lambda: self.client.account_status(),
            clock=clock, ttl=None, use_cache=False,
        )
        quota = getattr(self.client, "quota_snapshot", lambda: {})()
        self.quota_budget = adaptive_quota_budget(
            quota, requested_maximum=self.maximum_calls,
            already_consumed=self._request_count(),
            daily_safety_reserve=self.daily_safety_reserve,
        )
        if self.quota_budget.additional_calls_available == 0 and not hasattr(self.client, "quota_snapshot"):
            self.quota_budget = AdaptiveQuotaBudget(
                self.maximum_calls, self.maximum_calls, self._request_count(),
                self.maximum_calls - self._request_count(), None, None,
                self.daily_safety_reserve, None, "TEST_DOUBLE_EXPLICIT_LIMIT",
            )

        capabilities, capability_cache_status = await self._capabilities(clock)
        bookmaker_catalogue, bookmaker_cache_status = await self._bookmakers(clock)
        self.allowed_bookmaker_ids = frozenset(
            item.bookmaker_id for item in bookmaker_catalogue
            if item.relevance != "OTHER_CURRENT_PROVIDER_SOURCE"
        )

        fixtures: dict[int, dict[str, object]] = {}
        fixture_rows_seen = 0
        days: list[str] = []
        for offset in range(horizon_days):
            if self._remaining() <= 0:
                break
            day = (clock.date() + timedelta(days=offset)).isoformat()
            days.append(day)
            payload, _ = await self._fetch(
                "/fixtures", {"date": day, "timezone": "UTC"},
                lambda value=day: self.client.fixtures_by_date(value, timezone_name="UTC"),
                clock=clock, ttl=timedelta(minutes=5), use_cache=True,
            )
            fixture_rows_seen += _result_count(payload)
            for item in _fixture_rows(payload, capabilities, clock):
                fixtures[int(item["fixture_id"])] = item
        ordered = sorted(fixtures.values(), key=lambda item: (
            item["kickoff_utc"], TIER_ORDER[item["capability_tier"]], item["fixture_id"],
        ))

        odds_evidence, odds_page_report = await self._date_odds(
            days, {int(item["fixture_id"]) for item in ordered}, clock,
        )
        odds_fixtures = [
            item for item in ordered
            if item["fixture_id"] in odds_evidence
            and any(value.status == "AVAILABLE" for value in odds_evidence[item["fixture_id"]][2].values())
        ]

        final_review_reserve = _final_review_call_reserve(odds_fixtures, clock)
        histories, adapters, history_budget_skips = await self._histories(
            odds_fixtures, clock, reserve_calls=final_review_reserve,
        )
        api_predictions, prediction_budget_skips = await self._predictions(
            odds_fixtures, clock, reserve_calls=final_review_reserve,
        )
        persisted_models, v1_keys, persisted_usage = self._persisted_v1(odds_fixtures, clock)

        preliminary = self._evaluate(
            odds_fixtures, odds_evidence, histories, adapters, api_predictions,
            persisted_models, {}, {}, clock,
        )
        shortlist_ids = _shortlist(preliminary, maximum=FINAL_REVIEW_SHORTLIST_SIZE)
        availability: dict[int, dict[str, AvailabilityImpact]] = {}
        final_reviews: dict[int, dict[str, object]] = {}
        cmi_enriched: set[int] = set()
        for fixture_id in shortlist_ids:
            fixture = fixtures[fixture_id]
            capability: LeagueCapability = fixture["capability"]
            near = timedelta(0) < fixture["kickoff_utc"] - clock <= FINAL_REVIEW_WINDOW
            context: dict[str, object] = {
                "near_kickoff": near,
                "fixture_refreshed": False,
                "odds_refreshed": False,
                "lineup_status": "NOT_REQUESTED",
                "injuries_status": "NOT_REQUESTED",
                "reviewed_at_utc": None,
            }
            if capability.injuries and self._remaining() > (3 if near else 0):
                payload, _ = await self._fetch(
                    "/injuries", {"fixture": fixture_id},
                    lambda identity=fixture_id: self._provider("injuries", identity, "/injuries"),
                    clock=clock, ttl=timedelta(hours=4), use_cache=not near,
                )
                availability[fixture_id] = _availability_from_payload(
                    payload, fixture, usage=persisted_usage.get(fixture_id, {}),
                )
                context["injuries_status"] = "REFRESHED" if near else "AVAILABLE"
                cmi_enriched.add(fixture_id)
            elif not capability.injuries:
                context["injuries_status"] = "NOT_SUPPORTED"

            if near and self._remaining() >= 2 + int(capability.lineups):
                fixture_payload, _ = await self._fetch(
                    "/fixtures", {"id": fixture_id},
                    lambda identity=fixture_id: self.client.fixture(identity),
                    clock=clock, ttl=timedelta(minutes=2), use_cache=False,
                )
                context["fixture_refreshed"] = _fixture_still_upcoming(fixture_payload, fixture_id, clock)
                odds_payload, retrieved = await self._fetch(
                    "/odds", {"fixture": fixture_id},
                    lambda identity=fixture_id: self.client.current_odds(identity),
                    clock=clock, ttl=timedelta(minutes=5), use_cache=False,
                )
                exact_consensus = current_market_consensus(
                    odds_payload, fixture_id=fixture_id, retrieved_at=retrieved,
                    now=max(clock, retrieved),
                    allowed_bookmaker_ids=self.allowed_bookmaker_ids,
                )
                if any(value.status == "AVAILABLE" for value in exact_consensus.values()):
                    odds_evidence[fixture_id] = (odds_payload, retrieved, exact_consensus)
                    context["odds_refreshed"] = True
                if capability.lineups:
                    lineup_payload, _ = await self._fetch(
                        "/fixtures/lineups", {"fixture": fixture_id},
                        lambda identity=fixture_id: self._provider("lineup", identity, "/fixtures/lineups"),
                        clock=clock, ttl=timedelta(minutes=5), use_cache=False,
                    )
                    context["lineup_status"] = (
                        "CONFIRMED" if _confirmed_lineups(lineup_payload, fixture) else "NOT_YET_PUBLISHED"
                    )
                else:
                    context["lineup_status"] = "NOT_SUPPORTED"
                context["reviewed_at_utc"] = _metadata_time(
                    getattr(self.client, "response_metadata", lambda: {})(), clock
                ).isoformat()
                cmi_enriched.add(fixture_id)
            final_reviews[fixture_id] = context

        candidates = self._evaluate(
            odds_fixtures, odds_evidence, histories, adapters, api_predictions,
            persisted_models, availability, final_reviews, clock,
        )
        approved = [item for item in candidates if item["decision"] == "APPROVED"]
        v2_keys = {f"{item['fixture_id']}:{item['market']}" for item in approved}
        ready = [item for item in approved if item["stage"] == "READY_TO_PUBLISH"]
        early = [item for item in approved if item["stage"] == "EARLY_CANDIDATE"]
        final = [item for item in approved if item["stage"] == "FINAL_REVIEW_REQUIRED"]
        combos = _combos(ready)
        pi_states = _counts(
            (adapters[item["league_id"]].signal(item["home_team_id"], item["away_team_id"]).state.value
             if item["league_id"] in adapters else PiAvailability.UNAVAILABLE.value)
            for item in odds_fixtures
        )
        endpoint_calls = _counts(
            str(item["endpoint"]) for item in self.calls
            for _ in range(int(item["actual_calls"]))
        )
        current_quota = getattr(self.client, "quota_snapshot", lambda: {})()
        remaining_daily = current_quota.get("daily_remaining")
        reserve_remaining = (
            int(remaining_daily) - self.daily_safety_reserve
            if type(remaining_daily) is int else None
        )
        budget_skips = (
            odds_page_report["fixtures_not_analyzed_due_to_budget"]
            + history_budget_skips + prediction_budget_skips
        )
        rejection_reasons = _counts(
            reason for item in candidates for reason in item["rejection_reasons"]
        )
        report = {
            "schema_version": SCHEMA_VERSION,
            "mode": "LAB_V2_NO_SEND",
            "analysis_mode": "LAB_V2_NO_SEND",
            "publication_requested": bool(publication_requested),
            "publication_enabled": bool(publication_requested),
            "publication_attempt_count": 0,
            "evaluated_at_utc": clock.isoformat(),
            "fixtures_discovered": len(fixtures),
            "provider_fixture_rows": fixture_rows_seen,
            "number_of_leagues": len({item["league_id"] for item in ordered}),
            "league_distribution": _counts(f"{item['league_id']}:{item['league_name']}" for item in ordered),
            "capability_cache": capability_cache_status,
            "capability_tier_distribution": _counts(item["capability_tier"].value for item in ordered),
            "fixtures_excluded_before_odds": max(0, fixture_rows_seen - len(fixtures)),
            "fixtures_with_no_current_odds": odds_page_report["fixtures_with_no_current_odds"],
            "fixtures_rejected_for_stale_current_odds": odds_page_report[
                "fixtures_rejected_for_stale_current_odds"
            ],
            "fixtures_with_unreliable_market_normalization": odds_page_report[
                "fixtures_with_unreliable_market_normalization"
            ],
            "current_odds_fixtures": len(odds_fixtures),
            "number_of_bookmakers_in_current_quotes": len({
                quote.bookmaker_name for _, _, families in odds_evidence.values()
                for family in families.values() for quote in family.quotes
            }),
            "bookmaker_catalogue_cache": bookmaker_cache_status,
            "bookmaker_catalogue": catalogue_summary(bookmaker_catalogue),
            "odds_pagination": odds_page_report,
            "pi_state_distribution": pi_states,
            "pi_available_fixtures": pi_states.get("AVAILABLE", 0),
            "pi_low_sample_fixtures": pi_states.get("LOW_SAMPLE", 0),
            "pi_insufficient_fixtures": pi_states.get("INSUFFICIENT", 0),
            "pi_unavailable_fixtures": pi_states.get("UNAVAILABLE", 0),
            "api_prediction_available_fixtures": sum(item.available for item in api_predictions.values()),
            "market_consensus_available_fixtures": sum(
                any(value.status == "AVAILABLE" for value in data[2].values())
                for data in odds_evidence.values()
            ),
            "cmi_enrichment_count": len(cmi_enriched),
            "candidate_markets_evaluated": len(candidates),
            "v1_candidate_count": len(v1_keys),
            "v2_candidate_count": len(v2_keys),
            "overlap": sorted(v1_keys & v2_keys),
            "new_v2_candidates": sorted(v2_keys - v1_keys),
            "v1_candidates_rejected_by_v2": sorted(v1_keys - v2_keys),
            "candidate_markets": candidates,
            "rejection_reasons": rejection_reasons,
            "readiness_policy": READINESS_POLICY_VERSION,
            "lineup_sensitive_markets": sorted(LINEUP_SENSITIVE_MARKETS),
            "final_review_call_reserve": final_review_reserve,
            "early_candidate_count": len(early),
            "final_review_candidate_count": len(final),
            "ready_candidate_count": len(ready),
            "three_leg_combos": combos,
            "api_calls_consumed": self._request_count(),
            "api_call_allocation": endpoint_calls,
            "adaptive_quota_budget": self.quota_budget.document(),
            "api_call_ceiling": self.maximum_calls,
            "current_remaining_daily_quota": remaining_daily,
            "daily_safety_reserve": self.daily_safety_reserve,
            "reserve_headroom_remaining": reserve_remaining,
            "fixtures_not_analyzed_due_to_quota": budget_skips,
            "projected_worst_case_daily_usage": projected_daily_usage(maximum_per_cycle=self.maximum_calls),
            "call_efficiency": {
                "v2_current_odds_fixtures_per_call": (
                    str(Decimal(len(odds_fixtures)) / Decimal(self._request_count()))
                    if self._request_count() else None
                ),
                "v1_observed_current_odds_fixtures_per_call": "0.2006335797254487856388595565",
            },
            "historical_bookmaker_odds_used": False,
            "telegram_sends": 0,
            "telegram_transport_constructed": False,
            "official_mutations": 0,
            "timers_started": 0,
        }
        identity = "lab-v2-cycle-" + fingerprint((clock, report["fixtures_discovered"], report["api_calls_consumed"]))
        for fixture_id, (_, retrieved, families) in sorted(odds_evidence.items()):
            for family, consensus in sorted(families.items()):
                document = _plain(asdict(consensus))
                document.update({
                    "retrieved_at_utc": retrieved.isoformat(),
                    "source": "API_FOOTBALL_CURRENT_ODDS",
                    "historical_bookmaker_odds_used": False,
                })
                self.repository.append(
                    "market_consensus", f"{fixture_id}:{family}:{fingerprint(document)}",
                    document, created_at=clock,
                )
        for candidate in candidates:
            self.repository.append("candidate", candidate["candidate_id"], candidate, created_at=clock)
        self.repository.append("rehearsal", identity, report, created_at=clock)
        return _plain(report)

    async def _date_odds(
        self, days: list[str], fixture_ids: set[int], clock: datetime,
    ) -> tuple[dict[int, tuple[object, datetime, dict[str, CurrentMarketConsensus]]], dict[str, object]]:
        result: dict[int, tuple[object, datetime, dict[str, CurrentMarketConsensus]]] = {}
        pages: list[tuple[str, int]] = [(day, 1) for day in days]
        fetched: list[dict[str, object]] = []
        joined_fixture_ids: set[int] = set()
        stale_fixture_ids: set[int] = set()
        unreliable_fixture_ids: set[int] = set()
        page_budget = max(0, int(self._effective_maximum() * 0.58) - self._request_count())
        used = 0
        while pages and self._remaining() > 0 and used < page_budget:
            day, page = pages.pop(0)
            payload, retrieved = await self._fetch(
                "/odds(date)", {"date": day, "page": page},
                lambda value=day, number=page: self._provider_odds_date(value, number),
                clock=clock, ttl=timedelta(minutes=15), use_cache=True,
            )
            used += int(self.calls[-1]["actual_calls"])
            paging = payload.get("paging") if isinstance(payload, dict) and isinstance(payload.get("paging"), dict) else {}
            current = _safe_int(paging.get("current"), page)
            total = _safe_int(paging.get("total"), current)
            fetched.append({"date": day, "page": current, "total_pages": total, "rows": _result_count(payload)})
            for row in _response_rows(payload):
                fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
                fixture_id = _safe_int(fixture.get("id"), -1)
                if fixture_id not in fixture_ids:
                    continue
                joined_fixture_ids.add(fixture_id)
                single_payload = {"results": 1, "response": [row]}
                consensus = current_market_consensus(
                    single_payload, fixture_id=fixture_id,
                    retrieved_at=retrieved, now=max(clock, retrieved),
                    allowed_bookmaker_ids=self.allowed_bookmaker_ids,
                )
                if any(value.status == "AVAILABLE" for value in consensus.values()):
                    result[fixture_id] = (single_payload, retrieved, consensus)
                elif consensus and all(value.status == "STALE_CURRENT_ODDS" for value in consensus.values()):
                    stale_fixture_ids.add(fixture_id)
                else:
                    unreliable_fixture_ids.add(fixture_id)
            if current < total:
                pages.append((day, current + 1))
        unvisited_pages = len(pages)
        return result, {
            "pages_fetched": fetched,
            "page_calls": used,
            "pages_not_fetched_due_to_budget": unvisited_pages,
            "fixtures_not_analyzed_due_to_budget": unvisited_pages * 10,
            "fixtures_with_no_current_odds": len(fixture_ids - joined_fixture_ids),
            "fixtures_rejected_for_stale_current_odds": len(stale_fixture_ids - result.keys()),
            "fixtures_with_unreliable_market_normalization": len(
                unreliable_fixture_ids - result.keys() - stale_fixture_ids
            ),
            "batching": "CURRENT_/odds?date=YYYY-MM-DD&page=N",
        }

    async def _histories(
        self, fixtures: list[dict[str, object]], clock: datetime, *, reserve_calls: int = 0,
    ) -> tuple[dict[int, tuple[MatchResult, ...]], dict[int, PiRatingAdapter], int]:
        histories: dict[int, tuple[MatchResult, ...]] = {}
        adapters: dict[int, PiRatingAdapter] = {}
        skipped = 0
        grouped: dict[int, list[dict[str, object]]] = {}
        for fixture in fixtures:
            grouped.setdefault(int(fixture["league_id"]), []).append(fixture)
        for league_id, targets in sorted(grouped.items(), key=lambda item: min(x["kickoff_utc"] for x in item[1])):
            if self._remaining() <= max(12, reserve_calls):
                skipped += len(targets)
                continue
            season = int(targets[0]["season"])
            payload, _ = await self._fetch(
                "/fixtures(results)", {"league": league_id, "season": season, "status": "FT", "last": 99},
                lambda lid=league_id, value=season: self.client.finished_matches(lid, value, last=99),
                clock=clock, ttl=timedelta(hours=6), use_cache=True,
            )
            matches = list(parse_api_fixture_results((payload,)))
            adapter = PiRatingAdapter(league_id)
            adapter.replay(matches, before=clock)
            needs_previous = any(
                adapter.signal(int(item["home_team_id"]), int(item["away_team_id"])).state
                in {PiAvailability.INSUFFICIENT, PiAvailability.UNAVAILABLE}
                for item in targets
            )
            if needs_previous and season > 1 and self._remaining() > max(16, reserve_calls):
                previous, _ = await self._fetch(
                    "/fixtures(results)", {"league": league_id, "season": season - 1, "status": "FT", "last": 99},
                    lambda lid=league_id, value=season - 1: self.client.finished_matches(lid, value, last=99),
                    clock=clock, ttl=timedelta(days=1), use_cache=True,
                )
                matches = list(parse_api_fixture_results((previous, payload)))
                adapter = PiRatingAdapter(league_id)
                adapter.replay(matches, before=clock)
            histories[league_id] = tuple(matches)
            adapters[league_id] = adapter
        return histories, adapters, skipped

    async def _predictions(
        self, fixtures: list[dict[str, object]], clock: datetime, *, reserve_calls: int = 0,
    ) -> tuple[dict[int, ApiPredictionSignal], int]:
        result: dict[int, ApiPredictionSignal] = {}
        skipped = 0
        for fixture in fixtures:
            capability: LeagueCapability = fixture["capability"]
            if not capability.predictions:
                continue
            if self._remaining() <= max(8, reserve_calls):
                skipped += 1
                continue
            fixture_id = int(fixture["fixture_id"])
            payload, _ = await self._fetch(
                "/predictions", {"fixture": fixture_id},
                lambda identity=fixture_id: self._provider("prediction", identity, "/predictions"),
                clock=clock, ttl=timedelta(hours=1), use_cache=True,
            )
            result[fixture_id] = normalize_api_prediction(payload, fixture_id=fixture_id)
        return result, skipped

    async def _capabilities(self, clock: datetime) -> tuple[LeagueCapabilityCache, str]:
        cache = LeagueCapabilityCache.load(self.capability_cache_path, now=clock)
        if cache is not None:
            return cache, "HIT"
        payload, retrieved = await self._fetch(
            "/leagues", {"current": "true"}, lambda: self.client.leagues(current=True),
            clock=clock, ttl=None,
        )
        cache = LeagueCapabilityCache.from_api_payload(payload, retrieved_at=retrieved)
        cache.save(self.capability_cache_path)
        return cache, "REFRESHED"

    async def _bookmakers(self, clock: datetime):
        query: dict[str, object] = {}
        cached = self.repository.cached("/odds/bookmakers", query, now=clock)
        if cached is not None:
            self.calls.append({"endpoint": "/odds/bookmakers", "query": query, "cache": "HIT", "actual_calls": 0,
                               "result_count": _result_count(cached["payload"])})
            return review_bookmaker_catalogue(cached["payload"]), "HIT"
        if self._remaining() <= 0:
            return (), "SKIPPED_BUDGET"
        payload, _ = await self._fetch(
            "/odds/bookmakers", query,
            lambda: self._provider_no_arg("odds_bookmakers", "/odds/bookmakers"),
            clock=clock, ttl=timedelta(days=CATALOGUE_CACHE_DAYS), use_cache=False,
        )
        return review_bookmaker_catalogue(payload), "REFRESHED"

    async def _fetch(
        self, endpoint: str, query: dict[str, object], operation, *,
        clock: datetime, ttl: timedelta | None, use_cache: bool = True,
    ) -> tuple[object, datetime]:
        if ttl is not None and use_cache:
            cached = self.repository.cached(endpoint, query, now=clock)
            if cached is not None:
                self.calls.append({"endpoint": endpoint, "query": query, "cache": "HIT", "actual_calls": 0,
                                   "result_count": _result_count(cached["payload"])})
                return cached["payload"], cached["retrieved_at"]
        if self._remaining() <= 0:
            raise ValueError("LAB_V2_API_CALL_BUDGET_EXHAUSTED")
        before = self._request_count()
        payload = await operation()
        actual = self._request_count() - before
        metadata = getattr(self.client, "response_metadata", lambda: {})()
        retrieved = _metadata_time(metadata, clock)
        self.calls.append({"endpoint": endpoint, "query": query, "cache": "MISS", "actual_calls": actual,
                           "result_count": _result_count(payload)})
        if ttl is not None and not (isinstance(payload, dict) and payload.get("errors")):
            self.repository.append_cache(endpoint, query, payload, retrieved_at=retrieved, ttl=ttl)
        return payload, retrieved

    async def _provider_odds_date(self, day: str, page: int) -> object:
        method = getattr(self.client, "current_odds_by_date", None)
        if method is not None:
            return await method(day, page=page)
        return await self._raw("/odds", {"date": day, "page": page})

    async def _provider(self, name: str, fixture_id: int, endpoint: str) -> object:
        method = getattr(self.client, name, None)
        if method is not None:
            return await method(fixture_id)
        return await self._raw(endpoint, {"fixture": fixture_id})

    async def _provider_no_arg(self, name: str, endpoint: str) -> object:
        method = getattr(self.client, name, None)
        if method is not None:
            return await method()
        return await self._raw(endpoint, {})

    async def _raw(self, endpoint: str, query: dict[str, object]) -> object:
        getter = getattr(self.client, "_get", None)
        if getter is None:
            raise RuntimeError("LAB_V2_PROVIDER_ENDPOINT_UNAVAILABLE")
        response = await getter(endpoint, params=query)
        return response.json()

    def _request_count(self) -> int:
        return int(getattr(self.client, "request_count", 0))

    def _effective_maximum(self) -> int:
        return self.quota_budget.effective_cycle_maximum if self.quota_budget else self.maximum_calls

    def _remaining(self) -> int:
        return max(0, self._effective_maximum() - self._request_count())

    def _persisted_v1(
        self, fixtures: list[dict], now: datetime,
    ) -> tuple[dict[int, dict[str, Decimal]], set[str], dict[int, dict[str, dict[str, PlayerUsage]]]]:
        if self.analysis_path is None or not self.analysis_path.is_file():
            return {}, set(), {}
        connection = sqlite3.connect(self.analysis_path.resolve().as_uri() + "?mode=ro", uri=True)
        models: dict[int, dict[str, Decimal]] = {}
        keys: set[str] = set()
        usage: dict[int, dict[str, dict[str, PlayerUsage]]] = {}
        try:
            for fixture in fixtures:
                row = connection.execute(
                    """SELECT snapshot_json FROM current_match_intelligence_snapshots
                    WHERE fixture_id=? AND evaluated_at<=? ORDER BY snapshot_version DESC LIMIT 1""",
                    (str(fixture["fixture_id"]), now.isoformat()),
                ).fetchone()
                if row is None:
                    continue
                snapshot = snapshot_from_document(json.loads(row[0]))
                fields = {item.name: item.value for item in snapshot.fields}
                usage[int(fixture["fixture_id"])] = {
                    side: _player_usage(fields, side) for side in ("home", "away")
                }
                evaluated = evaluate_snapshot(snapshot, now=now)
                models[int(fixture["fixture_id"])] = {
                    item["market"]: Decimal(item["experimental_signal"])
                    for item in evaluated if item.get("experimental_signal") is not None
                }
                keys.update(
                    f"{item['fixture_id']}:{item['market']}"
                    for item in evaluated if item["decision"] == "APPROVED"
                )
        finally:
            connection.close()
        return models, keys, usage

    def _evaluate(
        self, fixtures, odds_evidence, histories, adapters, api_predictions,
        persisted_models, availability, final_reviews, now,
    ) -> list[dict[str, object]]:
        values: list[dict[str, object]] = []
        for fixture in fixtures:
            fixture_id, league_id = int(fixture["fixture_id"]), int(fixture["league_id"])
            adapter = adapters.get(league_id)
            matches = histories.get(league_id, ())
            pi = adapter.signal(fixture["home_team_id"], fixture["away_team_id"]) if adapter else _missing_pi(fixture)
            home_form = opponent_adjusted_form(fixture["home_team_id"], matches, adapter) if adapter else None
            away_form = opponent_adjusted_form(fixture["away_team_id"], matches, adapter) if adapter else None
            impacts = availability.get(fixture_id, {})
            cmi = _history_market_probabilities(fixture, matches, home_form, away_form, impacts)
            api = api_predictions.get(fixture_id)
            _, _, consensus_by_family = odds_evidence[fixture_id]
            review = final_reviews.get(fixture_id, {})
            for consensus in consensus_by_family.values():
                if consensus.status != "AVAILABLE":
                    continue
                for market, consensus_probability in consensus.fair_probabilities.items():
                    price = best_current_price(consensus, market)
                    if price is None:
                        continue
                    signals = [EnsembleSignal(
                        "CURRENT_MARKET_CONSENSUS", market, consensus_probability,
                        max(consensus.fair_probabilities, key=consensus.fair_probabilities.get),
                        Decimal("0.90"), "AVAILABLE", "CURRENT_API_FOOTBALL_QUOTES_ONLY",
                    )]
                    model_probability = persisted_models.get(fixture_id, {}).get(market)
                    if model_probability is not None:
                        signals.append(EnsembleSignal(
                            "GOALVISION_EXPERIMENTAL_MODEL", market, model_probability,
                            None, Decimal("1.00"), "AVAILABLE", "PERSISTED_CMI_SNAPSHOT",
                        ))
                    if market in pi.probabilities:
                        signals.append(EnsembleSignal(
                            "PI_RATINGS", market, pi.probabilities[market],
                            max(pi.probabilities, key=pi.probabilities.get),
                            Decimal("0.90") if pi.state == PiAvailability.AVAILABLE else Decimal("0.50"),
                            pi.state.value, "SAME_LEAGUE_MATCH_RESULTS_AND_GOALS_ONLY",
                        ))
                    if api and market in api.probabilities:
                        signals.append(EnsembleSignal(
                            "API_FOOTBALL_PREDICTION", market, api.probabilities[market],
                            max(api.probabilities, key=api.probabilities.get), Decimal("0.75"),
                            "AVAILABLE", "CURRENT_/PREDICTIONS",
                        ))
                    if market in cmi:
                        signals.append(EnsembleSignal(
                            "CURRENT_MATCH_INTELLIGENCE", market, cmi[market], max(cmi, key=cmi.get),
                            Decimal("0.80"), "AVAILABLE", "RESULT_HISTORY_FORM_AVAILABILITY",
                        ))
                    veto = _availability_veto(market, impacts)
                    decision = evaluate_ensemble(
                        market, price.decimal_odds, signals,
                        severe_current_match_contradiction=veto,
                    )
                    stage, readiness_reasons = _readiness(decision, fixture, now, review)
                    material = {
                        "policy": decision.policy, "fixture_id": fixture_id,
                        "readiness_policy": READINESS_POLICY_VERSION,
                        "league_id": league_id, "league": fixture["league_name"],
                        "capability_tier": fixture["capability_tier"].value,
                        "home_team_id": fixture["home_team_id"], "away_team_id": fixture["away_team_id"],
                        "home_team": fixture["home_team"], "away_team": fixture["away_team"],
                        "kickoff_utc": fixture["kickoff_utc"].isoformat(), "market": market,
                        "offered_odds": str(price.decimal_odds), "captured_odds": str(price.decimal_odds),
                        "bookmaker": price.bookmaker_name, "bookmaker_id": price.bookmaker_id,
                        "provider_type": "API_FOOTBALL_CURRENT_ODDS",
                        "provider_origin_timestamp_utc": price.provider_origin_timestamp_utc.isoformat(),
                        "goalvision_retrieved_at_utc": price.retrieved_at_utc.isoformat(),
                        "quote_provenance_fingerprint": price.provenance_fingerprint,
                        "decision": decision.decision, "confidence": decision.confidence,
                        "experimental_confidence": decision.confidence,
                        "odds_band": _odds_band(price.decimal_odds),
                        "lineup_confirmed": review.get("lineup_status", "NOT_REVIEWED"),
                        "pi_available": pi.state.value, "pi_agreement": _relation(pi.probabilities, market),
                        "api_prediction_relation": _relation(api.probabilities if api else {}, market),
                        "market_consensus_relation": _relation(consensus.fair_probabilities, market),
                        "ensemble_decision_class": decision.decision,
                        "ensemble_probability": str(decision.ensemble_probability) if decision.ensemble_probability is not None else None,
                        "edge": str(decision.edge) if decision.edge is not None else None,
                        "market_context_edge": str(decision.edge) if decision.edge is not None else None,
                        "weighted_agreement": str(decision.weighted_agreement) if decision.weighted_agreement is not None else None,
                        "stage": stage,
                        "readiness_reasons": list(readiness_reasons),
                        "final_review_completed_at_utc": review.get("reviewed_at_utc") if stage == "READY_TO_PUBLISH" else None,
                        "approval_reasons": list(decision.approval_reasons),
                        "rejection_reasons": list(decision.rejection_reasons),
                        "signals": [_plain(asdict(item)) for item in decision.signals],
                        "pi": _plain(asdict(pi)), "api_prediction_available": bool(api and api.available),
                        "market_consensus_bookmakers": consensus.bookmaker_count,
                        "market_consensus_dispersion": _plain(consensus.dispersion),
                        "availability_impact": _plain({key: asdict(value) for key, value in impacts.items()}),
                        "final_review": _plain(review), "historical_bookmaker_odds_used": False,
                    }
                    material["candidate_id"] = "lab-v2-candidate-" + fingerprint(material)
                    values.append(material)
        return sorted(values, key=lambda item: (item["fixture_id"], item["market"]))


def _fixture_rows(payload: object, capabilities: LeagueCapabilityCache, now: datetime) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in _response_rows(payload):
        fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
        league = row.get("league") if isinstance(row.get("league"), dict) else {}
        teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
        try:
            kickoff = _utc(datetime.fromisoformat(str(fixture["date"]).replace("Z", "+00:00")))
            league_id, season = int(league["id"]), int(league["season"])
            capability = capabilities.current(league_id, season, day=kickoff.date())
            identity = " ".join((str(league.get("name") or ""), str(home.get("name") or ""), str(away.get("name") or "")))
            if (status.get("short") not in {"NS", "TBD"} or kickoff <= now + MINIMUM_KICKOFF_LEAD
                    or capability is None or capability.tier == CapabilityTier.UNSUPPORTED or EXCLUDED.search(identity)):
                continue
            result.append({
                "fixture_id": int(fixture["id"]), "kickoff_utc": kickoff,
                "league_id": league_id, "league_name": str(league.get("name") or capability.competition_name),
                "season": season, "home_team_id": int(home["id"]), "away_team_id": int(away["id"]),
                "home_team": str(home.get("name") or home["id"]), "away_team": str(away.get("name") or away["id"]),
                "capability_tier": capability.tier, "capability": capability,
            })
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _history_market_probabilities(fixture, matches, home_form, away_form, impacts) -> dict[str, Decimal]:
    home_id, away_id = int(fixture["home_team_id"]), int(fixture["away_team_id"])
    home_rates = _team_goal_rates(home_id, matches, home_venue=True)
    away_rates = _team_goal_rates(away_id, matches, home_venue=False)
    if home_rates is None or away_rates is None:
        return {}
    home_rate = (home_rates[0] + away_rates[1]) / Decimal(2)
    away_rate = (away_rates[0] + home_rates[1]) / Decimal(2)
    if home_form and away_form and home_form.score is not None and away_form.score is not None:
        delta = home_form.score - away_form.score
        adjustment = max(Decimal("-0.15"), min(Decimal("0.15"), delta * Decimal("0.20")))
        home_rate *= Decimal(1) + adjustment
        away_rate *= Decimal(1) - adjustment
    home_rate *= Decimal(1) - impacts.get("home", _zero_impact()).impact * Decimal("0.25")
    away_rate *= Decimal(1) - impacts.get("away", _zero_impact()).impact * Decimal("0.25")
    return _poisson_markets(max(Decimal("0.15"), home_rate), max(Decimal("0.15"), away_rate))


def _team_goal_rates(team_id: int, matches: tuple[MatchResult, ...], *, home_venue: bool) -> tuple[Decimal, Decimal] | None:
    selected = []
    for match in sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id), reverse=True):
        is_home = match.home_team_id == team_id
        is_away = match.away_team_id == team_id
        if not (is_home or is_away) or (home_venue and not is_home) or (not home_venue and not is_away):
            continue
        selected.append((match.home_goals, match.away_goals) if is_home else (match.away_goals, match.home_goals))
        if len(selected) == 8:
            break
    if len(selected) < 3:
        return None
    weights = [Decimal(len(selected) - index) for index in range(len(selected))]
    total = sum(weights, Decimal(0))
    return (
        sum((Decimal(score[0]) * weight for score, weight in zip(selected, weights, strict=True)), Decimal(0)) / total,
        sum((Decimal(score[1]) * weight for score, weight in zip(selected, weights, strict=True)), Decimal(0)) / total,
    )


def _poisson_markets(home: Decimal, away: Decimal) -> dict[str, Decimal]:
    with localcontext() as context:
        context.prec = 28
        joint: list[tuple[int, int, Decimal]] = []
        mass = Decimal(0)
        for h in range(13):
            for a in range(13):
                value = _poisson(home, h) * _poisson(away, a)
                joint.append((h, a, value)); mass += value
        values = {
            "HOME_WIN": sum((p for h, a, p in joint if h > a), Decimal(0)) / mass,
            "DRAW": sum((p for h, a, p in joint if h == a), Decimal(0)) / mass,
            "AWAY_WIN": sum((p for h, a, p in joint if h < a), Decimal(0)) / mass,
            "BTTS_YES": sum((p for h, a, p in joint if h and a), Decimal(0)) / mass,
        }
        values["BTTS_NO"] = Decimal(1) - values["BTTS_YES"]
        for line in (1, 2, 3):
            over = sum((p for h, a, p in joint if h + a > line), Decimal(0)) / mass
            values[f"OVER_{line}_5"] = over; values[f"UNDER_{line}_5"] = Decimal(1) - over
        return values


def _poisson(rate: Decimal, goals: int) -> Decimal:
    return (-rate).exp() * (rate ** goals) / Decimal(factorial(goals))


def _stage(decision: EnsembleDecision, fixture: dict, now: datetime, review: dict[str, object]) -> str:
    """Return the public stage while `_readiness` retains auditable reasons."""
    return _readiness(decision, fixture, now, review)[0]


def _readiness(
    decision: EnsembleDecision,
    fixture: dict,
    now: datetime,
    review: dict[str, object],
) -> tuple[str, tuple[str, ...]]:
    if decision.decision != "APPROVED":
        return "REJECTED", ("ENSEMBLE_NOT_APPROVED",)
    remaining = fixture["kickoff_utc"] - now
    if remaining <= MINIMUM_KICKOFF_LEAD:
        return "REJECTED", ("MINIMUM_KICKOFF_LEAD_NOT_MET",)
    if remaining > FINAL_REVIEW_WINDOW:
        return "EARLY_CANDIDATE", ("FINAL_REVIEW_WINDOW_NOT_OPEN",)
    blockers: list[str] = []
    if not review.get("fixture_refreshed"):
        blockers.append("FIXTURE_REFRESH_REQUIRED")
    if not review.get("odds_refreshed"):
        blockers.append("CURRENT_ODDS_REFRESH_REQUIRED")
    if not _current_review_timestamp(review.get("reviewed_at_utc"), now, fixture["kickoff_utc"]):
        blockers.append("CURRENT_FINAL_REVIEW_TIMESTAMP_REQUIRED")
    capability: LeagueCapability = fixture["capability"]
    if decision.market in LINEUP_SENSITIVE_MARKETS:
        if capability.lineups and review.get("lineup_status") != "CONFIRMED":
            blockers.append("CONFIRMED_LINEUPS_REQUIRED_FOR_MARKET")
        if capability.injuries and review.get("injuries_status") != "REFRESHED":
            blockers.append("CURRENT_INJURIES_REQUIRED_FOR_MARKET")
    if capability.tier == CapabilityTier.TIER_C_BASIC and (
        decision.confidence not in {"MEDIUM", "HIGH"} or decision.available_signals < 3
        or (decision.weighted_agreement or Decimal(0)) < Decimal("0.75")
    ):
        blockers.append("TIER_C_READINESS_QUALITY_REQUIRED")
    return (
        ("FINAL_REVIEW_REQUIRED", tuple(blockers))
        if blockers else
        ("READY_TO_PUBLISH", ("FINAL_REVIEW_COMPLETE",))
    )


def _current_review_timestamp(value: object, now: datetime, kickoff: datetime) -> bool:
    if not isinstance(value, str):
        return False
    try:
        reviewed = _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return False
    return now - FINAL_REVIEW_MAX_AGE <= reviewed <= now + FINAL_REVIEW_MAX_AGE and reviewed < kickoff


def _final_review_call_reserve(fixtures: list[dict[str, object]], now: datetime) -> int:
    near_count = sum(
        MINIMUM_KICKOFF_LEAD < item["kickoff_utc"] - now <= FINAL_REVIEW_WINDOW
        for item in fixtures
    )
    return min(FINAL_REVIEW_SHORTLIST_SIZE, near_count) * MAX_FINAL_REVIEW_CALLS_PER_FIXTURE


def _shortlist(candidates: list[dict[str, object]], *, maximum: int) -> list[int]:
    ordered = sorted(candidates, key=lambda item: (
        item["decision"] != "APPROVED", item["stage"] != "FINAL_REVIEW_REQUIRED",
        item["kickoff_utc"], -Decimal(str(item.get("edge") or "-99")),
        item["fixture_id"], item["market"],
    ))
    result: list[int] = []
    for item in ordered:
        fixture_id = int(item["fixture_id"])
        if fixture_id not in result: result.append(fixture_id)
        if len(result) == maximum: break
    return result


def _combos(candidates: list[dict]) -> list[dict[str, object]]:
    values = []
    for group in combinations(sorted(candidates, key=lambda item: item["candidate_id"]), 3):
        if len({item["fixture_id"] for item in group}) != 3: continue
        teams = [item[key] for item in group for key in ("home_team_id", "away_team_id")]
        if len(set(teams)) != 6: continue
        combined = Decimal(1)
        for item in group: combined *= Decimal(item["offered_odds"])
        values.append({"legs": [item["candidate_id"] for item in group], "combined_odds": str(combined),
                       "correlation_review": "PASSED_DISTINCT_FIXTURES_AND_TEAMS"})
        if len(values) == 3: break
    return values


def _availability_from_payload(
    payload: object, fixture: dict, *, usage: dict[str, dict[str, PlayerUsage]] | None = None,
) -> dict[str, AvailabilityImpact]:
    grouped = {"home": [], "away": []}
    sides = {str(fixture["home_team_id"]): "home", str(fixture["away_team_id"]): "away"}
    for row in _response_rows(payload):
        team, player = row.get("team") or {}, row.get("player") or {}
        side = sides.get(str(team.get("id")))
        if side and player.get("id") is not None:
            reason = str(player.get("reason") or "")
            suspended = any(word in reason.casefold() for word in ("suspend", "red card", "yellow cards"))
            grouped[side].append({"player_id": str(player["id"]), "status": "SUSPENDED" if suspended else "INJURED"})
    usage = usage or {}
    return {side: availability_impact(rows, usage.get(side)) for side, rows in grouped.items()}


def _player_usage(fields: dict[str, object], side: str) -> dict[str, PlayerUsage]:
    result: dict[str, PlayerUsage] = {}
    prefix = f"{side}.player_usage."
    for name, value in fields.items():
        if not name.startswith(prefix) or not name.endswith(".recent_starts"):
            continue
        player_id = name[len(prefix):].split(".", 1)[0]
        try:
            starts = int(value)
        except (TypeError, ValueError):
            continue
        result[player_id] = PlayerUsage(
            player_id=player_id, starts=starts,
            recent_start_frequency=min(Decimal(1), Decimal(starts) / Decimal(3)),
        )
    return result


def _confirmed_lineups(payload: object, fixture: dict) -> bool:
    team_ids = {str(fixture["home_team_id"]), str(fixture["away_team_id"])}
    confirmed: set[str] = set()
    for row in _response_rows(payload):
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        starters = row.get("startXI") if isinstance(row.get("startXI"), list) else []
        if str(team.get("id")) in team_ids and str(row.get("formation") or "").strip() and len(starters) == 11:
            confirmed.add(str(team.get("id")))
    return confirmed == team_ids


def _fixture_still_upcoming(payload: object, fixture_id: int, now: datetime) -> bool:
    rows = _response_rows(payload)
    if len(rows) != 1: return False
    fixture = rows[0].get("fixture") if isinstance(rows[0].get("fixture"), dict) else {}
    status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
    try:
        kickoff = _utc(datetime.fromisoformat(str(fixture["date"]).replace("Z", "+00:00")))
        return int(fixture["id"]) == fixture_id and status.get("short") in {"NS", "TBD"} and kickoff > now
    except (KeyError, TypeError, ValueError):
        return False


def _availability_veto(market: str, impacts: dict[str, AvailabilityImpact]) -> bool:
    home = impacts.get("home", _zero_impact()).impact; away = impacts.get("away", _zero_impact()).impact
    return (market == "HOME_WIN" and home - away >= Decimal("0.18")) or (market == "AWAY_WIN" and away - home >= Decimal("0.18"))


def _zero_impact() -> AvailabilityImpact:
    return AvailabilityImpact("COUNT_FALLBACK", 0, 0, 0, Decimal(0), (), "")


def _missing_pi(fixture: dict) -> PiSignal:
    return PiSignal(PiAvailability.UNAVAILABLE, fixture["league_id"], fixture["home_team_id"], fixture["away_team_id"],
                    None, None, None, None, None, None, None, None, 0, 0, 0, 0, {})


def _relation(probabilities: dict[str, Decimal], market: str) -> str:
    if not probabilities or market not in probabilities: return "UNAVAILABLE"
    return "AGREEMENT" if max(probabilities, key=probabilities.get) == market else "DISAGREEMENT"


def _odds_band(odds: Decimal) -> str:
    if odds < Decimal("1.70"): return "BELOW_1.70"
    if odds < Decimal("2.00"): return "1.70-1.99"
    if odds < Decimal("2.50"): return "2.00-2.49"
    if odds < Decimal("3.50"): return "2.50-3.49"
    return "3.50+"


def _response_rows(payload: object) -> list[dict]:
    rows = payload.get("response") if isinstance(payload, dict) else payload if isinstance(payload, list) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _result_count(payload: object) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("results"), int): return payload["results"]
    return len(_response_rows(payload))


def _metadata_time(metadata: object, fallback: datetime) -> datetime:
    raw = metadata.get("retrieved_at_utc") if isinstance(metadata, dict) else None
    try: return _utc(datetime.fromisoformat(str(raw).replace("Z", "+00:00"))) if raw else fallback
    except ValueError: return fallback


def _counts(values) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values: result[str(value)] = result.get(str(value), 0) + 1
    return dict(sorted(result.items()))


def _plain(value: object) -> object:
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, CapabilityTier): return value.value
    if isinstance(value, dict): return {str(key): _plain(item) for key, item in value.items() if key != "capability"}
    if isinstance(value, (tuple, list)): return [_plain(item) for item in value]
    return value


def _safe_int(value: object, default: int) -> int:
    try: return int(value)
    except (TypeError, ValueError): return default


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None: raise ValueError("LAB_V2_TIME_REQUIRES_OFFSET")
    return value.astimezone(timezone.utc)
