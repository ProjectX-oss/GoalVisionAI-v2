"""One bounded current/upcoming LAB_V2_SHADOW rehearsal with zero delivery path."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import combinations
import json
from pathlib import Path
import re
import sqlite3

from app.current_match_intelligence.serialization import snapshot_from_document
from app.lab_combo.experimental import evaluate_snapshot
from app.real_match_lab_analysis.fingerprint import fingerprint

from .api_prediction import ApiPredictionSignal, normalize_api_prediction
from .capability import CapabilityTier, LeagueCapability, LeagueCapabilityCache
from .context_signals import AvailabilityImpact, availability_impact, opponent_adjusted_form
from .ensemble import EnsembleDecision, EnsembleSignal, evaluate_ensemble
from .market_consensus import CurrentMarketConsensus, best_current_price, current_market_consensus
from .pi_ratings import MatchResult, PiAvailability, PiRatingAdapter, PiSignal, parse_api_fixture_results
from .repository import ShadowEvidenceRepository


SCHEMA_VERSION = "goalvision-lab-v2-shadow-rehearsal-v1"
MAXIMUM_CALLS = 40
EXCLUDED = re.compile(r"(?i)(\byouth\b|\bu[- ]?\d{2}\b|\breserves?\b|\bacademy\b|\bvirtual\b|\besports?\b|\bfriendly\b)")
TIER_ORDER = {CapabilityTier.TIER_A_FULL: 0, CapabilityTier.TIER_B_GOOD: 1, CapabilityTier.TIER_C_BASIC: 2}


class LabV2ShadowRunner:
    """A separate shadow runner. It has no Telegram dependency or send method."""

    def __init__(
        self,
        client: object,
        repository: ShadowEvidenceRepository,
        *,
        capability_cache_path: Path,
        analysis_path: Path | None = None,
        maximum_calls: int = MAXIMUM_CALLS,
    ) -> None:
        if not 1 <= maximum_calls <= MAXIMUM_CALLS:
            raise ValueError("LAB_V2_SHADOW_RETAINS_40_CALL_CEILING")
        self.client, self.repository = client, repository
        self.capability_cache_path = capability_cache_path
        self.analysis_path = analysis_path
        self.maximum_calls = maximum_calls
        self.calls: list[dict[str, object]] = []
        restrict = getattr(client, "restrict_requests", None)
        if restrict:
            restrict(maximum_calls, daily_reserve=20)

    async def run(self, *, now: datetime, horizon_days: int = 3) -> dict[str, object]:
        clock = _utc(now)
        if not 1 <= horizon_days <= 7:
            raise ValueError("LAB_V2_SHADOW_HORIZON_OUTSIDE_1_TO_7_DAYS")
        await self._fetch("/status", {}, lambda: self.client.account_status(), clock=clock, ttl=None)
        capabilities, cache_status = await self._capabilities(clock)
        fixtures: dict[int, dict[str, object]] = {}
        for offset in range(horizon_days):
            day = (clock.date() + timedelta(days=offset)).isoformat()
            payload, _ = await self._fetch(
                "/fixtures", {"date": day, "timezone": "UTC"},
                lambda value=day: self.client.fixtures_by_date(value, timezone_name="UTC"),
                clock=clock, ttl=timedelta(minutes=5), use_cache=False,
            )
            for item in _fixture_rows(payload, capabilities, clock):
                fixtures[int(item["fixture_id"])] = item
        ordered = sorted(fixtures.values(), key=lambda item: (
            TIER_ORDER[item["capability_tier"]], item["kickoff_utc"], item["fixture_id"],
        ))
        tier_distribution = _counts(item["capability_tier"].value for item in ordered)
        league_distribution = _counts(f"{item['league_id']}:{item['league_name']}" for item in ordered)

        odds_evidence: dict[int, tuple[object, datetime, dict[str, CurrentMarketConsensus]]] = {}
        odds_probe_limit = min(16, len(ordered))
        for fixture in ordered[:odds_probe_limit]:
            if len(odds_evidence) >= 10 or self._remaining() <= 14:
                break
            payload, retrieved = await self._fetch(
                "/odds", {"fixture": fixture["fixture_id"]},
                lambda identity=fixture["fixture_id"]: self.client.current_odds(identity),
                clock=clock, ttl=timedelta(minutes=15), use_cache=False,
            )
            consensus = current_market_consensus(
                payload, fixture_id=fixture["fixture_id"], retrieved_at=retrieved, now=retrieved,
            )
            if any(value.quote_count for value in consensus.values()):
                odds_evidence[fixture["fixture_id"]] = (payload, retrieved, consensus)

        odds_fixtures = [item for item in ordered if item["fixture_id"] in odds_evidence]
        league_histories: dict[int, tuple[MatchResult, ...]] = {}
        pi_adapters: dict[int, PiRatingAdapter] = {}
        history_calls = 0
        for league_id in dict.fromkeys(int(item["league_id"]) for item in odds_fixtures):
            if history_calls >= 6 or self._remaining() <= 8:
                break
            targets = [item for item in odds_fixtures if item["league_id"] == league_id]
            season = int(targets[0]["season"])
            payload, _ = await self._fetch(
                "/fixtures", {"league": league_id, "season": season, "status": "FT", "last": 99},
                lambda lid=league_id, value=season: self.client.finished_matches(lid, value, last=99),
                clock=clock, ttl=timedelta(hours=6),
            )
            history_calls += 1
            matches = list(parse_api_fixture_results((payload,)))
            adapter = PiRatingAdapter(league_id); adapter.replay(matches, before=clock)
            if (any(adapter.signal(item["home_team_id"], item["away_team_id"]).state
                    in {PiAvailability.INSUFFICIENT, PiAvailability.UNAVAILABLE} for item in targets)
                    and history_calls < 6 and self._remaining() > 9 and season > 1):
                previous, _ = await self._fetch(
                    "/fixtures", {"league": league_id, "season": season - 1, "status": "FT", "last": 99},
                    lambda lid=league_id, value=season - 1: self.client.finished_matches(lid, value, last=99),
                    clock=clock, ttl=timedelta(days=1),
                )
                history_calls += 1
                matches = list(parse_api_fixture_results((previous, payload)))
                adapter = PiRatingAdapter(league_id); adapter.replay(matches, before=clock)
            league_histories[league_id] = tuple(matches)
            pi_adapters[league_id] = adapter

        api_predictions: dict[int, ApiPredictionSignal] = {}
        for fixture in odds_fixtures:
            capability: LeagueCapability = fixture["capability"]
            if not capability.predictions or len(api_predictions) >= 5 or self._remaining() <= 5:
                continue
            payload, _ = await self._fetch(
                "/predictions", {"fixture": fixture["fixture_id"]},
                lambda identity=fixture["fixture_id"]: self._raw("/predictions", {"fixture": identity}),
                clock=clock, ttl=timedelta(hours=1),
            )
            api_predictions[fixture["fixture_id"]] = normalize_api_prediction(payload, fixture_id=fixture["fixture_id"])

        persisted_models, v1_keys = self._persisted_v1(odds_fixtures, clock)
        preliminary = self._evaluate(
            odds_fixtures, odds_evidence, league_histories, pi_adapters,
            api_predictions, persisted_models, {}, clock,
        )
        shortlist_ids = []
        for item in sorted(preliminary, key=lambda value: (
            value["decision"] != "APPROVED", -Decimal(value.get("edge") or "-99"), value["fixture_id"], value["market"],
        )):
            if item["fixture_id"] not in shortlist_ids:
                shortlist_ids.append(item["fixture_id"])
            if len(shortlist_ids) == 2:
                break
        availability: dict[int, dict[str, AvailabilityImpact]] = {}
        for fixture_id in shortlist_ids:
            fixture = fixtures[fixture_id]
            capability = fixture["capability"]
            if not capability.injuries or self._remaining() <= 1:
                continue
            payload, _ = await self._fetch(
                "/injuries", {"fixture": fixture_id},
                lambda identity=fixture_id: self._raw("/injuries", {"fixture": identity}),
                clock=clock, ttl=timedelta(hours=4),
            )
            availability[fixture_id] = _availability_from_payload(payload, fixture)

        candidates = self._evaluate(
            odds_fixtures, odds_evidence, league_histories, pi_adapters,
            api_predictions, persisted_models, availability, clock,
        )
        v2_approved = [item for item in candidates if item["decision"] == "APPROVED"]
        v2_keys = {f"{item['fixture_id']}:{item['market']}" for item in v2_approved}
        ready = [item for item in v2_approved if item["stage"] == "READY_TO_PUBLISH"]
        combos = _combos(ready)
        v1_leagues = {item["league_id"] for item in odds_fixtures if item["fixture_id"] in persisted_models}
        v2_leagues = {item["league_id"] for item in odds_fixtures}
        endpoint_calls = _counts(str(item["endpoint"]) for item in self.calls for _ in range(int(item["actual_calls"])))
        report = {
            "schema_version": SCHEMA_VERSION,
            "mode": "LAB_V2_SHADOW",
            "evaluated_at_utc": clock.isoformat(),
            "fixtures_discovered": len(fixtures),
            "number_of_leagues": len({item["league_id"] for item in ordered}),
            "league_distribution": league_distribution,
            "capability_cache": cache_status,
            "capability_tier_distribution": tier_distribution,
            "fixtures_excluded_before_odds": max(0, sum(self._fixture_result_counts) - len(fixtures)),
            "fixtures_left_without_odds_probe_due_to_budget": max(0, len(ordered) - odds_probe_limit),
            "current_odds_fixtures": len(odds_fixtures),
            "pi_available_fixtures": sum(
                pi_adapters[item["league_id"]].signal(item["home_team_id"], item["away_team_id"]).state == PiAvailability.AVAILABLE
                for item in odds_fixtures if item["league_id"] in pi_adapters
            ),
            "api_prediction_available_fixtures": sum(item.available for item in api_predictions.values()),
            "v1_candidate_count": len(v1_keys),
            "v2_candidate_count": len(v2_keys),
            "v1_leagues_evaluated": len(v1_leagues),
            "v2_leagues_evaluated": len(v2_leagues),
            "league_coverage_increase": len(v2_leagues - v1_leagues),
            "overlap": sorted(v1_keys & v2_keys),
            "new_v2_candidates": sorted(v2_keys - v1_keys),
            "v1_candidates_rejected_by_v2": sorted(v1_keys - v2_keys),
            "candidate_markets": candidates,
            "ready_candidate_count": len(ready),
            "three_leg_combos": combos,
            "api_calls_consumed": self._request_count(),
            "api_call_allocation": endpoint_calls,
            "api_call_ceiling": self.maximum_calls,
            "signal_completeness": {
                "persisted_v1_model": len(persisted_models),
                "pi": len(pi_adapters), "api_prediction": sum(item.available for item in api_predictions.values()),
                "current_market_consensus": sum(any(value.status == "AVAILABLE" for value in data[2].values()) for data in odds_evidence.values()),
                "availability": len(availability),
            },
            "historical_bookmaker_odds_used": False,
            "telegram_sends": 0,
            "telegram_transport_constructed": False,
            "official_mutations": 0,
            "timers_started": 0,
        }
        identity = "lab-v2-shadow-" + fingerprint((clock, report["fixtures_discovered"], report["api_calls_consumed"]))
        for fixture_id, (_, retrieved, families) in sorted(odds_evidence.items()):
            for family, consensus in sorted(families.items()):
                document = _plain(asdict(consensus))
                document["retrieved_at_utc"] = retrieved.isoformat()
                document["source"] = "API_FOOTBALL_CURRENT_ODDS"
                document["historical_bookmaker_odds_used"] = False
                self.repository.append(
                    "market_consensus", f"{fixture_id}:{family}:{fingerprint(document)}",
                    document, created_at=clock,
                )
        for candidate in candidates:
            self.repository.append("candidate", candidate["candidate_id"], candidate, created_at=clock)
        self.repository.append("rehearsal", identity, report, created_at=clock)
        return _plain(report)

    @property
    def _fixture_result_counts(self) -> list[int]:
        return [int(item.get("result_count") or 0) for item in self.calls if item["endpoint"] == "/fixtures" and "date" in item["query"]]

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

    async def _fetch(self, endpoint: str, query: dict[str, object], operation, *, clock: datetime,
                     ttl: timedelta | None, use_cache: bool = True) -> tuple[object, datetime]:
        if ttl is not None and use_cache:
            cached = self.repository.cached(endpoint, query, now=clock)
            if cached is not None:
                self.calls.append({"endpoint": endpoint, "query": query, "cache": "HIT", "actual_calls": 0,
                                   "result_count": _result_count(cached["payload"])})
                return cached["payload"], cached["retrieved_at"]
        if self._remaining() <= 0:
            raise ValueError("LAB_V2_SHADOW_API_CALL_BUDGET_EXHAUSTED")
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

    async def _raw(self, endpoint: str, query: dict[str, object]) -> object:
        getter = getattr(self.client, "_get", None)
        if getter is None:
            method = getattr(self.client, endpoint.strip("/").replace("/", "_"), None)
            if method is None:
                raise RuntimeError("LAB_V2_PROVIDER_ENDPOINT_UNAVAILABLE")
            return await method(**query)
        response = await getter(endpoint, params=query)
        return response.json()

    def _request_count(self) -> int:
        return int(getattr(self.client, "request_count", 0))

    def _remaining(self) -> int:
        return self.maximum_calls - self._request_count()

    def _persisted_v1(self, fixtures: list[dict], now: datetime) -> tuple[dict[int, dict[str, Decimal]], set[str]]:
        if self.analysis_path is None or not self.analysis_path.is_file():
            return {}, set()
        connection = sqlite3.connect(self.analysis_path.resolve().as_uri() + "?mode=ro", uri=True)
        models, keys = {}, set()
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
                evaluated = evaluate_snapshot(snapshot, now=now)
                models[fixture["fixture_id"]] = {
                    item["market"]: Decimal(item["experimental_signal"])
                    for item in evaluated if item.get("experimental_signal") is not None
                }
                keys.update(f"{item['fixture_id']}:{item['market']}" for item in evaluated if item["decision"] == "APPROVED")
        finally:
            connection.close()
        return models, keys

    def _evaluate(
        self, fixtures, odds_evidence, histories, adapters, api_predictions,
        persisted_models, availability, now,
    ) -> list[dict[str, object]]:
        values = []
        for fixture in fixtures:
            fixture_id, league_id = fixture["fixture_id"], fixture["league_id"]
            adapter = adapters.get(league_id)
            matches = histories.get(league_id, ())
            pi = adapter.signal(fixture["home_team_id"], fixture["away_team_id"]) if adapter else _missing_pi(fixture)
            home_form = opponent_adjusted_form(fixture["home_team_id"], matches, adapter) if adapter else None
            away_form = opponent_adjusted_form(fixture["away_team_id"], matches, adapter) if adapter else None
            impacts = availability.get(fixture_id, {})
            cmi = _cmi_probabilities(home_form, away_form, impacts)
            api = api_predictions.get(fixture_id)
            _, _, consensus_by_family = odds_evidence[fixture_id]
            for family, consensus in consensus_by_family.items():
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
                        signals.append(EnsembleSignal("GOALVISION_EXPERIMENTAL_MODEL", market, model_probability,
                                                      None, Decimal("1.00"), "AVAILABLE", "PERSISTED_CMI_SNAPSHOT"))
                    if market in pi.probabilities:
                        signals.append(EnsembleSignal(
                            "PI_RATINGS", market, pi.probabilities[market],
                            max(pi.probabilities, key=pi.probabilities.get),
                            Decimal("0.90") if pi.state == PiAvailability.AVAILABLE else Decimal("0.50"),
                            pi.state.value, "MATCH_RESULTS_AND_GOALS_ONLY",
                        ))
                    if api and market in api.probabilities:
                        signals.append(EnsembleSignal(
                            "API_FOOTBALL_PREDICTION", market, api.probabilities[market],
                            max(api.probabilities, key=api.probabilities.get), Decimal("0.75"),
                            "AVAILABLE", "CURRENT_/PREDICTIONS",
                        ))
                    elif api and api.under_over:
                        probability = Decimal("0.58") if market == api.under_over else Decimal("0.42") if _same_family(market, api.under_over) else None
                        if probability is not None:
                            signals.append(EnsembleSignal("API_FOOTBALL_PREDICTION", market, probability,
                                                          api.under_over, Decimal("0.60"), "AVAILABLE", "CURRENT_/PREDICTIONS"))
                    if market in cmi:
                        signals.append(EnsembleSignal(
                            "CURRENT_MATCH_INTELLIGENCE", market, cmi[market], max(cmi, key=cmi.get),
                            Decimal("0.70"), "AVAILABLE", "OPPONENT_ADJUSTED_FORM_AND_AVAILABILITY",
                        ))
                    decision = evaluate_ensemble(market, price.decimal_odds, signals)
                    stage = _stage(decision, fixture, now)
                    material = {
                        "policy": decision.policy, "fixture_id": fixture_id,
                        "league_id": league_id, "league": fixture["league_name"],
                        "capability_tier": fixture["capability_tier"].value,
                        "home_team_id": fixture["home_team_id"], "away_team_id": fixture["away_team_id"],
                        "home_team": fixture["home_team"], "away_team": fixture["away_team"],
                        "kickoff_utc": fixture["kickoff_utc"].isoformat(), "market": market,
                        "offered_odds": str(price.decimal_odds), "bookmaker": price.bookmaker_name,
                        "quote_provenance_fingerprint": price.provenance_fingerprint,
                        "decision": decision.decision, "confidence": decision.confidence,
                        "odds_band": _odds_band(price.decimal_odds),
                        "lineup_confirmed": "NOT_CONFIRMED",
                        "pi_available": pi.state.value,
                        "api_prediction_relation": (
                            "AGREEMENT" if api and api.probabilities and max(api.probabilities, key=api.probabilities.get) == market
                            else "DISAGREEMENT" if api and api.probabilities else "UNAVAILABLE"
                        ),
                        "market_consensus_relation": (
                            "AGREEMENT" if max(consensus.fair_probabilities, key=consensus.fair_probabilities.get) == market
                            else "DISAGREEMENT"
                        ),
                        "ensemble_probability": str(decision.ensemble_probability) if decision.ensemble_probability is not None else None,
                        "edge": str(decision.edge) if decision.edge is not None else None,
                        "weighted_agreement": str(decision.weighted_agreement) if decision.weighted_agreement is not None else None,
                        "stage": stage, "approval_reasons": list(decision.approval_reasons),
                        "rejection_reasons": list(decision.rejection_reasons),
                        "signals": [_plain(asdict(item)) for item in decision.signals],
                        "pi": _plain(asdict(pi)),
                        "api_prediction_available": bool(api and api.available),
                        "market_consensus_bookmakers": consensus.bookmaker_count,
                        "market_consensus_dispersion": _plain(consensus.dispersion),
                        "availability_impact": _plain({key: asdict(value) for key, value in impacts.items()}),
                    }
                    material["candidate_id"] = "lab-v2-candidate-" + fingerprint(material)
                    values.append(material)
        return sorted(values, key=lambda item: (item["fixture_id"], item["market"]))


def _fixture_rows(payload: object, capabilities: LeagueCapabilityCache, now: datetime) -> list[dict[str, object]]:
    rows = payload.get("response") if isinstance(payload, dict) else None
    result = []
    for row in rows if isinstance(rows, list) else ():
        fixture = row.get("fixture") if isinstance(row, dict) and isinstance(row.get("fixture"), dict) else {}
        league = row.get("league") if isinstance(row, dict) and isinstance(row.get("league"), dict) else {}
        teams = row.get("teams") if isinstance(row, dict) and isinstance(row.get("teams"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
        try:
            kickoff = _utc(datetime.fromisoformat(str(fixture["date"]).replace("Z", "+00:00")))
            league_id, season = int(league["id"]), int(league["season"])
            capability = capabilities.current(league_id, season, day=now.date())
            identity = " ".join((str(league.get("name") or ""), str(home.get("name") or ""), str(away.get("name") or "")))
            if (status.get("short") not in {"NS", "TBD"} or kickoff <= now + timedelta(minutes=60)
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


def _availability_from_payload(payload: object, fixture: dict) -> dict[str, AvailabilityImpact]:
    rows = payload.get("response") if isinstance(payload, dict) else None
    grouped = {"home": [], "away": []}
    sides = {str(fixture["home_team_id"]): "home", str(fixture["away_team_id"]): "away"}
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict): continue
        team, player = row.get("team") or {}, row.get("player") or {}
        side = sides.get(str(team.get("id")))
        if side and player.get("id") is not None:
            reason = str(player.get("reason") or "")
            suspended = any(word in reason.casefold() for word in ("suspend", "red card", "yellow cards"))
            grouped[side].append({"player_id": str(player["id"]), "status": "SUSPENDED" if suspended else "INJURED"})
    return {side: availability_impact(rows) for side, rows in grouped.items()}


def _cmi_probabilities(home_form, away_form, impacts: dict[str, AvailabilityImpact]) -> dict[str, Decimal]:
    if home_form is None or away_form is None or home_form.score is None or away_form.score is None:
        return {}
    delta = home_form.score - away_form.score
    delta -= impacts.get("home", AvailabilityImpact("COUNT_FALLBACK", 0, 0, 0, Decimal(0), (), "")).impact
    delta += impacts.get("away", AvailabilityImpact("COUNT_FALLBACK", 0, 0, 0, Decimal(0), (), "")).impact
    home = max(Decimal("0.12"), min(Decimal("0.70"), Decimal("0.38") + delta * Decimal("0.45")))
    away = max(Decimal("0.12"), min(Decimal("0.70"), Decimal("0.32") - delta * Decimal("0.45")))
    draw = max(Decimal("0.16"), Decimal(1) - home - away)
    total = home + draw + away
    return {"HOME_WIN": home / total, "DRAW": draw / total, "AWAY_WIN": away / total}


def _missing_pi(fixture: dict) -> PiSignal:
    return PiSignal(PiAvailability.UNAVAILABLE, fixture["league_id"], fixture["home_team_id"], fixture["away_team_id"],
                    None, None, None, None, None, None, None, None, 0, 0, 0, 0, {})


def _stage(decision: EnsembleDecision, fixture: dict, now: datetime) -> str:
    if decision.decision != "APPROVED": return "REJECTED"
    if fixture["kickoff_utc"] - now > timedelta(minutes=60): return "EARLY"
    if fixture["capability_tier"] == CapabilityTier.TIER_A_FULL: return "FINAL_REVIEW"
    return "READY_TO_PUBLISH"


def _combos(candidates: list[dict]) -> list[dict[str, object]]:
    values = []
    for group in combinations(candidates, 3):
        if len({item["fixture_id"] for item in group}) != 3: continue
        teams = [item[key] for item in group for key in ("home_team_id", "away_team_id")]
        if len(set(teams)) != 6: continue
        combined = Decimal(1)
        for item in group: combined *= Decimal(item["offered_odds"])
        if combined >= Decimal("2.00"):
            values.append({"legs": [item["candidate_id"] for item in group], "combined_odds": str(combined)})
        if len(values) == 3: break
    return values


def _same_family(first: str, second: str) -> bool:
    return first.split("_", 1)[-1] == second.split("_", 1)[-1]


def _odds_band(odds: Decimal) -> str:
    if odds < Decimal("1.70"): return "BELOW_1.70"
    if odds < Decimal("2.00"): return "1.70-1.99"
    if odds < Decimal("2.50"): return "2.00-2.49"
    if odds < Decimal("3.50"): return "2.50-3.49"
    return "3.50+"


def _result_count(payload: object) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("results"), int): return payload["results"]
    if isinstance(payload, dict) and isinstance(payload.get("response"), list): return len(payload["response"])
    if isinstance(payload, list): return len(payload)
    return 0


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


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None: raise ValueError("LAB_V2_TIME_REQUIRES_OFFSET")
    return value.astimezone(timezone.utc)
