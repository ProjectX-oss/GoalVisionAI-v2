from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.lab_telegram.models import LabTelegramConfig
from app.lab_v2_shadow.api_prediction import normalize_api_prediction
from app.lab_v2_shadow.capability import CapabilityTier, LeagueCapabilityCache
from app.lab_v2_shadow.context_signals import PlayerUsage, availability_impact, opponent_adjusted_form
from app.lab_v2_shadow.ensemble import EnsembleSignal, evaluate_ensemble
from app.lab_v2_shadow.market_consensus import current_market_consensus
from app.lab_v2_shadow.bookmakers import review_bookmaker_catalogue
from app.lab_v2_shadow.publication import prepare_v2_publications, v2_single_message
from app.lab_v2_shadow.quota import (
    DAILY_SAFETY_RESERVE, MAX_DISCOVERY_CALLS_PER_CYCLE,
    adaptive_quota_budget, projected_daily_usage,
)
from app.lab_v2_shadow.pi_ratings import MatchResult, PiAvailability, PiRatingAdapter, parse_api_fixture_results
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.runner import LabV2ShadowRunner
from app.lab_v2_shadow.runner import _stage
from app.lab_v2_shadow.segmentation import segment_results
from app.real_match_lab_analysis.models import LAB_BOT_USERNAME, LAB_CHAT_ID


NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


def coverage(*, league_id=999, full=False, predictions=True, standings=False):
    fixture = {"events": True, "lineups": full, "statistics_fixtures": full, "statistics_players": full}
    return {"league": {"id": league_id, "name": "Worldwide League", "type": "League"},
            "country": {"name": "Elsewhere"}, "seasons": [{"year": 2026, "current": True,
            "start": "2026-01-01", "end": "2026-12-31", "coverage": {
                "fixtures": fixture, "standings": standings, "injuries": full,
                "predictions": predictions, "odds": True}}]}


def test_league_capability_tiers_and_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = {"response": [coverage(league_id=1, full=True), coverage(league_id=2), coverage(league_id=4, standings=True),
                            {**coverage(league_id=3), "league": {"id": 3, "name": "No odds", "type": "League"}}]}
    payload["response"][3]["seasons"][0]["coverage"]["odds"] = False
    cache = LeagueCapabilityCache.from_api_payload(payload, retrieved_at=NOW)
    assert cache.current(1, 2026, day=NOW.date()).tier is CapabilityTier.TIER_A_FULL
    assert cache.current(2, 2026, day=NOW.date()).tier is CapabilityTier.TIER_C_BASIC
    assert cache.current(4, 2026, day=NOW.date()).tier is CapabilityTier.TIER_B_GOOD
    assert cache.current(3, 2026, day=NOW.date()).tier is CapabilityTier.UNSUPPORTED
    path = Path("var/capabilities.json"); cache.save(path)
    assert LeagueCapabilityCache.load(path, now=NOW + timedelta(days=1)).content_fingerprint == cache.content_fingerprint


def test_non_major_league_is_not_restricted():
    cache = LeagueCapabilityCache.from_api_payload({"response": [coverage(league_id=9876)]}, retrieved_at=NOW)
    record = cache.current(9876, 2026, day=NOW.date())
    assert record is not None and record.tier is CapabilityTier.TIER_C_BASIC
    assert "major" not in " ".join(record.reasons).lower()


def results() -> tuple[MatchResult, ...]:
    rows = []
    for index in range(10):
        rows.append(MatchResult(999, 2026, index + 1, NOW - timedelta(days=20-index),
                                10 if index % 2 == 0 else 30,
                                20 if index % 2 == 0 else 10,
                                3 if index % 2 == 0 else 0, 0 if index % 2 == 0 else 1))
        rows.append(MatchResult(999, 2026, index + 101, NOW - timedelta(days=20-index, hours=1),
                                40 if index % 2 == 0 else 20,
                                20 if index % 2 == 0 else 50,
                                2 if index % 2 == 0 else 1, 0))
    return tuple(rows)


