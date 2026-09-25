"""Adaptive broad-coverage current/upcoming Lab V2 selection cycle."""

from __future__ import annotations

from app.lab_combo.publication_window import publication_blocker

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from itertools import combinations
from math import factorial
import json
from pathlib import Path
import sqlite3
from typing import Callable

import httpx

from app.current_match_intelligence.serialization import snapshot_from_document
from app.football.client import FootballRequestLimitError
from app.football.quota import FootballQuotaError
from app.lab_combo.experimental import evaluate_snapshot
from app.real_match_lab_analysis.fingerprint import fingerprint

from .api_prediction import ApiPredictionSignal, normalize_api_prediction
from .bookmakers import CATALOGUE_CACHE_DAYS, catalogue_summary, review_bookmaker_catalogue
from .capability import CapabilityTier, LeagueCapability, LeagueCapabilityCache
from .context_signals import PlayerUsage, AvailabilityImpact, availability_impact, opponent_adjusted_form
from .ensemble import EnsembleDecision, EnsembleSignal
from .market_consensus import CurrentMarketConsensus, best_current_price, current_market_consensus
from .pi_ratings import MatchResult, PiAvailability, PiRatingAdapter, PiSignal, parse_api_fixture_results
from .quota import (
    SETTLEMENT_RESERVE, DAILY_SAFETY_RESERVE, MINIMUM_ENRICHMENT_CALLS, ODDS_RELEASED_RESERVE_CYCLE_FRACTION,
    MAX_DISCOVERY_CALLS_PER_CYCLE,
    AdaptiveQuotaBudget,
    adaptive_quota_budget,
    projected_daily_usage, discovery_state, PRIORITY_EXACT_RETRIES_PER_CYCLE,
)
from .repository import ShadowEvidenceRepository
from .tracking import load_reviews, new_review, restore_fixture
from .profiles import classify, fallback_capability, policy_for, is_priority, resource_priority
from .global_evaluation import evaluate_profile
from .signal_evidence import signal_requirements
from .scheduling import fair_order, record_service
from .diagnostics import global_diagnostic
from .odds_coverage import DateOddsCoverage, quote_absence_reason
from .forward_evidence import capture_selection