def test_pi_deterministic_replay_and_home_away_behavior():
    first, second = PiRatingAdapter(999), PiRatingAdapter(999)
    first.replay(results()); second.replay(reversed(results()))
    assert first.signal(10, 20) == second.signal(10, 20)
    signal = first.signal(10, 20)
    assert signal.state is PiAvailability.AVAILABLE
    assert signal.home_team_home_strength != signal.home_team_away_strength
    assert signal.rating_difference == signal.home_team_home_strength - signal.away_team_away_strength


def test_pi_insufficient_history_is_not_high_confidence():
    pi = PiRatingAdapter(999); pi.replay(results()[:2])
    assert pi.signal(10, 20).state in {PiAvailability.INSUFFICIENT, PiAvailability.UNAVAILABLE}
    assert not pi.signal(10, 20).probabilities


def test_pi_result_parser_ignores_odds_and_rejects_cross_league():
    payload = {"response": [{"fixture": {"id": 1, "date": NOW.isoformat(), "status": {"short": "FT"}},
               "league": {"id": 999, "season": 2026}, "teams": {"home": {"id": 10}, "away": {"id": 20}},
               "goals": {"home": 2, "away": 0}, "bookmaker_odds": {"home": 1.1}}]}
    matches = parse_api_fixture_results((payload,))
    assert len(matches) == 1 and not hasattr(matches[0], "odds")
    with pytest.raises(ValueError, match="CROSS_LEAGUE"):
        PiRatingAdapter(1).update(matches[0])


def test_no_historical_odds_dependency():
    import app.lab_v2_shadow.pi_ratings as pi_module
    import app.lab_v2_shadow.runner as runner_module
    source = (inspect.getsource(pi_module) + inspect.getsource(runner_module)).lower()
    assert "historical_odds" not in source
    assert "bookmaker_odds" not in inspect.getsource(pi_module)


def test_api_football_prediction_normalization():
    value = normalize_api_prediction({"response": [{"predictions": {
        "winner": {"id": 10, "name": "Home", "comment": "Win"}, "under_over": "Over 2.5",
        "goals": {"home": "2.1", "away": "0.9"}, "percent": {"home": "60%", "draw": "25%", "away": "15%"}},
        "comparison": {"att": {"home": "64%", "away": "36%"}}}]}, fixture_id=7)
    assert value.available and value.predicted_winner_id == 10
    assert value.probabilities["HOME_WIN"] == Decimal("0.6")
    assert value.under_over == "OVER_2_5" and value.expected_goals_home == Decimal("2.1")
    assert set(("OVER_2_5", "UNDER_2_5", "BTTS_YES", "BTTS_NO")) <= value.probabilities.keys()


def test_api_prediction_normalizes_real_signed_total_without_negative_goal_rate():
    value = normalize_api_prediction({"response": [{"predictions": {
        "winner": {"id": 70, "name": "Home"}, "under_over": "+1.5",
        "goals": {"home": "-4.5", "away": "-2.5"},
        "percent": {"home": "45%", "draw": "45%", "away": "10%"},
    }, "comparison": {}}]}, fixture_id=8)
    assert value.available and value.under_over == "OVER_1_5"
    assert value.expected_goals_home is None and value.expected_goals_away is None
    assert set(value.probabilities) == {"HOME_WIN", "DRAW", "AWAY_WIN"}


def test_reviewed_bookmaker_catalogue_tags_only_exact_name_matches():
    entries = review_bookmaker_catalogue({"response": [
        {"id": 1, "name": "OlyBet"}, {"id": 2, "name": "Not OlyBet Latvia"},
        {"id": 3, "name": "Pinnacle"},
    ]})
    assert entries[0].relevance == "REVIEWED_LATVIAN_FACING_NAME_MATCH"
    assert entries[1].relevance == "OTHER_CURRENT_PROVIDER_SOURCE"
    assert entries[2].relevance == "REPUTABLE_CURRENT_CONSENSUS_SOURCE"


def test_adaptive_quota_preserves_1500_reserve_and_hard_maximum_100():
    quota = {"interpretation_status": "NORMALIZED", "daily_remaining": 1550, "minute_remaining": 300}
    budget = adaptive_quota_budget(quota, requested_maximum=100, already_consumed=1)
    assert budget.effective_cycle_maximum == 51
    assert budget.additional_calls_available == 50
    assert budget.daily_safety_reserve == DAILY_SAFETY_RESERVE
    assert MAX_DISCOVERY_CALLS_PER_CYCLE == 100
    projection = projected_daily_usage(maximum_per_cycle=100)
    assert projection["maximum_discovery_calls"] == 4800
    assert projection["projected_worst_case_total"] == 6300
    assert projection["within_daily_limit"] is True