SCHEMA_VERSION = "goalvision-lab-v2-global-cycle-v8"
READINESS_POLICY_VERSION = "LAB_V2_FINAL_REVIEW_READINESS_V5"
MAXIMUM_CALLS = MAX_DISCOVERY_CALLS_PER_CYCLE
FINAL_REVIEW_WINDOW = timedelta(minutes=75)
FINAL_REVIEW_MAX_AGE = timedelta(minutes=5)
MINIMUM_KICKOFF_LEAD = timedelta(minutes=10)
FINAL_REVIEW_SHORTLIST_SIZE = 5
MAX_FINAL_REVIEW_CALLS_PER_FIXTURE = 4
MAX_PROVIDER_ATTEMPTS_PER_CALL = 3
LINEUP_SENSITIVE_MARKETS = frozenset({"HOME_WIN", "DRAW", "AWAY_WIN"})
MARKET_FAMILIES = {
    "1X2": ("HOME_WIN", "DRAW", "AWAY_WIN"),
    "BTTS": ("BTTS_YES", "BTTS_NO"),
    "TOTAL_1_5": ("OVER_1_5", "UNDER_1_5"),
    "TOTAL_2_5": ("OVER_2_5", "UNDER_2_5"),
    "TOTAL_3_5": ("OVER_3_5", "UNDER_3_5"),
}
TIER_ORDER = {
    CapabilityTier.TIER_A_FULL: 0,
    CapabilityTier.TIER_B_GOOD: 1,
    CapabilityTier.TIER_C_BASIC: 2,
    CapabilityTier.UNSUPPORTED: 3,
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
        adaptive_learning: object | None = None,
        runtime_clock: Callable[[], datetime] | None = None,
        football_context_observer: object | None = None,
    ) -> None:
        if not 1 <= maximum_calls <= MAXIMUM_CALLS:
            raise ValueError("LAB_V2_MAXIMUM_CALLS_MUST_BE_BETWEEN_1_AND_400")
        if daily_safety_reserve != DAILY_SAFETY_RESERVE:
            raise ValueError("LAB_V2_USE_SETTLEMENT_RESULT_RESERVE_100")
        self.football_context_observer = football_context_observer
        self.football_context_observer_failures = 0
        self.adaptive_learning = adaptive_learning
        self.runtime_clock = runtime_clock
        self.client = client
        self.repository = repository
        self.capability_cache_path = capability_cache_path
        self.analysis_path = analysis_path
        self.maximum_calls = maximum_calls
        self.daily_safety_reserve = daily_safety_reserve
        self.analysis_evidence: dict[int, dict] = {}
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
        near_only: bool = False,
    ) -> dict[str, object]:
        """Produce and persist analysis evidence without crossing the send boundary.

        ``publication_requested`` records the controlling CLI intent only.  This
        runner never constructs Telegram transport or mutates the publication
        ledger; the outer controlled-cycle command owns that handoff.
        """
        clock = _utc(now)
        if not 1 <= horizon_days <= 7:
            raise ValueError("LAB_V2_HORIZON_OUTSIDE_1_TO_7_DAYS")

        if discovery_state(clock) == "NIGHT_DISCOVERY_PAUSED":
            return self.pause_report(clock)

        if self.adaptive_learning is not None:
            from app.adaptive_lab.quota import SharedQuota
            SharedQuota(self.adaptive_learning.repository).bind(
                self.client, lambda: datetime.now(timezone.utc), allow_status_preflight=True)
        if hasattr(self.client, 'request_authorizer'):
            previous_authorizer = self.client.request_authorizer
            def authorize_daytime() -> None:
                if discovery_state(self.runtime_clock() if self.runtime_clock else clock) == 'NIGHT_DISCOVERY_PAUSED':
                    raise FootballQuotaError('NIGHT_DISCOVERY_PAUSED')
                if previous_authorizer is not None:
                    previous_authorizer()
            self.client.request_authorizer = authorize_daytime

        await self._fetch(
            "/status", {}, lambda: self.client.account_status(),
            clock=clock, ttl=None, use_cache=False,
        )
        quota = getattr(self.client, "quota_snapshot", lambda: {})()
        self.quota_budget = adaptive_quota_budget(
            quota, requested_maximum=self.maximum_calls,
            already_consumed=self._request_count(), now=clock,
            daily_safety_reserve=self.daily_safety_reserve,
        )
        if self.quota_budget.additional_calls_available == 0 and not hasattr(self.client, "quota_snapshot"):
            self.quota_budget = AdaptiveQuotaBudget(
                self.maximum_calls, self.maximum_calls, self._request_count(),
                self.maximum_calls - self._request_count(), None, None,
                self.daily_safety_reserve, None, "TEST_DOUBLE_EXPLICIT_LIMIT",
            )

        # Enforce the paced ceiling inside the provider too, including retries.
        restrict = getattr(self.client, "restrict_requests", None)
        if restrict:
            restrict(max(1, self._effective_maximum()), daily_reserve=self.daily_safety_reserve)

        capabilities, capability_cache_status = await self._capabilities(clock)
        tracked = load_reviews(self.repository, clock)
        tracked_ids = {key[0] for key in tracked}
        bookmaker_catalogue, bookmaker_cache_status = await self._bookmakers(clock)
        self.allowed_bookmaker_ids = frozenset(
            item.bookmaker_id for item in bookmaker_catalogue
            if item.relevance != "OTHER_CURRENT_PROVIDER_SOURCE"
        )

        fixtures: dict[int, dict[str, object]] = {}
        discovery_exclusions: list[dict[str, object]] = []
        fixture_rows_seen = 0
        days = _discovery_dates(clock, horizon_days)
        dates_fetched: list[str] = []
        dates_failed: list[str] = []
        for day in ([] if near_only else days):
            if self._remaining() <= 0:
                break
            payload, _ = await self._fetch(
                "/fixtures", {"date": day, "timezone": "UTC"},
                lambda value=day: self.client.fixtures_by_date(value, timezone_name="UTC"),
                clock=clock, ttl=timedelta(minutes=5), use_cache=True,
            )
            dates_fetched.append(day)
            if not _provider_payload_succeeded(payload):
                dates_failed.append(day)
            fixture_rows_seen += _result_count(payload)
            accepted, excluded = _fixture_rows_with_evidence(payload, capabilities, clock)
            discovery_exclusions.extend(excluded)
            for item in excluded:
                self.repository.append("discovery_rejection", fingerprint((clock, item)), item, created_at=clock)
            for item in accepted:
                fixtures[int(item["fixture_id"])] = item
                self.repository.append("global_discovery", f"{clock.isoformat()}:{item['fixture_id']}",
                                       {**_plain(item), "state": "DISCOVERED", "reason": "PROVIDER_DATE_FIXTURE"}, created_at=clock)
        for item in self.repository.latest_global_fixtures(now=clock, include_expired=True):
            if datetime.fromisoformat(item["kickoff_utc"]) <= clock:
                expired = {**item, "state": "RESULT_TRACKING", "reason": "PREMATCH_PUBLICATION_CLOSED",
                           "evaluated_at_utc": clock.isoformat(), "next_refresh_at": None}
                if item["fixture_id"] not in fixtures and item.get("state") != "RESULT_TRACKING":
                    self.repository.append("global_fixture_state", f"{clock.isoformat()}:{item['fixture_id']}", expired, created_at=clock)
                continue
            if item["fixture_id"] not in fixtures:
                metadata = item.get("provider_metadata")
                if metadata:
                    accepted, _ = _fixture_rows_with_evidence({"response": [metadata]}, capabilities, clock)
                    for restored in accepted:
                        fixtures[restored["fixture_id"]] = restored
        # Broad fixture/odds coverage is discovery, not the pending-review queue.
        for record in tracked.values():
            restored = restore_fixture(record, capabilities)
            if restored is not None and restored["kickoff_utc"] > clock:
                fixtures.setdefault(record["fixture_id"], restored)
        ordered = sorted(fixtures.values(), key=lambda item: (
            resource_priority(item), item["kickoff_utc"], TIER_ORDER[item["capability_tier"]], item["fixture_id"],
        ))

        # Started fixtures remain audit/result evidence, never new PREMATCH work.
        upcoming = [item for item in ordered if item.get("prematch_eligible", True)
                    and item["kickoff_utc"] > clock]
        if near_only:
            upcoming = [f for f in upcoming if MINIMUM_KICKOFF_LEAD < f['kickoff_utc'] - clock <= FINAL_REVIEW_WINDOW]
        first_resource_class = min((resource_priority(x) for x in upcoming), default=2)
        # Optional observation plan from existing immutable classification scalars.
        # This hook neither discovers fixtures nor returns prediction inputs.
        if self.football_context_observer is not None:
            try:
                prepare_context = getattr(self.football_context_observer, 'prepare', None)
                if prepare_context is not None:
                    prepare_context(tuple(tuple(f.get(k) for k in (
                        'fixture_id', 'league_id', 'season', 'competition_profile', 'classifier_version',
                        'classification_reason', 'classification_fingerprint', 'age_category'))
                        + (tuple(f.get('flags', ())),) for f in upcoming))
            except Exception:
                self.football_context_observer_failures += 1
        early_reviews, exact_evidence, priority_exact_evidence = {}, {}, {}
        due = [f for f in fair_order(upcoming, self.repository, phase='review')
               if MINIMUM_KICKOFF_LEAD < f['kickoff_utc'] - clock <= FINAL_REVIEW_WINDOW
               and resource_priority(f) == first_resource_class]
        for fixture in due[:FINAL_REVIEW_SHORTLIST_SIZE]:
            if self._remaining() < 2:
                break
            context = dict(near_kickoff=True, fixture_refreshed=False, odds_refreshed=False,
                           lineup_status='NOT_REQUESTED', injuries_status='NOT_REQUESTED',
                           reviewed_at_utc=None, status='FINAL_REVIEW_REQUIRED')
            early_reviews[fixture['fixture_id']] = await self._exact_review(
                fixture, clock, exact_evidence, context, optional_reserve=2 * len(due))
        for fixture in upcoming:
            identity = fixture['fixture_id']
            if (identity in tracked_ids and identity not in exact_evidence and self._remaining() > 0
                    and resource_priority(fixture) == first_resource_class):
                if len(priority_exact_evidence) >= PRIORITY_EXACT_RETRIES_PER_CYCLE:
                    break
                payload, retrieved = await self._fetch('/odds', {'fixture': identity},
                    lambda identity=identity: self.client.current_odds(identity),
                    clock=clock, ttl=timedelta(minutes=5), use_cache=False)
                consensus = current_market_consensus(payload, fixture_id=identity, retrieved_at=retrieved,
                    now=max(clock, retrieved), allowed_bookmaker_ids=self.allowed_bookmaker_ids) if _provider_payload_succeeded(payload) else {}
                exact_evidence[identity] = (payload, retrieved, consensus)
                priority_exact_evidence[identity] = (payload, retrieved)
                self.repository.append('tracked_odds_refresh', f'{clock.isoformat()}:{identity}',
                    {'fixture_id': identity, 'status': 'AVAILABLE' if any(c.status == 'AVAILABLE' for c in consensus.values()) else 'WAITING_CURRENT_ODDS',
                     'final_review': False, 'response_fingerprint': fingerprint(payload)}, created_at=clock)
        priority = fair_order([item for item in upcoming if is_priority(item)],
                              self.repository, phase="priority_odds")
        # Reserve analysis before date pagination can exhaust the cycle. Shared
        # league history and provider prediction each cost at most one first call;
        # exact misses are bounded separately and provider retries share the cap.
        priority_reserve = min(max(0, self._remaining() - len(days)), len(priority) * 3)
        odds_discovery_final_review_reserve = min(
            _final_review_call_reserve(upcoming, clock), self._remaining() // 4)
        odds_evidence, odds_page_report = await self._date_odds(
            [] if near_only or not upcoming else days, upcoming, clock, reserve_calls=max(priority_reserve, odds_discovery_final_review_reserve),
            tracked_fixture_ids=frozenset(tracked_ids), priority_reserve=priority_reserve,
        )
        odds_evidence.update(exact_evidence)
        histories, adapters, api_predictions = {}, {}, {}
        history_budget_skips = prediction_budget_skips = 0
        exact_retries = []
        # Finish a priority fixture's odds/context/model inputs before spending
        # quota on an ordinary fixture. Failed/absent prices still get analysis.
        for fixture in priority:
            fixture_id, league_id = fixture["fixture_id"], fixture["league_id"]
            if fixture_id not in odds_evidence and self._remaining() > 0 and len(exact_retries) < PRIORITY_EXACT_RETRIES_PER_CYCLE:
                record_service(self.repository, fixture, clock, "priority_odds")
                before_reason = odds_page_report["fixture_coverage_reasons"].get(str(fixture_id))
                payload, retrieved = await self._fetch(
                    "/odds", {"fixture": fixture_id},
                    lambda identity=fixture_id: self.client.current_odds(identity),
                    clock=clock, ttl=timedelta(minutes=5), use_cache=False)
                priority_exact_evidence[fixture_id] = (payload, retrieved)
                consensus = current_market_consensus(payload, fixture_id=fixture_id,
                    retrieved_at=retrieved, now=max(clock, retrieved),
                    allowed_bookmaker_ids=self.allowed_bookmaker_ids) if _provider_payload_succeeded(payload) else {}
                recovered = any(value.status == "AVAILABLE" for value in consensus.values())
                if recovered:
                    odds_evidence[fixture_id] = (payload, retrieved, consensus)
                    odds_page_report["fixture_statuses"][str(fixture_id)] = "FIXTURE_DISCOVERED_WITH_CURRENT_ODDS"
                exact_retries.append({"fixture_id": fixture_id, "broad_reason": before_reason,
                                      "recovered": recovered})
            if league_id not in histories:
                h, a, skipped = await self._histories([fixture], clock)
                histories.update(h); adapters.update(a); history_budget_skips += skipped
            predictions, skipped = await self._predictions([fixture], clock)
            api_predictions.update(predictions); prediction_budget_skips += skipped
        odds_page_report["priority_exact_retries"] = exact_retries
        # Every valid upcoming fixture reaches local model/context evaluation,
        # even when the current quote is missing. Never synthesize a price or EV.
        odds_fixtures = upcoming
        for fixture in odds_fixtures:
            odds_evidence.setdefault(fixture["fixture_id"], ({}, clock, {}))
        final_review_reserve = min(_final_review_call_reserve(odds_fixtures, clock), self._remaining() // 4)
        ordinary = [item for item in upcoming if not is_priority(item)]
        h, a, skipped = await self._histories(
            [item for item in ordinary if item["league_id"] not in histories], clock,
            reserve_calls=final_review_reserve)
        histories.update(h); adapters.update(a); history_budget_skips += skipped
        predictions, skipped = await self._predictions(ordinary, clock, reserve_calls=final_review_reserve)
        api_predictions.update(predictions); prediction_budget_skips += skipped
        persisted_models, v1_keys, persisted_usage = self._persisted_v1(odds_fixtures, clock)

        preliminary = self._evaluate(
            odds_fixtures, odds_evidence, histories, adapters, api_predictions,
            persisted_models, {}, {}, clock,
        )
        shortlist_ids = _shortlist(preliminary, maximum=max(1, len(odds_fixtures)))
        tracked_due = [item["fixture_id"] for item in ordered
                       if item["fixture_id"] in tracked_ids
                       and MINIMUM_KICKOFF_LEAD < item["kickoff_utc"] - clock <= FINAL_REVIEW_WINDOW]
        all_due = [item['fixture_id'] for item in ordered
                   if MINIMUM_KICKOFF_LEAD < item['kickoff_utc'] - clock <= FINAL_REVIEW_WINDOW]
        review_pool = list(dict.fromkeys([*tracked_due, *all_due, *shortlist_ids]))
        near_pool = [i for i in review_pool if MINIMUM_KICKOFF_LEAD < fixtures[i]["kickoff_utc"] - clock <= FINAL_REVIEW_WINDOW]
        review_pool = near_pool or review_pool
        shortlist_ids = [item["fixture_id"] for item in fair_order(
            [fixtures[i] for i in review_pool], self.repository, phase="review")][:FINAL_REVIEW_SHORTLIST_SIZE]
        availability: dict[int, dict[str, AvailabilityImpact]] = {}
        final_reviews: dict[int, dict[str, object]] = dict(early_reviews)
        cmi_enriched: set[int] = set()
        for fixture_id in shortlist_ids:
            fixture = fixtures[fixture_id]
            if publication_blocker(clock,[fixture['kickoff_utc']]) is not None:
                continue
            capability: LeagueCapability = fixture["capability"]
            near = timedelta(0) < fixture["kickoff_utc"] - clock <= FINAL_REVIEW_WINDOW
            if fixture_id in early_reviews:
                continue
            context: dict[str, object] = {
                "near_kickoff": near,
                "fixture_refreshed": False,
                "odds_refreshed": False,
                "lineup_status": "NOT_REQUESTED",
                "injuries_status": "NOT_REQUESTED",
                "reviewed_at_utc": None,
                "status": "FINAL_REVIEW_REQUIRED",
                "reason": "FINAL_REVIEW_BUDGET_UNAVAILABLE" if near else "FINAL_REVIEW_WINDOW_NOT_OPEN",
            }
            if capability.injuries and self._remaining() > (3 if near else 0):
                payload, _ = await self._fetch(
                    "/injuries", {"fixture": fixture_id},
                    lambda identity=fixture_id: self._provider("injuries", identity, "/injuries"),
                    clock=clock, ttl=timedelta(hours=4), use_cache=not near,
                )
                if _provider_payload_succeeded(payload):
                    availability[fixture_id] = _availability_from_payload(
                        payload, fixture, usage=persisted_usage.get(fixture_id, {}),
                    )
                    context["injuries_status"] = "REFRESHED" if near else "AVAILABLE"
                    cmi_enriched.add(fixture_id)
                else:
                    context["injuries_status"] = "PROVIDER_ERROR"
            elif not capability.injuries:
                context["injuries_status"] = "NOT_SUPPORTED"

            if near and self._remaining() >= 2:
                context = await self._exact_review(fixture, clock, odds_evidence, context,
                                                   exact_cache=priority_exact_evidence)
                cmi_enriched.add(fixture_id)
            final_reviews[fixture_id] = context

        evaluation_clock = max(clock, _metadata_time(getattr(self.client, 'response_metadata', lambda: {})(), clock))
        # Observation-only input boundary: after collection, before FINAL evaluation.
        context_receipt = None
        if self.football_context_observer is not None:
            try:
                context_receipt = self.football_context_observer.begin()
            except Exception:
                self.football_context_observer_failures += 1
        candidates = self._evaluate(
            odds_fixtures, odds_evidence, histories, adapters, api_predictions,
            persisted_models, availability, final_reviews, evaluation_clock,
        )
        if self.football_context_observer is not None:
            try:
                from app.prematch_football_context.snapshot.observer import identity
                self.football_context_observer.bind(context_receipt, tuple(identity(c) for c in candidates))
            except Exception:
                self.football_context_observer_failures += 1
        lifecycle = self._track_reviews(tracked, candidates, fixtures, final_reviews, clock)
        current_odds_fixture_count = sum(
            any(value.status == "AVAILABLE" for value in families.values())
            for _, _, families in odds_evidence.values()
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
        fixture_coverage = _fixture_coverage(
            ordered, candidates, odds_page_report["fixture_statuses"], discovery_exclusions,
        )
        report = {
            "discovery_state": discovery_state(clock),
            "schema_version": SCHEMA_VERSION,
            "mode": "LAB_V2_NO_SEND",
            "analysis_mode": "LAB_V2_NO_SEND",
            "publication_requested": bool(publication_requested),
            "publication_enabled": bool(publication_requested),
            "publication_attempt_count": 0,
            "evaluated_at_utc": clock.isoformat(),
            "fixtures_discovered": len(fixtures),
            "provider_fixture_rows": fixture_rows_seen,
            "discovery_dates_requested": days,
            "discovery_dates_fetched": dates_fetched,
            "discovery_dates_failed": dates_failed,
            "discovery_dates_unvisited": sorted(set(days) - set(dates_fetched)),
            "discovery_window_complete": not dates_failed and len(dates_fetched) == len(days),
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
            "fixtures_with_unsupported_current_markets": odds_page_report[
                "fixtures_with_unsupported_current_markets"
            ],
            "fixtures_with_incomplete_odds_page_coverage": odds_page_report[
                "fixtures_with_incomplete_odds_page_coverage"
            ],
            "current_odds_fixtures": current_odds_fixture_count,
            "fixtures_considered_for_evaluation": len(odds_fixtures),
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
            "tracked_final_reviews": lifecycle,
            "tracked_final_review_state_counts": _counts(item["state"] for item in lifecycle),
            "tracked_final_review_shortlist": [value for value in shortlist_ids if value in tracked_due],
            "rejection_reasons": rejection_reasons,
            "fixture_coverage": fixture_coverage,
            "fixture_coverage_status_counts": _counts(item["status"] for item in fixture_coverage),
            "one_x_two_diagnostics": _one_x_two_diagnostics(candidates),
            "readiness_policy": READINESS_POLICY_VERSION,
            "near_kickoff_cycle_result": "NO_FIXTURES_CURRENTLY_DUE" if not due else "EXACT_REVIEW_ATTEMPTED",
            "currently_due_fixtures": len(due),
            "lineup_sensitive_markets": sorted(LINEUP_SENSITIVE_MARKETS),
            "final_review_call_reserve": final_review_reserve,
            "odds_discovery_final_review_call_reserve": odds_discovery_final_review_reserve,
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
                    str(Decimal(current_odds_fixture_count) / Decimal(self._request_count()))
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
        # Exact refresh status supersedes broad-discovery coverage in diagnostics too.
        effective_odds_statuses = dict(odds_page_report["fixture_statuses"])
        for fixture_id, review in final_reviews.items():
            if review.get("odds_status"):
                effective_odds_statuses[str(fixture_id)] = {
                    "AVAILABLE": "FIXTURE_DISCOVERED_WITH_CURRENT_ODDS",
                    "ODDS_STALE": "FIXTURE_DISCOVERED_ODDS_STALE",
                    "CURRENT_ODDS_UNAVAILABLE": "FIXTURE_DISCOVERED_NO_CURRENT_ODDS",
                }[review["odds_status"]]
        diagnostic = global_diagnostic(ordered, candidates, effective_odds_statuses, clock, reviews=final_reviews,
                                       odds_reasons=odds_page_report["fixture_coverage_reasons"])
        report.update(diagnostic)
        report['readiness_lanes'] = {lane + '_READY': sum(c.get('readiness_lane') == lane + '_READY' for c in candidates)
                                     for lane in ('EXPERIMENTAL', 'STANDARD', 'STRONG')}
        report['predictive_evidence_counts'] = {
            'one_family_fixtures': len({c['fixture_id'] for c in candidates if c['predictive_family_count'] == 1}),
            'two_plus_family_fixtures': len({c['fixture_id'] for c in candidates if c['predictive_family_count'] >= 2})}
        report['exact_fixture_odds_refresh_calls'] = sum(int(c['actual_calls']) for c in self.calls if c['endpoint'] == '/odds' and 'fixture' in c['query'])
        for item in diagnostic["global_fixture_states"]:
            self.repository.append("global_fixture_state", f"{clock.isoformat()}:{item['fixture_id']}", item, created_at=clock)
        for item in discovery_exclusions:
            self.repository.append("discovery_rejection", fingerprint((clock, item)), item, created_at=clock)
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
        shadow_captures = 0
        for analysis in self.analysis_evidence.values():
            self.repository.append("model_analysis", fingerprint(analysis), analysis, created_at=clock)
        for candidate in candidates:
            self.repository.append("candidate", candidate["candidate_id"], candidate, created_at=clock)
            capture_clock = max(clock, datetime.fromisoformat(candidate["goalvision_retrieved_at_utc"]),
                                self.runtime_clock() if self.runtime_clock else clock)
            shadow_captures += int(capture_selection(self.repository, candidate, now=capture_clock))
        report.update(
            priority_fixtures_discovered=len(priority),
            priority_fixtures_analyzed=sum(i["fixture_id"] in self.analysis_evidence and
                self.analysis_evidence[i["fixture_id"]]["probability_available"] for i in priority),
            total_analyzed=sum(i["probability_available"] for i in self.analysis_evidence.values()),
            model_analysis_attempts=len(self.analysis_evidence),
            waiting_odds_refresh=len(upcoming) - current_odds_fixture_count,
            soft_confidence_penalties=sum(bool(i.get("soft_findings") or i.get("soft_penalties")) for i in candidates),
            actual_hard_rejects=sum(bool(i.get("hard_failures")) for i in candidates),
            positive_ev_shadow_observations=shadow_captures,
        )
        persisted_report = {key: value for key, value in report.items() if key != "candidate_markets"}
        persisted_report.update({
            "candidate_document_kind": "candidate",
            "candidate_ids": [item["candidate_id"] for item in candidates],
            "readiness_reasons": _counts(
                reason for item in candidates for reason in item.get("readiness_reasons", ())
            ),
            "candidate_payload_storage": "INDIVIDUAL_APPEND_ONLY_DOCUMENTS_NOT_DUPLICATED_IN_CYCLE",
        })
        self.repository.append("rehearsal", identity, persisted_report, created_at=clock)
        return _plain(report)

    def pause_report(self, clock: datetime) -> dict[str, object]:
        """Persist an intentional pause without any provider operation."""
        report = night_report(clock)
        self.repository.append("rehearsal", "lab-v2-night-" + fingerprint(clock), report, created_at=clock)
        return report

    def _track_reviews(
        self, tracked: dict, candidates: list[dict], fixtures: dict,
        reviews: dict, clock: datetime,
    ) -> list[dict]:
        """Record every pending market's outcome without recycling its old price."""
        by_key = {(item["fixture_id"], item["market"]): item for item in candidates}
        terminal_keys = self.repository.terminal_review_keys()
        for key, candidate in by_key.items():
            if key in terminal_keys:
                tracked.setdefault(key, self.repository.review(*key))
            if candidate["stage"] in {"EARLY_CANDIDATE", "FINAL_REVIEW_REQUIRED", "READY_TO_PUBLISH"} or (
                not candidate.get("hard_failures") and candidate.get("soft_findings")
            ):
                tracked.setdefault(key, new_review(candidate, clock))
        result = []
        for key, previous in sorted(tracked.items()):
            fixture_id, _ = key
            fixture = fixtures.get(fixture_id)
            review = reviews.get(fixture_id, {})
            candidate = by_key.get(key)
            record = {**previous, "evaluated_at_utc": clock.isoformat(), "final_review": review}
            kickoff = fixture["kickoff_utc"] if fixture else datetime.fromisoformat(record["kickoff_utc"])
            record["kickoff_utc"] = kickoff.isoformat()
            remaining = kickoff - clock
            if remaining <= MINIMUM_KICKOFF_LEAD:
                state, reasons = "PUBLICATION_CLOSED", ["PREMATCH_PUBLICATION_CLOSED"]
            elif review.get("status") == "PREMATCH_CLOSED":
                state, reasons = "PUBLICATION_CLOSED", ["PREMATCH_PUBLICATION_CLOSED"]
            elif fixture is None:
                state, reasons = "FIXTURE_INVALID", ["CURRENT_SEASON_CAPABILITY_NOT_FOUND"]
            elif review.get("status") == "FIXTURE_INVALID":
                state, reasons = "FIXTURE_INVALID", [review["reason"]]
            elif remaining > FINAL_REVIEW_WINDOW:
                state, reasons = "EARLY_CANDIDATE", ["FINAL_REVIEW_WINDOW_NOT_OPEN"]
            elif not review.get("fixture_refreshed"):
                state, reasons = "FINAL_REVIEW_REQUIRED", [review.get("reason", "FINAL_REVIEW_SHORTLIST_OR_BUDGET_PENDING")]
            elif review.get("odds_status") in {"ODDS_STALE", "CURRENT_ODDS_UNAVAILABLE"}:
                state, reasons = review["odds_status"], [review["odds_status"]]
            elif candidate is None:
                state, reasons = "CURRENT_ODDS_UNAVAILABLE", ["TRACKED_MARKET_CURRENT_ODDS_UNAVAILABLE"]
            else:
                state = candidate["stage"]
                reasons = candidate["rejection_reasons"] or candidate["readiness_reasons"]
            record.update(state=state, reasons=list(reasons),
                          candidate_id=candidate["candidate_id"] if candidate else None)
            self.repository.save_tracked_review(record, now=clock)
            result.append(record)
        return result

    async def _exact_review(self, fixture: dict, clock: datetime, odds_evidence: dict, context: dict,
                            *, optional_reserve: int = 0, exact_cache: dict | None = None) -> dict:
        """Mandatory exact pair bypasses cache and replaces even successful broad quotes."""
        fixture_id = fixture['fixture_id']
        capability = fixture['capability']
        record_service(self.repository, fixture, clock, "review")
        fixture_payload, _ = await self._fetch(
            "/fixtures", {"id": fixture_id},
            lambda identity=fixture_id: self.client.fixture(identity),
            clock=clock, ttl=timedelta(minutes=2), use_cache=False,
        )
        refreshed_kickoff = _refreshed_fixture_kickoff(fixture_payload, fixture_id, clock)
        context["fixture_refreshed"] = refreshed_kickoff is not None
        refreshed_rows = [row for row in _response_rows(fixture_payload)
                          if str((row.get("fixture") or {}).get("id")) == str(fixture_id)]
        refreshed_status = (
            ((refreshed_rows[0].get("fixture") or {}).get("status") or {}).get("short")
            if refreshed_rows and _provider_payload_succeeded(fixture_payload) else None
        )
        context["fixture_status"] = refreshed_status
        exact_teams = refreshed_rows[0].get("teams", {}) if refreshed_rows else {}
        identity_conflict = (bool(refreshed_rows) and (refreshed_rows[0].get('league') or {}).get('id', fixture['league_id']) != fixture['league_id']) or bool(exact_teams) and any(
            str((exact_teams.get(side) or {}).get("id")) != str(fixture[f"{side}_team_id"])
            for side in ("home", "away")
        )
        if identity_conflict:
            context.update(status="FIXTURE_INVALID", reason="CONTRADICTORY_FIXTURE_IDENTITY")
            refreshed_kickoff = None
        elif refreshed_status is not None and refreshed_status not in {"NS", "TBD"}:
            context.update(status="PREMATCH_CLOSED", reason="FIXTURE_STATUS_NOT_UPCOMING")
        elif refreshed_kickoff is None:
            context.update(reason="FIXTURE_REFRESH_UNAVAILABLE")
            if refreshed_status in {"NS", "TBD"}:
                try:
                    changed = _utc(datetime.fromisoformat(
                        str(refreshed_rows[0]["fixture"]["date"]).replace("Z", "+00:00")
                    ))
                except (KeyError, TypeError, ValueError):
                    pass
                else:
                    if changed <= clock:
                        fixture["kickoff_utc"] = changed
                        context["refreshed_kickoff_utc"] = changed.isoformat()
        if refreshed_kickoff is not None:
            fixture["kickoff_utc"] = refreshed_kickoff
            context["refreshed_kickoff_utc"] = refreshed_kickoff.isoformat()
            context.update(status="FIXTURE_REFRESHED", reason="EXACT_FIXTURE_REFRESH_COMPLETE")
        if exact_cache is not None and fixture_id in exact_cache:
            odds_payload, retrieved = exact_cache[fixture_id]
        else:
            odds_payload, retrieved = await self._fetch(
                "/odds", {"fixture": fixture_id},
                lambda identity=fixture_id: self.client.current_odds(identity),
                clock=clock, ttl=timedelta(minutes=5), use_cache=False,
            )
        exact_consensus = current_market_consensus(
            odds_payload, fixture_id=fixture_id, retrieved_at=retrieved,
            now=max(clock, retrieved),
            allowed_bookmaker_ids=self.allowed_bookmaker_ids,
        ) if _provider_payload_succeeded(odds_payload) else {}
        # The exact response supersedes broad quotes, including missing markets.
        odds_evidence[fixture_id] = (odds_payload, retrieved, exact_consensus)
        context["odds_retrieved_at_utc"] = retrieved.isoformat()
        context["odds_provider_timestamp_utc"] = next((
            row.get("update") for row in _response_rows(odds_payload)
            if str((row.get("fixture") or {}).get("id")) == str(fixture_id)
        ), None)
        context["odds_status"] = (
            "AVAILABLE" if any(value.status == "AVAILABLE" for value in exact_consensus.values()) else
            "ODDS_STALE" if any(value.status == "STALE_CURRENT_ODDS" for value in exact_consensus.values()) else
            "CURRENT_ODDS_UNAVAILABLE"
        )
        context['odds_retry_state'] = (
            None if context['odds_status'] == 'AVAILABLE' else
            'ODDS_FINAL_REFRESH_FAILED' if not _provider_payload_succeeded(odds_payload) or context['odds_status'] == 'ODDS_STALE'
            else 'ODDS_FINAL_MARKET_UNAVAILABLE')
        if context["odds_status"] == "AVAILABLE":
            context["odds_refreshed"] = True
        if capability.lineups and self._remaining() > optional_reserve:
            lineup_payload, _ = await self._fetch(
                "/fixtures/lineups", {"fixture": fixture_id},
                lambda identity=fixture_id: self._provider("lineup", identity, "/fixtures/lineups"),
                clock=clock, ttl=timedelta(minutes=5), use_cache=False,
            )
            context["lineup_status"] = (
                "PROVIDER_ERROR" if not _provider_payload_succeeded(lineup_payload) else
                "CONFIRMED" if _confirmed_lineups(lineup_payload, fixture) else
                "NOT_YET_PUBLISHED"
            )
        else:
            context["lineup_status"] = "NOT_SUPPORTED"
        context["reviewed_at_utc"] = _metadata_time(
            getattr(self.client, "response_metadata", lambda: {})(), clock
        ).isoformat()
        return context

    async def _date_odds(
        self, days: list[str], fixtures: list[dict[str, object]], clock: datetime,
        *, reserve_calls: int = 0, tracked_fixture_ids: frozenset[int] = frozenset(),
        priority_reserve: int = 0,
    ) -> tuple[dict[int, tuple[object, datetime, dict[str, CurrentMarketConsensus]]], dict[str, object]]:
        fixture_ids = {int(item["fixture_id"]) for item in fixtures}
        fixture_days = {int(item["fixture_id"]): item["kickoff_utc"].date().isoformat() for item in fixtures}
        result: dict[int, tuple[object, datetime, dict[str, CurrentMarketConsensus]]] = {}
        first_pages: list[tuple[str, int]] = [(day, 1) for day in days]
        continuation_pages: list[tuple[str, int]] = []
        cursor_by_day = {row["date"]: row["next_page"] for row in self.repository.all("odds_page_cursor")}
        skipped_prefix_days: set[str] = set()
        previous_maxima: dict[str, int] = {}
        for checkpoint in self.repository.all('odds_date_coverage'):
            day = checkpoint['date']
            previous_maxima[day] = max(previous_maxima.get(day, 1), checkpoint['maximum_advertised_total'])
        coverage = {day: DateOddsCoverage(previous_maximum=previous_maxima.get(day, 1)) for day in days}
        details: dict[int, str] = {}
        initial_reserve = reserve_calls
        fetched: list[dict[str, object]] = []
        joined_fixture_ids: set[int] = set()
        stale_fixture_ids: set[int] = set()
        unreliable_fixture_ids: set[int] = set()
        unsupported_market_fixture_ids: set[int] = set()
        empty_quote_fixture_ids: set[int] = set()
        tracked_quote_times: dict[str, dict[str, object]] = {}
        quote_ages: dict[str, float | None] = {}
        enrichment_reserve = min(MINIMUM_ENRICHMENT_CALLS, self._remaining() // 2)
        page_budget = max(0, self._remaining() - max(reserve_calls, enrichment_reserve))
        used = 0
        while (first_pages or continuation_pages) and self._remaining() > reserve_calls and used < page_budget:
            # Finish current date before next date, including incomplete pages.
            queue = sorted([*first_pages, *continuation_pages])
            day, page = queue[0]
            if (day, page) in first_pages:
                first_pages.remove((day, page))
            else:
                continuation_pages.remove((day, page))
            payload, retrieved = await self._fetch(
                "/odds(date)", {"date": day, "page": page},
                lambda value=day, number=page: self._provider_odds_date(value, number),
                # A 15-minute page cannot be reused by the 30-minute cycle.
                # Normalized per-fixture quote evidence is persisted below;
                # retaining every expired unrelated page caused unbounded growth.
                clock=clock, ttl=None, use_cache=False,
            )
            used += int(self.calls[-1]["actual_calls"])
            paging = payload.get("paging") if isinstance(payload, dict) and isinstance(payload.get("paging"), dict) else {}
            valid_page = coverage[day].observe(page, payload)
            current = page
            total = coverage[day].maximum
            fetched.append({"date": day, "page": current, "total_pages": _safe_int(paging.get("total"), 0),
                            "maximum_total_observed": total, "rows": _result_count(payload),
                            "response_fingerprint": fingerprint(payload),
                            "provider_fixture_ids": [_safe_int(r["fixture"].get("id"), -1) for r in _response_rows(payload) if isinstance(r.get("fixture"), dict)]})
            self.repository.append('odds_date_coverage', f'{clock.isoformat()}:{day}:{current}',
                                   {'date': day, **coverage[day].document()}, created_at=clock)
            if not valid_page:
                continue
            for row in _response_rows(payload):
                fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
                fixture_id = _safe_int(fixture.get("id"), -1)
                if fixture_id not in fixture_ids:
                    continue
                joined_fixture_ids.add(fixture_id)
                expected = next(item for item in fixtures if int(item["fixture_id"]) == fixture_id)
                row_league = row.get("league") if isinstance(row.get("league"), dict) else {}
                if ((row_league.get("id") is not None and expected.get("league_id") is not None
                     and row_league["id"] != expected["league_id"]) or fixture_days[fixture_id] != day):
                    details[fixture_id] = "ODDS_FIXTURE_LEAGUE_OR_DATE_MISMATCH"
                    unreliable_fixture_ids.add(fixture_id)
                    result.pop(fixture_id, None)
                    continue
                if fixture_id in tracked_fixture_ids:
                    tracked_quote_times[str(fixture_id)] = {
                        "provider_timestamp_utc": row.get("update"),
                        "retrieved_at_utc": retrieved.isoformat(),
                        "date": day, "page": current,
                    }
                try:
                    updated = datetime.fromisoformat(str(row.get('update')).replace('Z', '+00:00'))
                    quote_ages[str(fixture_id)] = (max(clock, retrieved) - updated).total_seconds()
                except (ValueError, TypeError):
                    quote_ages[str(fixture_id)] = None
                single_payload = {"results": 1, "response": [row]}
                consensus = current_market_consensus(
                    single_payload, fixture_id=fixture_id,
                    retrieved_at=retrieved, now=max(clock, retrieved),
                    allowed_bookmaker_ids=self.allowed_bookmaker_ids,
                )
                details[fixture_id] = ("CURRENT_ODDS_AVAILABLE" if any(v.status == "AVAILABLE" for v in consensus.values()) else
                    "ODDS_STALE" if consensus and all(v.status == "STALE_CURRENT_ODDS" for v in consensus.values()) else
                    "ODDS_INSUFFICIENT_COMPARABLE_BOOKMAKERS" if any(v.quote_count for v in consensus.values()) else
                    quote_absence_reason(row, self.allowed_bookmaker_ids))
                if any(value.status == "AVAILABLE" for value in consensus.values()):
                    result[fixture_id] = (single_payload, retrieved, consensus)
                elif consensus and all(value.status == "STALE_CURRENT_ODDS" for value in consensus.values()):
                    stale_fixture_ids.add(fixture_id)
                elif consensus and all(value.quote_count == 0 for value in consensus.values()):
                    if _has_raw_bookmaker_values(row):
                        unsupported_market_fixture_ids.add(fixture_id)
                    else:
                        empty_quote_fixture_ids.add(fixture_id)
                else:
                    unreliable_fixture_ids.add(fixture_id)
            next_page = current + 1
            if current == 1 and 2 < cursor_by_day.get(day, 2) <= total:
                next_page = cursor_by_day[day]
                skipped_prefix_days.add(day)
                coverage[day].restart_gap = True
            pending = sorted(set(range(1, total + 1)) - coverage[day].attempted)
            if pending:
                next_page = next_page if next_page in pending else pending[0]
                continuation_pages.append((day, next_page))
            if set(range(1, total + 1)) <= coverage[day].pages:
                skipped_prefix_days.discard(day)
                coverage[day].restart_gap = False
            self.repository.append("odds_page_cursor", f"{clock.isoformat()}:{day}:{current}",
                                   {"date": day, "next_page": next_page if current < total else 2}, created_at=clock)
            # Release only reserve for near-kickoff fixtures proven to have no usable odds.
            # Daily reserve and the cycle ceiling remain unchanged; enrichment keeps capacity.
            if initial_reserve and coverage[day].reason() is None:
                potential = [item for item in fixtures if item['fixture_id'] in result
                             or item['fixture_id'] in tracked_fixture_ids
                             or coverage.get(fixture_days[item['fixture_id']], DateOddsCoverage()).reason() is not None]
                reserve_calls = max(priority_reserve, min(reserve_calls, _final_review_call_reserve(potential, clock)))
                if reserve_calls < initial_reserve:
                    page_budget = max(page_budget, min(
                        int(self._effective_maximum() * ODDS_RELEASED_RESERVE_CYCLE_FRACTION) - self._request_count() + used,
                        self._remaining() - max(MINIMUM_ENRICHMENT_CALLS, reserve_calls) + used))
        unvisited = [*first_pages, *continuation_pages]
        unvisited_pages = sum(len(set(range(1, c.maximum + 1)) - c.pages) for c in coverage.values())
        incomplete_days = ({day for day, c in coverage.items() if c.reason() is not None}
                           | skipped_prefix_days | (set(fixture_days.values()) - set(coverage)))
        for fixture_id in fixture_ids - joined_fixture_ids:
            day = fixture_days[fixture_id]
            details[fixture_id] = (coverage.get(day, DateOddsCoverage()).reason(reserve_limited=self._remaining() <= reserve_calls)
                or ('ODDS_RESTART_PREFIX_NOT_REFRESHED' if day in skipped_prefix_days else 'ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD'))
        no_odds_ids = {
            fixture_id for fixture_id in fixture_ids - joined_fixture_ids
            if fixture_days.get(fixture_id) not in incomplete_days
        }
        incomplete_ids = {
            fixture_id for fixture_id in fixture_ids - joined_fixture_ids
            if fixture_days.get(fixture_id) in incomplete_days
        }
        fixture_statuses = {
            str(fixture_id): (
                "FIXTURE_DISCOVERED_WITH_CURRENT_ODDS" if fixture_id in result else
                "FIXTURE_DISCOVERED_ODDS_STALE" if fixture_id in stale_fixture_ids else
                "FIXTURE_DISCOVERED_MARKET_UNSUPPORTED" if fixture_id in unsupported_market_fixture_ids else
                "FIXTURE_DISCOVERED_ODDS_UNNORMALIZABLE" if fixture_id in unreliable_fixture_ids else
                "FIXTURE_DISCOVERED_NO_CURRENT_ODDS" if fixture_id in empty_quote_fixture_ids else
                "FIXTURE_DISCOVERED_ODDS_COVERAGE_INCOMPLETE" if fixture_id in incomplete_ids else
                "FIXTURE_DISCOVERED_NO_CURRENT_ODDS" if fixture_id in no_odds_ids else
                "FIXTURE_DISCOVERED_NO_CURRENT_ODDS"
            ) for fixture_id in sorted(fixture_ids)
        }
        return result, {
            "pages_fetched": fetched,
            "coverage_by_date": {day: value.document() for day, value in coverage.items()},
            "fixture_coverage_reasons": {str(k): v for k, v in sorted(details.items())},
            "coverage_reason_counts": {reason: list(details.values()).count(reason) for reason in sorted(set(details.values()))},
            "fixtures_with_complete_odds_coverage": len(fixture_ids) - len(incomplete_ids),
            "initial_final_review_reserve": initial_reserve,
            "remaining_final_review_reserve": reserve_calls,
            "page_calls": used,
            "pages_not_fetched_due_to_budget": sum(len(set(range(1, c.maximum + 1)) - c.attempted) for c in coverage.values() if not c.errors),
            "pages_missing_valid_response": unvisited_pages,
            "unvisited_pages": [{"date": day, "page": page} for day, page in sorted(unvisited)],
            "fixtures_not_analyzed_due_to_budget": len(incomplete_ids),
            "fixtures_with_no_current_odds": len(no_odds_ids | empty_quote_fixture_ids),
            "fixtures_with_incomplete_odds_page_coverage": len(incomplete_ids),
            "fixtures_rejected_for_stale_current_odds": len(stale_fixture_ids - result.keys()),
            "fixtures_with_unreliable_market_normalization": len(
                unreliable_fixture_ids - result.keys() - stale_fixture_ids
            ),
            "fixtures_with_unsupported_current_markets": len(
                unsupported_market_fixture_ids - result.keys() - stale_fixture_ids
            ),
            "fixture_statuses": fixture_statuses,
            "tracked_fixture_quote_times": tracked_quote_times,
            "provider_quote_age_seconds_by_fixture": quote_ages,
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
        league_order = fair_order([targets[0] for targets in grouped.values()], self.repository, phase="history")
        league_order.sort(key=lambda f: (not (MINIMUM_KICKOFF_LEAD < f['kickoff_utc'] - clock <= FINAL_REVIEW_WINDOW), f['kickoff_utc']))
        for target in league_order:
            league_id = int(target["league_id"])
            targets = grouped[league_id]
            policy = policy_for(targets[0].get("competition_profile", "UNKNOWN"))
            season = int(targets[0]["season"])
            near=any(MINIMUM_KICKOFF_LEAD < item["kickoff_utc"]-clock <= FINAL_REVIEW_WINDOW for item in targets)
            history_query={"league":league_id,"season":season,"status":"FT","last":99}
            cached_history=None if near else self.repository.cached("/fixtures(results)",history_query,now=clock)
            if self._remaining() <= reserve_calls and cached_history is None:
                skipped += len(targets)
                continue
            record_service(self.repository, targets[0], clock, "history")
            payload, _ = await self._fetch(
                "/fixtures(results)", {"league": league_id, "season": season, "status": "FT", "last": 99},
                lambda lid=league_id, value=season: self.client.finished_matches(lid, value, last=99),
                clock=clock, ttl=timedelta(hours=6), use_cache=not any(
                    MINIMUM_KICKOFF_LEAD < item["kickoff_utc"] - clock <= FINAL_REVIEW_WINDOW
                    for item in targets
                ),
            )
            matches = list(parse_api_fixture_results((payload,)))
            adapter = PiRatingAdapter(league_id)
            adapter.replay(matches, before=clock)
            needs_previous = any(
                adapter.signal(int(item["home_team_id"]), int(item["away_team_id"])).state
                in {PiAvailability.INSUFFICIENT, PiAvailability.UNAVAILABLE}
                for item in targets
            )
            if needs_previous and policy.history_days >= 365 and season > 1 and self._remaining() > max(16, reserve_calls) and not is_priority(targets[0]):
                previous, _ = await self._fetch(
                    "/fixtures(results)", {"league": league_id, "season": season - 1, "status": "FT", "last": 99},
                    lambda lid=league_id, value=season - 1: self.client.finished_matches(lid, value, last=99),
                    clock=clock, ttl=timedelta(days=1), use_cache=True,
                )
                matches = list(parse_api_fixture_results((previous, payload)))
                adapter = PiRatingAdapter(league_id)
                adapter.replay(matches, before=clock)
            matches = [m for m in matches if m.league_id==league_id
                       and m.fixture_id not in {int(t['fixture_id']) for t in targets}
                       and clock - timedelta(days=policy.history_days) <= m.kickoff_utc < clock]
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
        for fixture in sorted(fair_order(fixtures, self.repository, phase="prediction"), key=lambda f: (
                not (MINIMUM_KICKOFF_LEAD < f['kickoff_utc'] - clock <= FINAL_REVIEW_WINDOW), f['kickoff_utc'])):
            capability: LeagueCapability = fixture["capability"]
            if not capability.predictions:
                continue
            fixture_id = int(fixture["fixture_id"])
            near=MINIMUM_KICKOFF_LEAD < fixture['kickoff_utc']-clock <= FINAL_REVIEW_WINDOW
            cached=None if near else self.repository.cached('/predictions',{'fixture':fixture_id},now=clock)
            if self._remaining() <= reserve_calls and cached is None:
                skipped += 1
                continue
            payload, _ = await self._fetch(
                "/predictions", {"fixture": fixture_id},
                lambda identity=fixture_id: self._provider("prediction", identity, "/predictions"),
                clock=clock, ttl=timedelta(hours=1), use_cache=not (
                    MINIMUM_KICKOFF_LEAD < fixture["kickoff_utc"] - clock <= FINAL_REVIEW_WINDOW
                ),
            )
            record_service(self.repository, fixture, clock, "prediction")
            result[fixture_id] = normalize_api_prediction(
                payload, fixture_id=fixture_id, home_team_id=fixture["home_team_id"],
                away_team_id=fixture["away_team_id"], league_id=fixture["league_id"], season=fixture["season"])
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
            self.calls.append({"endpoint": endpoint, "query": query, "cache": "SKIPPED_BUDGET",
                               "actual_calls": 0, "result_count": 0})
            return {"errors": {"request": "LAB_V2_API_CALL_BUDGET_EXHAUSTED"}, "response": []}, clock
        if discovery_state(self.runtime_clock() if self.runtime_clock else clock) == "NIGHT_DISCOVERY_PAUSED":
            self.calls.append({"endpoint": endpoint, "query": query, "cache": "NIGHT_DISCOVERY_PAUSED",
                               "actual_calls": 0, "result_count": 0})
            return {"errors": {"request": "NIGHT_DISCOVERY_PAUSED"}, "response": []}, clock
        before = self._request_count()
        try:
            if self.adaptive_learning is not None:
                from app.adaptive_lab.quota import CATEGORY
                token = CATEGORY.set('STATUS' if endpoint=='/status' else 'PREMATCH_REVIEW' if 'fixture' in query else 'PREMATCH_DISCOVERY')
                try:
                    payload = await operation()
                finally:
                    CATEGORY.reset(token)
            else:
                payload = await operation()
        except (httpx.HTTPError, OSError, TimeoutError, json.JSONDecodeError,
                FootballRequestLimitError, FootballQuotaError) as exc:
            # The client owns bounded retries. Never log exception text or cache
            # failure as fresh data; pending reviews must still receive evidence.
            code = ("ODDS_QUOTA_OR_REQUEST_LIMIT" if isinstance(exc, (FootballRequestLimitError, FootballQuotaError)) else
                    "ODDS_API_TIMEOUT" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else
                    "ODDS_RESPONSE_MALFORMED" if isinstance(exc, json.JSONDecodeError) else "ODDS_API_ERROR")
            payload = {"errors": {"request": code}, "response": []}
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
                if not _persisted_context_current(snapshot, fixture, now):
                    continue
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
        terminal_keys = self.repository.terminal_review_keys()
        for fixture in fixtures:
            fixture_id, league_id = int(fixture["fixture_id"]), int(fixture["league_id"])
            adapter = adapters.get(league_id)
            matches = histories.get(league_id, ())
            pi = adapter.signal(fixture["home_team_id"], fixture["away_team_id"]) if adapter else _missing_pi(fixture)
            # Venue-specific Pi evidence is not portable to explicitly neutral games.
            if "IS_NEUTRAL_VENUE" in fixture.get("flags", ()):
                pi = _missing_pi(fixture)
            home_form = opponent_adjusted_form(fixture["home_team_id"], matches, adapter) if adapter else None
            away_form = opponent_adjusted_form(fixture["away_team_id"], matches, adapter) if adapter else None
            impacts = availability.get(fixture_id, {})
            cmi = _history_market_probabilities(fixture, matches, home_form, away_form, impacts)
            api = api_predictions.get(fixture_id)
            _, _, consensus_by_family = odds_evidence[fixture_id]
            review = final_reviews.get(fixture_id, {})
            self.analysis_evidence[fixture_id] = {
                "fixture_id": fixture_id, "league_id": league_id,
                "competition_profile": fixture.get("competition_profile", "UNKNOWN"),
                "kickoff_utc": fixture["kickoff_utc"].isoformat(), "evaluated_at_utc": now.isoformat(),
                "history_probabilities": _plain(cmi), "pi_probabilities": _plain(pi.probabilities),
                "api_probabilities": _plain(api.probabilities if api else {}),
                "persisted_model_probabilities": _plain(persisted_models.get(fixture_id, {})),
                "probability_available": bool(cmi or pi.probabilities or (api and api.probabilities)
                                              or persisted_models.get(fixture_id)),
                "state": "ANALYZED" if any(c.status == "AVAILABLE" for c in consensus_by_family.values())
                         else "WAITING_FOR_REFRESH",
                "model_generation": "LAB_V2_DETERMINISTIC_ENSEMBLE:" + policy_for(fixture.get("competition_profile", "UNKNOWN")).version,
            }
            for consensus in consensus_by_family.values():
                if consensus.status != "AVAILABLE":
                    continue
                for market, consensus_probability in consensus.fair_probabilities.items():
                    price = best_current_price(consensus, market)
                    if price is None:
                        continue
                    signals = [EnsembleSignal(
                        "CURRENT_MARKET_CONSENSUS", market, consensus_probability,
                        _market_selection(consensus.fair_probabilities, market),
                        Decimal("0.90"), "AVAILABLE", "CURRENT_API_FOOTBALL_QUOTES_ONLY",
                        "CURRENT_MARKET_CONSENSUS",
                    )]
                    model_probability = persisted_models.get(fixture_id, {}).get(market)
                    if model_probability is not None:
                        signals.append(EnsembleSignal(
                            "GOALVISION_EXPERIMENTAL_MODEL", market, model_probability,
                            None, Decimal("1.00"), "AVAILABLE", "PERSISTED_CMI_SNAPSHOT",
                            "RESULT_HISTORY_MODEL_CONTEXT",
                        ))
                    if market in pi.probabilities:
                        signals.append(EnsembleSignal(
                            "PI_RATINGS", market, pi.probabilities[market],
                            _market_selection(pi.probabilities, market),
                            Decimal("0.90") if pi.state == PiAvailability.AVAILABLE else Decimal("0.50"),
                            pi.state.value, "SAME_LEAGUE_MATCH_RESULTS_AND_GOALS_ONLY",
                            "RESULT_HISTORY_MODEL_CONTEXT",
                        ))
                    if api and market in api.probabilities:
                        signals.append(EnsembleSignal(
                            "API_FOOTBALL_PREDICTION", market, api.probabilities[market],
                            _market_selection(api.probabilities, market), Decimal("0.75"),
                            "AVAILABLE", f"CURRENT_/PREDICTIONS:{api.normalization_version}:{api.source_fingerprint}", "API_FOOTBALL_PREDICTION",
                        ))
                    if market in cmi:
                        signals.append(EnsembleSignal(
                            "CURRENT_MATCH_INTELLIGENCE", market, cmi[market],
                            _market_selection(cmi, market),
                            Decimal("0.80"), "AVAILABLE", "RESULT_HISTORY_FORM_AVAILABILITY",
                            "RESULT_HISTORY_MODEL_CONTEXT",
                        ))
                    veto = _availability_veto(market, impacts)
                    profile_policy = policy_for(fixture.get("competition_profile", "UNKNOWN"))
                    missing = tuple(name for name, present in (
                        ("lineup", review.get("lineup_status") == "CONFIRMED"),
                        ("injuries", review.get("injuries_status") in {"REFRESHED", "AVAILABLE"}),
                        ("advanced_stats", False),
                        ("standings", False),
                        ("recent_form", bool(cmi)),
                        ("competition_state", not any(flag in fixture.get("flags", ()) for flag in ("IS_SECOND_LEG", "IS_KNOCKOUT"))),
                    ) if not present)
                    decision, profile_evidence = evaluate_profile(
                        market, price.decimal_odds, signals, profile_policy, missing, contradiction=veto)
                    adaptive_provenance = {}
                    if self.adaptive_learning is not None:
                        adapted, adaptive_provenance = self.adaptive_learning.prematch_signals(
                            signals, decision, profile_evidence, fixture, market, price.decimal_odds,
                            now=now, quote_fingerprint=price.provenance_fingerprint, missing=missing, contradiction=veto)
                        if adaptive_provenance:
                            decision, profile_evidence = evaluate_profile(
                                market, price.decimal_odds, adapted, profile_policy, missing, contradiction=veto)

                    if (fixture_id, market) in terminal_keys:
                        decision = replace(decision, decision='REJECTED', rejection_reasons=('MARKET_REVIEW_TERMINAL',))
                        profile_evidence.update(hard_failures=['MARKET_REVIEW_TERMINAL'], candidate_lane='REJECTED')
                    if review.get("status") == "FIXTURE_INVALID":
                        reason = str(review.get("reason") or "FIXTURE_STATUS_NOT_UPCOMING")
                        decision = replace(decision, decision="REJECTED", rejection_reasons=(reason,))
                        profile_evidence["hard_failures"] = [reason]
                        profile_evidence["candidate_lane"] = "REJECTED"
                    from app.current_odds_forward_test.freshness import API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS
                    if (now - price.provider_origin_timestamp_utc).total_seconds() > API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS:
                        decision, profile_evidence = evaluate_profile(
                            market, None, signals, profile_policy, missing, contradiction=veto)
                        profile_evidence.update(waiting_for_refresh=True)
                    stage, readiness_reasons = _readiness(decision, fixture, now, review)
                    if profile_evidence["candidate_lane"] == "TRACKING" and stage not in {"REJECTED", "RESULT_TRACKING"}:
                        stage, readiness_reasons = "TRACKING", ("QUALITY_RISK_TRACKING",)
                    independent_probability = profile_evidence['predictive_family_count'] >= 1
                    requirements = signal_requirements(missing, fixture['capability'], independent_probability=independent_probability)
                    material = {
                        **profile_evidence,
                        "signal_requirements": requirements,
                        "independent_probability_available": independent_probability,
                        "probability_kind": "INDEPENDENT_SINGLE_MODEL" if profile_evidence["predictive_family_count"] == 1 else "MARKET_INCLUSIVE_UNCALIBRATED_ENSEMBLE",
                        "offered_implied_probability": str(decision.offered_implied_probability) if decision.offered_implied_probability is not None else None,
                        "calculated_fair_odds": str(Decimal(1) / decision.ensemble_probability) if decision.ensemble_probability is not None and decision.ensemble_probability > 0 else None,
                        "vig_method": "PER_BOOKMAKER_MULTIPLICATIVE_NORMALIZATION",
                        "market_fair_probability": str(consensus.fair_probabilities[market]),
                        "optional_data_reasons": [
                            *sorted({r["reason_code"] for r in requirements if r["gate_type"] == "SOFT"}),
                            *( ["LINEUPS_NOT_SUPPORTED_BY_PROVIDER" if not fixture["capability"].lineups else "LINEUPS_NOT_YET_AVAILABLE"] if "lineup" in missing else []),
                            *( ["INSUFFICIENT_RECENT_MATCHES"] if "recent_form" in missing else []),
                            *( ["ADVANCED_STATISTICS_UNAVAILABLE"] if "advanced_stats" in missing else []),
                            "CALIBRATION_UNAVAILABLE",
                        ],
                        "market_preference_rank": next((i for i, family in enumerate(profile_policy.market_preference)
                            if market in MARKET_FAMILIES[family]), len(profile_policy.market_preference)),
                        **{key: fixture.get(key) for key in ("competition_profile", "classifier_version",
                            "classification_reason", "classification_fingerprint", "flags", "age_category", "country", "provider_metadata")},
                        "model_generation": self.analysis_evidence[fixture_id]["model_generation"],
                        "policy": decision.policy, "fixture_id": fixture_id,
                        "readiness_policy": READINESS_POLICY_VERSION,
                        "league_id": league_id, "league": fixture["league_name"], "season": fixture["season"],
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
                        "expected_value": (
                            str(decision.ensemble_probability * price.decimal_odds - Decimal(1))
                            if decision.ensemble_probability is not None and not profile_evidence.get("waiting_for_refresh") else None
                        ),
                        "market_context_edge": str(decision.edge) if decision.edge is not None else None,
                        "weighted_agreement": str(decision.weighted_agreement) if decision.weighted_agreement is not None else None,
                        "stage": stage,
                        "readiness_lane": profile_evidence["candidate_lane"] + "_READY" if stage == "READY_TO_PUBLISH" else None,
                        "readiness_reasons": list(readiness_reasons),
                        "final_review_completed_at_utc": review.get("reviewed_at_utc") if stage == "READY_TO_PUBLISH" else None,
                        "approval_reasons": list(decision.approval_reasons),
                        "rejection_reasons": list(decision.rejection_reasons),
                        "signals": [_plain(asdict(item)) for item in decision.signals],
                        "pi": _plain(asdict(pi)), "api_prediction_available": bool(api and api.available),
                        "api_prediction_normalization": _plain(asdict(api)) if api else None,
                        "market_consensus_bookmakers": consensus.bookmaker_count,
                        "market_consensus_dispersion": _plain(consensus.dispersion),
                        "availability_impact": _plain({key: asdict(value) for key, value in impacts.items()}),
                        "final_review": _plain(review), "historical_bookmaker_odds_used": False,
                        "publication_blocker": publication_blocker(now,[fixture['kickoff_utc']]),
                    }
                    material.update(adaptive_provenance)
                    material["candidate_id"] = "lab-v2-candidate-" + fingerprint(material)
                    values.append(material)
        return sorted(values, key=lambda item: (item["fixture_id"], item["market"]))


def _discovery_dates(now: datetime, horizon_days: int) -> list[str]:
    """Return UTC provider dates, independent of the VPS local timezone."""
    clock = _utc(now)
    return [(clock.date() + timedelta(days=offset)).isoformat() for offset in range(horizon_days)]


def _fixture_rows(payload: object, capabilities: LeagueCapabilityCache, now: datetime) -> list[dict[str, object]]:
    return _fixture_rows_with_evidence(payload, capabilities, now)[0]


def _fixture_rows_with_evidence(
    payload: object, capabilities: LeagueCapabilityCache, now: datetime,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    result: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
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
            capability = capability or fallback_capability(league)
            classification = classify(league, teams, fixture, capability)
            fixture_id = int(fixture["id"])
            if fixture_id <= 0 or league_id <= 0 or season <= 0:
                raise ValueError("INVALID_PROVIDER_IDENTITY")
            if int(home["id"]) <= 0 or int(away["id"]) <= 0 or int(home["id"]) == int(away["id"]):
                raise ValueError("CONTRADICTORY_TEAM_IDENTITY")
            result.append({
                **classification.document(), "country": str(league.get("country") or capability.country),
                "provider_metadata": {"league": league, "fixture": fixture, "teams": teams},
                "fixture_id": fixture_id, "kickoff_utc": kickoff,
                "prematch_eligible": kickoff > now and status.get("short") in {"NS", "TBD"},
                "league_id": league_id, "league_name": str(league.get("name") or capability.competition_name),
                "season": season, "home_team_id": int(home["id"]), "away_team_id": int(away["id"]),
                "home_team": str(home.get("name") or home["id"]), "away_team": str(away.get("name") or away["id"]),
                "capability_tier": capability.tier, "capability": capability,
            })
        except (KeyError, TypeError, ValueError):
            excluded.append({"fixture_id": _safe_int(fixture.get("id"), -1),
                             "kickoff_utc": str(fixture.get("date") or ""),
                             "league_id": league.get("id"), "country": league.get("country", "UNKNOWN"),
                             "competition_profile": "UNKNOWN", "status": "REJECTED",
                             "reason": "FIXTURE_IDENTITY_OR_DATE_INVALID", "row_fingerprint": fingerprint(row)})
    return result, excluded


def _fixture_coverage(
    fixtures: list[dict[str, object]], candidates: list[dict[str, object]],
    odds_statuses: dict[str, str], exclusions: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_fixture: dict[int, list[dict[str, object]]] = {}
    for candidate in candidates:
        by_fixture.setdefault(int(candidate["fixture_id"]), []).append(candidate)
    result = [dict(item) for item in exclusions]
    for fixture in fixtures:
        fixture_id = int(fixture["fixture_id"])
        fixture_candidates = by_fixture.get(fixture_id, [])
        odds_status = odds_statuses.get(str(fixture_id), "FIXTURE_DISCOVERED_NO_CURRENT_ODDS")
        if odds_status != "FIXTURE_DISCOVERED_WITH_CURRENT_ODDS" and not fixture_candidates:
            status = odds_status
            reason = odds_status
        elif any(item["stage"] == "READY_TO_PUBLISH" for item in fixture_candidates):
            status, reason = "FIXTURE_READY", "FINAL_REVIEW_COMPLETE"
        elif any(item["stage"] == "FINAL_REVIEW_REQUIRED" for item in fixture_candidates):
            status, reason = "FIXTURE_FINAL_REVIEW", "FINAL_REVIEW_BLOCKED_OR_PENDING"
        elif any(item["stage"] == "EARLY_CANDIDATE" for item in fixture_candidates):
            status, reason = "FIXTURE_EVALUATED_EARLY", "FINAL_REVIEW_WINDOW_NOT_OPEN"
        elif fixture_candidates and all(
            "INSUFFICIENT_INDEPENDENT_SIGNALS" in item["rejection_reasons"]
            for item in fixture_candidates
        ):
            status, reason = (
                "FIXTURE_DISCOVERED_NO_REQUIRED_MODEL_CONTEXT",
                "INSUFFICIENT_INDEPENDENT_SIGNALS",
            )
        else:
            status, reason = "FIXTURE_EVALUATED_REJECTED", (
                "NO_SUPPORTED_NORMALIZED_MARKET" if not fixture_candidates else
                ";".join(sorted({r for c in fixture_candidates for r in c["rejection_reasons"]}))
            )
        result.append({
            "fixture_id": fixture_id,
            "kickoff_utc": fixture["kickoff_utc"].isoformat(),
            "league_id": fixture["league_id"],
            "home_team": fixture["home_team"],
            "away_team": fixture["away_team"],
            "capability_tier": fixture["capability_tier"].value,
            "status": status,
            "reason": reason,
            "markets_evaluated": len(fixture_candidates),
        })
    unique = {(item.get("fixture_id"), item.get("kickoff_utc")): item for item in result}
    return sorted(unique.values(), key=lambda item: (item.get("kickoff_utc", ""), item.get("fixture_id", -1)))


def _one_x_two_diagnostics(candidates: list[dict[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for market in MARKET_FAMILIES["1X2"]:
        rows = [item for item in candidates if item.get("market") == market]
        result[market] = {
            "evaluated": len(rows),
            "approved": sum(item.get("decision") == "APPROVED" for item in rows),
            "ensemble_probability": _distribution(item.get("ensemble_probability") for item in rows),
            "implied_probability": _distribution(
                Decimal(1) / Decimal(str(item["offered_odds"]))
                for item in rows if item.get("offered_odds") is not None
            ),
            "edge": _distribution(item.get("edge") for item in rows),
            "rejection_reasons": _counts(
                reason for item in rows for reason in item.get("rejection_reasons", ())
            ),
            "capability_tiers": _counts(item.get("capability_tier", "UNKNOWN") for item in rows),
            "signal_availability": _counts(
                signal.get("name", "UNKNOWN")
                for item in rows for signal in item.get("signals", ())
                if signal.get("availability") in {"AVAILABLE", "LOW_SAMPLE"}
            ),
        }
    return result


def _distribution(values) -> dict[str, str | int | None]:
    parsed = sorted(
        Decimal(str(value)) for value in values
        if value is not None and Decimal(str(value)).is_finite()
    )
    if not parsed:
        return {"count": 0, "mean": None, "median": None}
    middle = len(parsed) // 2
    median = parsed[middle] if len(parsed) % 2 else (parsed[middle - 1] + parsed[middle]) / Decimal(2)
    return {
        "count": len(parsed),
        "mean": str(sum(parsed, Decimal(0)) / Decimal(len(parsed))),
        "median": str(median),
    }


def _history_market_probabilities(fixture, matches, home_form, away_form, impacts) -> dict[str, Decimal]:
    home_id, away_id = int(fixture["home_team_id"]), int(fixture["away_team_id"])
    home_rates = _team_goal_rates(home_id, matches, home_venue=None if "IS_NEUTRAL_VENUE" in fixture.get("flags", ()) else True, policy=policy_for(fixture.get("competition_profile", "UNKNOWN")))
    away_rates = _team_goal_rates(away_id, matches, home_venue=None if "IS_NEUTRAL_VENUE" in fixture.get("flags", ()) else False, policy=policy_for(fixture.get("competition_profile", "UNKNOWN")))
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


def _team_goal_rates(team_id: int, matches: tuple[MatchResult, ...], *, home_venue: bool | None, policy=None) -> tuple[Decimal, Decimal] | None:
    selected = []
    dates = []
    for match in sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id), reverse=True):
        is_home = match.home_team_id == team_id
        is_away = match.away_team_id == team_id
        if not (is_home or is_away) or (home_venue is True and not is_home) or (home_venue is False and not is_away):
            continue
        dates.append(match.kickoff_utc)
        selected.append((match.home_goals, match.away_goals) if is_home else (match.away_goals, match.home_goals))
        if len(selected) == 8:
            break
    if len(selected) < 3:
        return None
    weights = [(Decimal(2) ** (-Decimal(str((dates[0] - date).total_seconds() / 86400)) / Decimal(policy.half_life_days)))
               for date in dates] if policy else [Decimal(len(selected) - index) for index in range(len(selected))]
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


def _persisted_context_current(snapshot: object, fixture: dict, now: datetime) -> bool:
    """A stored FRESH label is not proof that predictive context is still current."""
    fields = {item.name: item.value for item in snapshot.fields}
    if (str(snapshot.fixture_id) != str(fixture['fixture_id'])
            or snapshot.kickoff_utc != fixture['kickoff_utc']
            or not snapshot.evaluated_at <= now < snapshot.kickoff_utc
            or any(str(fields.get(side + '.team_id')) != str(fixture[side + '_team_id'])
                   for side in ('home', 'away'))):
        return False
    freshness = {item.signal: item for item in snapshot.freshness}
    # These are inputs of the persisted probability model. Current odds are
    # independently acquired/validated by V2 and are not reused from this snapshot.
    for name in ('fixture_context', 'team_statistics', 'team_history', 'injuries'):
        item = freshness.get(name)
        if (item is None or item.status.value != 'FRESH' or item.expires_at is None
                or item.newest_retrieved_at is None
                or not item.newest_retrieved_at <= snapshot.evaluated_at <= now <= item.expires_at):
            return False
    return all(p.retrieved_at <= snapshot.evaluated_at
               and (p.provider_timestamp is None or p.provider_timestamp <= snapshot.evaluated_at)
               for field in snapshot.fields for p in field.provenance)


def _readiness(
    decision: EnsembleDecision,
    fixture: dict,
    now: datetime,
    review: dict[str, object],
) -> tuple[str, tuple[str, ...]]:
    if fixture["kickoff_utc"] <= now or review.get("status") == "PREMATCH_CLOSED" or not fixture.get("prematch_eligible", True):
        return "RESULT_TRACKING", ("PREMATCH_PUBLICATION_CLOSED",)
    if review.get("status") == "FIXTURE_INVALID":
        return "REJECTED", (str(review.get("reason") or "FIXTURE_STATUS_NOT_UPCOMING"),)
    if decision.decision == "TRACKING":
        return "TRACKING", ("WAITING_FOR_REFRESH",)
    if decision.decision != "APPROVED":
        return "REJECTED", ("ENSEMBLE_NOT_APPROVED",)
    remaining = fixture["kickoff_utc"] - now
    if remaining <= MINIMUM_KICKOFF_LEAD:
        return "TRACKING", ("MINIMUM_KICKOFF_LEAD_NOT_MET",)
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
    if "competition_profile" not in fixture and decision.market in LINEUP_SENSITIVE_MARKETS:
        if capability.lineups and review.get("lineup_status") != "CONFIRMED":
            blockers.append("CONFIRMED_LINEUPS_REQUIRED_FOR_MARKET")
        if capability.injuries and review.get("injuries_status") != "REFRESHED":
            blockers.append("CURRENT_INJURIES_REQUIRED_FOR_MARKET")
    if "competition_profile" not in fixture and capability.tier == CapabilityTier.TIER_C_BASIC and (
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
    near = sorted((item for item in fixtures
                   if MINIMUM_KICKOFF_LEAD < item["kickoff_utc"] - now <= FINAL_REVIEW_WINDOW
                   and publication_blocker(now,[item['kickoff_utc']]) is None),
                  key=lambda item: (item["kickoff_utc"], item.get("fixture_id", -1)))
    total = 0
    for item in near[:FINAL_REVIEW_SHORTLIST_SIZE]:
        capability = item.get("capability")
        logical_calls = 2 + int(bool(getattr(capability, "lineups", True))) + int(
            bool(getattr(capability, "injuries", True))
        )
        total += logical_calls * MAX_PROVIDER_ATTEMPTS_PER_CALL
    return total


def _shortlist(candidates: list[dict[str, object]], *, maximum: int) -> list[int]:
    ordered = sorted(candidates, key=lambda item: (
        item["decision"] != "APPROVED", item["stage"] != "FINAL_REVIEW_REQUIRED",
        item["kickoff_utc"], item.get("market_preference_rank", 0), -Decimal(str(item.get("edge") or "-99")),
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
    remaining = sorted(candidates, key=lambda item: (
        -Decimal(str(item.get("edge") or "-99")), item["candidate_id"],
    ))
    while len(values) < 3:
        choices = []
        for group in combinations(remaining, 3):
            if len({item["fixture_id"] for item in group}) != 3:
                continue
            teams = [item[key] for item in group for key in ("home_team_id", "away_team_id")]
            if len(set(teams)) != 6:
                continue
            rank = (
                -min(Decimal(str(item["edge"])) for item in group),
                -sum((Decimal(str(item["edge"])) for item in group), Decimal(0)),
                tuple(item["candidate_id"] for item in group),
            )
            choices.append((rank, group))
        if not choices:
            break
        _, group = min(choices, key=lambda item: item[0])
        combined = Decimal(1)
        for item in group:
            combined *= Decimal(item["offered_odds"])
        values.append({"legs": [item["candidate_id"] for item in group], "combined_odds": str(combined),
                       "correlation_review": "PASSED_DISTINCT_FIXTURES_AND_TEAMS"})
        fixtures = {item["fixture_id"] for item in group}
        teams = {item[key] for item in group for key in ("home_team_id", "away_team_id")}
        remaining = [item for item in remaining
                     if item["fixture_id"] not in fixtures
                     and not teams.intersection({item["home_team_id"], item["away_team_id"]})]
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


def _refreshed_fixture_kickoff(
    payload: object, fixture_id: int, now: datetime,
) -> datetime | None:
    rows = _response_rows(payload)
    if len(rows) != 1 or not _provider_payload_succeeded(payload):
        return None
    fixture = rows[0].get("fixture") if isinstance(rows[0].get("fixture"), dict) else {}
    status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
    try:
        kickoff = _utc(datetime.fromisoformat(str(fixture["date"]).replace("Z", "+00:00")))
        return kickoff if (
            int(fixture["id"]) == fixture_id
            and status.get("short") in {"NS", "TBD"}
            and kickoff > now
        ) else None
    except (KeyError, TypeError, ValueError):
        return None


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
    return "AGREEMENT" if _market_selection(probabilities, market) == market else "DISAGREEMENT"


def _market_selection(probabilities: dict[str, Decimal], market: str) -> str | None:
    family = next((outcomes for outcomes in MARKET_FAMILIES.values() if market in outcomes), ())
    available = {key: probabilities[key] for key in family if key in probabilities}
    return max(available, key=available.get) if available else None


def _odds_band(odds: Decimal) -> str:
    if odds < Decimal("1.70"): return "BELOW_1.70"
    if odds < Decimal("2.00"): return "1.70-1.99"
    if odds < Decimal("2.50"): return "2.00-2.49"
    if odds < Decimal("3.50"): return "2.50-3.49"
    return "3.50+"


def _response_rows(payload: object) -> list[dict]:
    rows = payload.get("response") if isinstance(payload, dict) else payload if isinstance(payload, list) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _provider_payload_succeeded(payload: object) -> bool:
    return isinstance(payload, dict) and not payload.get("errors") and isinstance(payload.get("response"), list)


def _has_raw_bookmaker_values(row: dict[str, object]) -> bool:
    books = row.get("bookmakers") if isinstance(row.get("bookmakers"), list) else ()
    return any(
        isinstance(raw, dict) and raw.get("odd") not in (None, "")
        for book in books if isinstance(book, dict)
        for bet in (book.get("bets") if isinstance(book.get("bets"), list) else ()) if isinstance(bet, dict)
        for raw in (bet.get("values") if isinstance(bet.get("values"), list) else ())
    )


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


def night_report(now: datetime) -> dict[str, object]:
    """Network-free status shared by CLI and direct runner entrypoints."""
    return {"schema_version": SCHEMA_VERSION, "status": "NIGHT_DISCOVERY_PAUSED",
            "discovery_state": "NIGHT_DISCOVERY_PAUSED", "mode": "LAB_V2_NO_SEND",
            "analysis_mode": "LAB_V2_NO_SEND", "evaluated_at_utc": now.isoformat(),
            "api_calls_consumed": 0, "candidate_markets": [], "fixtures_discovered": 0,
            "ready_candidate_count": 0, "telegram_sends": 0, "official_mutations": 0,
            "historical_bookmaker_odds_used": False, "throughput": {},
            "competition_profile_counts": {}, "global_state_counts": {},
            "throughput_warnings": [], "publication_requested": False,
            "publication_enabled": False, "publication_attempt_count": 0,
            "telegram_transport_constructed": False}