def odds_payload(updated=NOW, fixture_id=7):
    books = []
    for identity, name, home, draw, away in ((3, "Betfair", "2.20", "3.50", "4.00"), (4, "Pinnacle", "2.15", "3.60", "4.10")):
        books.append({"id": identity, "name": name, "bets": [
            {"name": "Match Winner", "values": [{"value": "Home", "odd": home}, {"value": "Draw", "odd": draw}, {"value": "Away", "odd": away}]},
            {"name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "1.90"}, {"value": "Under 2.5", "odd": "1.95"}]},
        ]})
    return {"results": 1, "response": [{"fixture": {"id": fixture_id}, "update": updated.isoformat(), "bookmakers": books}]}


def test_current_market_consensus_removes_margin_and_keeps_provenance():
    value = current_market_consensus(odds_payload(), fixture_id=7, retrieved_at=NOW, now=NOW)["1X2"]
    assert value.status == "AVAILABLE" and value.bookmaker_count == 2
    assert sum(value.fair_probabilities.values(), Decimal(0)) == Decimal(1)
    assert len(value.quotes) == 6 and all(item.provenance_fingerprint for item in value.quotes)


def test_stale_current_odds_are_rejected():
    value = current_market_consensus(odds_payload(NOW - timedelta(hours=4)), fixture_id=7,
                                     retrieved_at=NOW, now=NOW)["1X2"]
    assert value.status == "STALE_CURRENT_ODDS" and not value.fair_probabilities


def test_ensemble_agreement_approves():
    signals = [EnsembleSignal(name, "HOME_WIN", probability, "HOME_WIN", weight, "AVAILABLE", name)
               for name, probability, weight in (("CURRENT_MARKET_CONSENSUS", Decimal("0.56"), Decimal("0.9")),
                                                  ("PI_RATINGS", Decimal("0.59"), Decimal("0.9")),
                                                  ("API_FOOTBALL_PREDICTION", Decimal("0.60"), Decimal("0.75")),
                                                  ("CURRENT_MATCH_INTELLIGENCE", Decimal("0.58"), Decimal("0.7")))]
    decision = evaluate_ensemble("HOME_WIN", Decimal("2.00"), signals)
    assert decision.decision == "APPROVED" and decision.confidence in {"MEDIUM", "HIGH"}


def test_ensemble_material_disagreement_rejects():
    signals = [
        EnsembleSignal("CURRENT_MARKET_CONSENSUS", "HOME_WIN", Decimal("0.55"), "HOME_WIN", Decimal("0.9"), "AVAILABLE", "x"),
        EnsembleSignal("PI_RATINGS", "HOME_WIN", Decimal("0.25"), "AWAY_WIN", Decimal("0.9"), "AVAILABLE", "x"),
        EnsembleSignal("API_FOOTBALL_PREDICTION", "HOME_WIN", Decimal("0.22"), "AWAY_WIN", Decimal("0.75"), "AVAILABLE", "x"),
    ]
    assert "MATERIAL_SIGNAL_DISAGREEMENT" in evaluate_ensemble("HOME_WIN", Decimal("2.0"), signals).rejection_reasons


def test_opponent_adjusted_form_rewards_stronger_opposition():
    pi = PiRatingAdapter(999); pi.replay(results())
    strong = opponent_adjusted_form(10, results(), pi)
    weak = opponent_adjusted_form(20, results(), pi)
    assert strong.state == weak.state == "AVAILABLE"
    assert strong.score != weak.score
    assert all("expected_result" in item for item in strong.components)


def test_injury_impact_uses_safe_count_fallback_and_usage_when_present():
    absences = [{"player_id": "1", "status": "INJURED"}, {"player_id": "2", "status": "SUSPENDED"}]
    fallback = availability_impact(absences)
    assert fallback.state == "COUNT_FALLBACK" and fallback.impact == Decimal("0.050")
    weighted = availability_impact(absences, {"1": PlayerUsage("1", starts=8, minutes=700,
                                                                 recent_start_frequency=Decimal("0.8"))})
    assert weighted.state == "USAGE_WEIGHTED" and weighted.weighted_players[0]["player_id"] == "1"


class Response:
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


class FakeClient:
    def __init__(self): self.request_count = 0; self.limit = 40; self.last = {}
    def restrict_requests(self, maximum_calls, *, daily_reserve=20): self.limit = maximum_calls
    def _hit(self, endpoint, query, payload):
        assert self.request_count < self.limit
        self.request_count += 1; self.last = {
            "retrieved_at_utc": (NOW + timedelta(seconds=5)).isoformat(),
            "endpoint": endpoint, "query": query,
        }
        return payload
    def response_metadata(self): return self.last
    async def account_status(self): return self._hit("/status", {}, {"response": {}})
    async def leagues(self, *, current=True): return self._hit("/leagues", {}, {"response": [coverage(full=True)]})
    async def fixtures_by_date(self, day, *, timezone_name="UTC"):
        fixture = {"fixture": {"id": 7, "date": (NOW + timedelta(hours=4)).isoformat(), "status": {"short": "NS"}},
                   "league": {"id": 999, "name": "Worldwide League", "season": 2026},
                   "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 20, "name": "Away"}}}
        return self._hit("/fixtures", {"date": day}, {"results": 1, "response": [fixture]})
    async def current_odds(self, fixture_id): return self._hit("/odds", {"fixture": fixture_id}, odds_payload(fixture_id=fixture_id))
    async def finished_matches(self, league_id, season, last=100):
        assert last == 99
        rows = []
        for item in results():
            rows.append({"fixture": {"id": item.fixture_id, "date": item.kickoff_utc.isoformat(), "status": {"short": "FT"}},
                         "league": {"id": item.league_id, "season": item.season},
                         "teams": {"home": {"id": item.home_team_id}, "away": {"id": item.away_team_id}},
                         "goals": {"home": item.home_goals, "away": item.away_goals}})
        return self._hit("/fixtures", {"league": league_id}, rows)
    async def _get(self, endpoint, *, params):
        if endpoint == "/odds" and "date" in params:
            payload = {**odds_payload(fixture_id=7), "paging": {"current": 1, "total": 1}}
        elif endpoint == "/odds/bookmakers":
            payload = {"results": 2, "response": [{"id": 3, "name": "Betfair"}, {"id": 4, "name": "Pinnacle"}]}
        elif endpoint == "/predictions":
            payload = {"response": [{"predictions": {"winner": {"id": 10, "name": "Home"},
                       "under_over": "Over 2.5", "goals": {"home": "2", "away": "1"},
                       "percent": {"home": "60%", "draw": "24%", "away": "16%"}}, "comparison": {}}]}
        elif endpoint == "/injuries": payload = {"response": []}
        else: payload = {"response": []}
        return Response(self._hit(endpoint, params, payload))


def test_api_call_budget_and_shadow_comparison(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = FakeClient(); repository = ShadowEvidenceRepository(Path("var/shadow.db"))
    runner = LabV2ShadowRunner(client, repository, capability_cache_path=Path("var/capabilities.json"), maximum_calls=40)
    report = asyncio.run(runner.run(now=NOW, horizon_days=1, publication_requested=True))
    persisted = repository.all("rehearsal")
    repository.close()
    assert report["api_calls_consumed"] <= 40
    assert report["fixtures_discovered"] == 1 and report["number_of_leagues"] == 1
    assert report["capability_tier_distribution"] == {"TIER_A_FULL": 1}
    assert report["v1_candidate_count"] == 0
    assert report["v2_candidate_count"] >= 0
    assert report["telegram_sends"] == 0 and report["historical_bookmaker_odds_used"] is False
    assert report["api_call_ceiling"] == 40
    assert report["odds_pagination"]["page_calls"] == 1
    assert report["current_odds_fixtures"] == 1
    assert report["fixtures_with_no_current_odds"] == 0
    assert report["fixtures_rejected_for_stale_current_odds"] == 0
    assert sum(call["endpoint"] == "/fixtures(results)" for call in runner.calls) == 1
    assert report["mode"] == report["analysis_mode"] == "LAB_V2_NO_SEND"
    assert report["publication_requested"] is report["publication_enabled"] is True
    assert report["telegram_transport_constructed"] is False
    assert persisted == [report]


def test_market_consensus_can_restrict_to_reviewed_current_sources():
    restricted = current_market_consensus(
        odds_payload(), fixture_id=7, retrieved_at=NOW, now=NOW,
        allowed_bookmaker_ids=frozenset({3}),
    )["1X2"]
    assert restricted.status == "INSUFFICIENT_COMPARABLE_BOOKMAKERS"
    assert {quote.bookmaker_id for quote in restricted.quotes} == {3}


def test_near_kickoff_stage_requires_review_but_tier_c_can_finish_without_lineups():
    from types import SimpleNamespace
    approved = evaluate_ensemble("HOME_WIN", Decimal("2.00"), [
        EnsembleSignal("CURRENT_MARKET_CONSENSUS", "HOME_WIN", Decimal("0.56"), "HOME_WIN", Decimal("0.9"), "AVAILABLE", "x"),
        EnsembleSignal("PI_RATINGS", "HOME_WIN", Decimal("0.59"), "HOME_WIN", Decimal("0.9"), "AVAILABLE", "x"),
        EnsembleSignal("API_FOOTBALL_PREDICTION", "HOME_WIN", Decimal("0.60"), "HOME_WIN", Decimal("0.75"), "AVAILABLE", "x"),
        EnsembleSignal("CURRENT_MATCH_INTELLIGENCE", "HOME_WIN", Decimal("0.58"), "HOME_WIN", Decimal("0.8"), "AVAILABLE", "x"),
    ])
    fixture = {"kickoff_utc": NOW + timedelta(minutes=45), "capability": SimpleNamespace(
        lineups=False, injuries=False, tier=CapabilityTier.TIER_C_BASIC)}
    assert _stage(approved, fixture, NOW, {}) == "FINAL_REVIEW_REQUIRED"
    review = {"fixture_refreshed": True, "odds_refreshed": True,
              "lineup_status": "NOT_SUPPORTED", "injuries_status": "NOT_SUPPORTED"}
    assert _stage(approved, fixture, NOW, review) == "READY_TO_PUBLISH"
    fixture["kickoff_utc"] = NOW + timedelta(hours=2)
    assert _stage(approved, fixture, NOW, review) == "EARLY_CANDIDATE"


def test_ready_publication_handoff_is_lab_only_and_exactly_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.lab_combo.repository import ComboRepository
    ledger = ComboRepository(Path("var/lab_combo/ledger.db"))
    candidate = {
        "candidate_id": "candidate-1", "policy": "v2", "fixture_id": 7,
        "market": "HOME_WIN", "decision": "APPROVED", "stage": "READY_TO_PUBLISH",
        "home_team": "Home", "away_team": "Away", "home_team_id": 10, "away_team_id": 20,
        "kickoff_utc": (NOW + timedelta(minutes=30)).isoformat(), "captured_odds": "1.80",
        "offered_odds": "1.80", "quote_provenance_fingerprint": "q1", "edge": "0.06",
        "ensemble_probability": "0.62", "confidence": "HIGH", "experimental_confidence": "HIGH",
        "provider_type": "API_FOOTBALL_CURRENT_ODDS", "provider_origin_timestamp_utc": NOW.isoformat(),
        "goalvision_retrieved_at_utc": NOW.isoformat(), "final_review_completed_at_utc": NOW.isoformat(),
        "league": "Small League", "capability_tier": "TIER_C_BASIC", "odds_band": "1.70-1.99",
        "pi_available": "AVAILABLE", "pi_agreement": "AGREEMENT",
        "api_prediction_relation": "AGREEMENT", "market_consensus_relation": "AGREEMENT",
        "lineup_confirmed": "NOT_SUPPORTED", "ensemble_decision_class": "APPROVED",
    }
    report = {"candidate_markets": [candidate]}
    first = prepare_v2_publications(report, ledger, now=NOW)
    second = prepare_v2_publications(report, ledger, now=NOW)
    assert len(first["singles"]) == 1 and len(second["singles"]) == 1
    assert len(ledger.all("single_prediction")) == 1
    message = v2_single_message(first["singles"][0])
    assert message.startswith("🧪 GoalVision AI Lab") and "raw" not in message.casefold()
    assert "Official" not in message and first["combos"] == []
    ledger.close()


def _controlled_ready_candidate(clock: datetime) -> dict[str, object]:
    signals = [
        EnsembleSignal(name, "HOME_WIN", probability, "HOME_WIN", reliability, "AVAILABLE", name)
        for name, probability, reliability in (
            ("CURRENT_MARKET_CONSENSUS", Decimal("0.56"), Decimal("0.90")),
            ("PI_RATINGS", Decimal("0.59"), Decimal("0.90")),
            ("API_FOOTBALL_PREDICTION", Decimal("0.60"), Decimal("0.75")),
            ("CURRENT_MATCH_INTELLIGENCE", Decimal("0.58"), Decimal("0.80")),
        )
    ]
    decision = evaluate_ensemble("HOME_WIN", Decimal("1.90"), signals)
    fixture = {
        "kickoff_utc": clock + timedelta(minutes=30),
        "capability": SimpleNamespace(
            lineups=False,
            injuries=False,
            tier=CapabilityTier.TIER_C_BASIC,
        ),
    }
    review = {
        "fixture_refreshed": True,
        "odds_refreshed": True,
        "lineup_status": "NOT_SUPPORTED",
        "injuries_status": "NOT_SUPPORTED",
    }
    stage = _stage(decision, fixture, clock, review)
    assert decision.decision == "APPROVED"
    assert decision.confidence == "MEDIUM"
    assert stage == "READY_TO_PUBLISH"
    return {
        "candidate_id": "deterministic-ready-v2-candidate",
        "policy": decision.policy,
        "fixture_id": 7001,
        "market": "HOME_WIN",
        "decision": decision.decision,
        "stage": stage,
        "home_team": "Fixture Home",
        "away_team": "Fixture Away",
        "home_team_id": 701,
        "away_team_id": 702,
        "kickoff_utc": fixture["kickoff_utc"].isoformat(),
        "captured_odds": "1.90",
        "offered_odds": "1.90",
        "quote_provenance_fingerprint": "deterministic-current-quote",
        "edge": str(decision.edge),
        "ensemble_probability": str(decision.ensemble_probability),
        "confidence": decision.confidence,
        "experimental_confidence": decision.confidence,
        "provider_type": "API_FOOTBALL_CURRENT_ODDS",
        "provider_origin_timestamp_utc": clock.isoformat(),
        "goalvision_retrieved_at_utc": clock.isoformat(),
        "final_review_completed_at_utc": clock.isoformat(),
        "league": "Deterministic League",
        "capability_tier": "TIER_C_BASIC",
        "odds_band": "1.70-1.99",
        "pi_available": "AVAILABLE",
        "pi_agreement": "AGREEMENT",
        "api_prediction_relation": "AGREEMENT",
        "market_consensus_relation": "AGREEMENT",
        "lineup_confirmed": "NOT_SUPPORTED",
        "ensemble_decision_class": decision.decision,
    }


class _NoNetworkClient:
    def __init__(self, *, request_limit: int) -> None:
        self.request_limit = request_limit

    async def close(self) -> None:
        return None


class _DeterministicReadyRunner:
    def __init__(self, client, repository, **kwargs) -> None:
        self.repository = repository

    async def run(
        self,
        *,
        now: datetime,
        horizon_days: int,
        publication_requested: bool,
    ) -> dict[str, object]:
        candidate = _controlled_ready_candidate(now)
        return {
            "schema_version": "deterministic-ready-v2-fixture",
            "mode": "LAB_V2_NO_SEND",
            "analysis_mode": "LAB_V2_NO_SEND",
            "publication_requested": publication_requested,
            "publication_enabled": publication_requested,
            "publication_attempt_count": 0,
            "ready_candidate_count": 1,
            "candidate_markets": [candidate],
            "telegram_sends": 0,
            "telegram_transport_constructed": False,
            "historical_bookmaker_odds_used": False,
            "official_mutations": 0,
        }


class _FakeBot:
    username = LAB_BOT_USERNAME.removeprefix("@")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _RecordingTransport:
    constructed = 0
    calls = 0
    fail = False

    def __init__(self, token: str) -> None:
        type(self).constructed += 1
        self.bot = _FakeBot()

    async def send_message_receipt(self, **kwargs):
        type(self).calls += 1
        assert kwargs["chat_id"] == LAB_CHAT_ID
        if type(self).fail:
            raise TimeoutError
        return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=9001)


def _install_controlled_cycle_fakes(monkeypatch, *, fail: bool = False) -> None:
    import app.lab_v2_shadow.cli as cli

    _RecordingTransport.constructed = 0
    _RecordingTransport.calls = 0
    _RecordingTransport.fail = fail
    monkeypatch.setattr(cli, "FootballClient", _NoNetworkClient)
    monkeypatch.setattr(cli, "LabV2ShadowRunner", _DeterministicReadyRunner)
    monkeypatch.setattr(cli, "LabTelegramTransport", _RecordingTransport)
    monkeypatch.setattr(
        cli,
        "load_lab_telegram_config",
        lambda: LabTelegramConfig(
            token="fictional-test-token",
            chat_id=LAB_CHAT_ID,
            automatic_enabled=True,
        ),
    )
    monkeypatch.setattr(
        "app.lab_combo.secure_logging.install_lab_secret_redaction",
        lambda token: None,
    )


def _controlled_cycle_arguments(*, send: bool) -> list[str]:
    values = [
        "controlled-cycle",
        "--shadow-database", "var/lab_v2/shadow.db",
        "--analysis-database", "var/lab_combo/analysis.db",
        "--ledger", "var/lab_combo/ledger.db",
        "--capability-cache", "var/lab_v2/capabilities.json",
        "--horizon-days", "1",
        "--max-calls", "40",
        "--daily-reserve", "1500",
    ]
    return [*values, "--send"] if send else values


def test_controlled_cycle_send_ready_candidate_is_exactly_once_end_to_end(
    tmp_path, monkeypatch, capsys,
):
    import app.lab_v2_shadow.cli as cli
    from app.lab_combo.repository import ComboRepository

    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)

    assert cli.main(_controlled_cycle_arguments(send=True)) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["analysis_mode"] == "LAB_V2_NO_SEND"
    assert first["mode"] == "LAB_V2_CONTROLLED_SEND"
    assert first["publication_requested"] is first["publication_enabled"] is True
    assert first["telegram_transport_constructed"] is True
    assert first["publication_attempt_count"] == first["telegram_sends"] == 1

    assert cli.main(_controlled_cycle_arguments(send=True)) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["controlled_publication"]["reason"] == "EXACTLY_ONCE_NO_NEW_PUBLICATIONS"
    assert replay["telegram_transport_constructed"] is False
    assert replay["publication_attempt_count"] == replay["telegram_sends"] == 0
    assert _RecordingTransport.constructed == _RecordingTransport.calls == 1

    ledger = ComboRepository(Path("var/lab_combo/ledger.db"))
    try:
        assert len(ledger.all("single_prediction")) == 1
        assert len(ledger.all("claim")) == 1
        assert len(ledger.all("receipt")) == 1
        assert ledger.all("delivery_unknown") == []
    finally:
        ledger.close()
    shadow = ShadowEvidenceRepository(Path("var/lab_v2/shadow.db"))
    try:
        cycles = shadow.all("publication_cycle")
        assert len(cycles) == 2
        assert cycles[0]["analysis_mode"] == "LAB_V2_NO_SEND"
        assert cycles[0]["telegram_sends"] == 1
        assert cycles[1]["telegram_sends"] == 0
    finally:
        shadow.close()


def test_controlled_cycle_without_send_never_constructs_or_mutates_delivery(
    tmp_path, monkeypatch, capsys,
):
    import app.lab_v2_shadow.cli as cli

    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    monkeypatch.setattr(
        cli,
        "load_lab_telegram_config",
        lambda: pytest.fail("no-send must not load Telegram configuration"),
    )

    assert cli.main(_controlled_cycle_arguments(send=False)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ready_candidate_count"] == 1
    assert report["analysis_mode"] == report["mode"] == "LAB_V2_NO_SEND"
    assert report["publication_requested"] is report["publication_enabled"] is False
    assert report["telegram_transport_constructed"] is False
    assert report["publication_attempt_count"] == report["telegram_sends"] == 0
    assert _RecordingTransport.constructed == _RecordingTransport.calls == 0
    assert not Path("var/lab_combo/ledger.db").exists()


def test_indeterminate_v2_send_blocks_replay_even_after_quote_refresh(
    tmp_path, monkeypatch, capsys,
):
    import app.lab_v2_shadow.cli as cli
    from app.lab_combo.repository import ComboRepository

    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch, fail=True)

    assert cli.main(_controlled_cycle_arguments(send=True)) == 0
    failed = json.loads(capsys.readouterr().out)
    assert failed["publication_attempt_count"] == 1
    assert failed["telegram_sends"] == 0
    assert failed["controlled_publication"]["deliveries"][0]["status"] == (
        "DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED"
    )

    original = _controlled_ready_candidate

    def refreshed(clock: datetime) -> dict[str, object]:
        candidate = original(clock)
        candidate["quote_provenance_fingerprint"] = "refreshed-current-quote"
        return candidate

    monkeypatch.setattr("tests.test_lab_v2_shadow._controlled_ready_candidate", refreshed)
    assert cli.main(_controlled_cycle_arguments(send=True)) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["controlled_publication"]["reason"] == "EXACTLY_ONCE_NO_NEW_PUBLICATIONS"
    assert replay["publication_attempt_count"] == replay["telegram_sends"] == 0
    assert _RecordingTransport.constructed == _RecordingTransport.calls == 1

    ledger = ComboRepository(Path("var/lab_combo/ledger.db"))
    try:
        assert len(ledger.all("single_prediction")) == 1
        assert len(ledger.all("claim")) == 1
        assert len(ledger.all("delivery_unknown")) == 1
        assert ledger.all("receipt") == []
    finally:
        ledger.close()


def test_shipped_v2_systemd_service_explicitly_arms_controlled_send():
    service = (
        Path(__file__).parents[1]
        / "app/lab_v2_shadow/systemd/goalvision-lab-v2-discover.service"
    ).read_text(encoding="utf-8")
    assert (
        "ExecStart=/home/arvis/GoalVisionAI/.venv/bin/python -m app.lab_v2_shadow "
        "controlled-cycle --send --max-calls 100 --daily-reserve 1500"
    ) in service


def test_v2_publication_does_not_duplicate_a_published_v1_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.lab_combo.repository import ComboRepository
    ledger = ComboRepository(Path("var/lab_combo/ledger.db"))
    assert prepare_v2_publications({"candidate_markets": [{
        "decision": "APPROVED", "stage": "EARLY_CANDIDATE",
    }]}, ledger, now=NOW)["singles"] == []
    ledger.append("single_prediction", "v1-single", {
        "prediction_id": "v1-single", "publication_key": "7:HOME_WIN",
    })
    ledger.append("receipt", "single_prediction:v1-single", {
        "status": "SENT", "chat_id": "-1003510920417", "message_id": 1,
    })
    report = {"candidate_markets": [{
        "candidate_id": "v2-candidate", "policy": "v2", "fixture_id": 7,
        "market": "HOME_WIN", "decision": "APPROVED", "stage": "READY_TO_PUBLISH",
        "home_team": "Home", "away_team": "Away", "home_team_id": 10, "away_team_id": 20,
        "kickoff_utc": (NOW + timedelta(minutes=30)).isoformat(), "captured_odds": "1.80",
        "quote_provenance_fingerprint": "q1", "edge": "0.06",
    }]}
    prepared = prepare_v2_publications(report, ledger, now=NOW)
    assert prepared["singles"] == []
    assert [item["prediction_id"] for item in ledger.all("single_prediction")] == ["v1-single"]
    ledger.close()


def test_result_segmentation_keeps_singles_and_combos_separate():
    result = segment_results([
        {"kind": "SINGLE", "status": "WON", "market": "HOME_WIN", "league": "L", "odds_band": "1.70-1.99"},
        {"kind": "COMBO", "status": "LOST", "market": "COMBO", "league": "MULTI", "odds_band": "3.50+"},
    ])
    assert next(item for item in result["SINGLE"] if item["dimension"] == "market")["won"] == 1
    assert next(item for item in result["COMBO"] if item["dimension"] == "market")["lost"] == 1
