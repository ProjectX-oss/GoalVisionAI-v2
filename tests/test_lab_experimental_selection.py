"""Focused LAB_EXPERIMENTAL_SELECTION_V1 tests; no provider or Telegram network."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import permutations
from pathlib import Path
import logging
import tempfile
from types import SimpleNamespace

from app.current_match_intelligence.models import (
    CurrentMatchIntelligenceSnapshot, DataClass, FieldProvenance,
    FreshnessEvidence, FreshnessStatus, IntelligenceField,
)
from app.current_odds_forward_test.discovery import discover_current_fixture
from app.lab_combo.cli import _recheck_fixture_ids
from app.lab_combo.experimental import (
    MAX_COMBOS_PER_DISCOVERY_CYCLE,
    combined_odds_eligible, evaluate_snapshot, select_combo_batch, select_single_predictions,
)
from app.lab_combo.presentation import (
    ResultImagePaths, combo_message, combo_result_message, public_decimal,
    single_message, single_result_message,
)
from app.lab_combo.repository import ComboRepository
from app.lab_combo.service import LabComboService
from app.lab_combo.secure_logging import SecretRedactionFilter
from app.lab_combo.settlement import resolve_single, single_statistics, statistics
from app.lab_telegram.models import LabTelegramConfig
from app.real_match_lab_analysis.models import LAB_CHAT_ID
from tests.test_api_football_adaptive_discovery import fixture, odds
from tests.test_api_football_discovery_efficiency import CostProvider


NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def snapshot(*, fixture_id="1", home_odds="1.70", lineup=True,
             kickoff_minutes=180, refresh_age_minutes=0):
    provenance = FieldProvenance("API-FOOTBALL", "/fixtures", NOW, NOW, fixture_id)
    values = {
        "fixture.id": fixture_id, "home.team_id": int(fixture_id) * 10,
        "away.team_id": int(fixture_id) * 10 + 1, "home.team_name": f"Home {fixture_id}",
        "away.team_name": f"Away {fixture_id}", "competition.id": int(fixture_id),
        "competition.name": f"League {fixture_id}",
        "feature.home_form_strength": "0.70", "feature.away_form_strength": "0.30",
        "feature.home_recent_goals_for_per_match": "2.5",
        "feature.home_recent_goals_against_per_match": "0.8",
        "feature.away_recent_goals_for_per_match": "0.8",
        "feature.away_recent_goals_against_per_match": "2.0",
        "feature.rest_days_home": 6, "feature.rest_days_away": 5,
        "feature.schedule_congestion_home": 0, "feature.schedule_congestion_away": 1,
        "feature.injury_count_home": 1, "feature.injury_count_away": 1,
        "feature.suspension_count_home": 0, "feature.suspension_count_away": 0,
        "home.season.home.matches_played": 4, "home.season.home.goals_for": 10,
        "away.season.away.matches_played": 4, "away.season.away.goals_against": 8,
        "away.season.away.goals_for": 3, "home.season.home.goals_against": 3,
        "market.HOME_WIN.decimal_odds": home_odds,
        "market.HOME_WIN.bookmaker": "Book",
        "market.HOME_WIN.implied_probability": str(Decimal(1) / Decimal(home_odds)),
    }
    if lineup:
        values.update({
            "home.lineup.confirmed": True, "away.lineup.confirmed": True,
            "home.formation": "4-3-3", "away.formation": "4-2-3-1",
            "feature.confirmed_starters_count_home": 11,
            "feature.confirmed_starters_count_away": 11,
            "feature.lineup_continuity_home": "0.73",
            "feature.lineup_continuity_away": "0.64",
            "feature.missing_recent_starters_count_home": 1,
            "feature.missing_recent_starters_count_away": 2,
            "home.lineup.starters.101.player_id": "101",
            "away.lineup.starters.201.player_id": "201",
            "home.lineup.substitutes.109.player_id": "109",
            "away.lineup.substitutes.209.player_id": "209",
        })
    fields = tuple(IntelligenceField(name, DataClass.PRE_MATCH_DYNAMIC, value, (provenance,))
                   for name, value in values.items())
    retrieved = NOW - timedelta(minutes=refresh_age_minutes)
    freshness = tuple(FreshnessEvidence(signal, FreshnessStatus.FRESH, NOW, retrieved, NOW + timedelta(hours=1), 3600)
                      for signal in ("fixture_context", "injuries", "team_statistics", "team_history", "odds"))
    freshness += (FreshnessEvidence("confirmed_lineups", FreshnessStatus.FRESH if lineup else FreshnessStatus.MISSING,
                                    NOW, retrieved, NOW + timedelta(minutes=15), 900),)
    return CurrentMatchIntelligenceSnapshot("v1", "snapshot-" + fixture_id, fixture_id, 1,
        NOW + timedelta(minutes=kickoff_minutes), NOW, fields, freshness, (), (), (), "fp-" + fixture_id)


def approved(fixture_id, odds="1.70", market="HOME_WIN"):
    value = next(item for item in evaluate_snapshot(snapshot(fixture_id=str(fixture_id), home_odds=odds), now=NOW)
                 if item["market"] == "HOME_WIN")
    value["market"] = market
    value["decision"] = "APPROVED"; value["rejection_reasons"] = []
    value["stage"] = "READY_TO_PUBLISH"
    value["final_review_completed_at_utc"] = NOW.isoformat()
    return value


def ledger_fixture():
    root = Path("var/lab_combo"); root.mkdir(parents=True, exist_ok=True)
    directory = tempfile.TemporaryDirectory(dir=root)
    return directory, ComboRepository(Path(directory.name) / "ledger.db")


def test_low_single_odds_are_judged_only_by_non_odds_quality_gates():
    low = next(item for item in evaluate_snapshot(snapshot(home_odds="1.25"), now=NOW) if item["market"] == "HOME_WIN")
    assert "SINGLE_ODDS_BELOW_1_70" not in low["rejection_reasons"]
    assert "INSUFFICIENT_MARKET_CONTEXT_AGREEMENT" in low["rejection_reasons"]


def test_early_candidate_retained_but_never_selected_or_used_in_combo():
    values = evaluate_snapshot(snapshot(lineup=False), now=NOW)
    home = next(item for item in values if item["market"] == "HOME_WIN")
    assert home["decision"] == "APPROVED"
    assert home["stage"] == "EARLY_CANDIDATE"
    assert select_single_predictions([home], existing_keys=set(), now=NOW) == []
    assert select_combo_batch([home, approved(2), approved(3)], used_leg_keys=set(), now=NOW) == []


def test_lineup_sensitive_candidate_waits_then_confirmed_recheck_is_ready():
    waiting = next(item for item in evaluate_snapshot(
        snapshot(lineup=False, kickoff_minutes=45), now=NOW
    ) if item["market"] == "HOME_WIN")
    ready = next(item for item in evaluate_snapshot(
        snapshot(lineup=True, kickoff_minutes=45), now=NOW
    ) if item["market"] == "HOME_WIN")
    assert waiting["stage"] == "FINAL_REVIEW_REQUIRED"
    assert waiting["stage_reasons"] == ["LINEUP_NOT_YET_PUBLISHED"]
    assert waiting["rejection_reasons"] == []
    assert ready["stage"] == "READY_TO_PUBLISH"
    assert ready["final_review_completed_at_utc"] == NOW.isoformat()


def test_failed_final_review_rejects_stale_refresh():
    value = next(item for item in evaluate_snapshot(
        snapshot(kickoff_minutes=45, refresh_age_minutes=6), now=NOW
    ) if item["market"] == "HOME_WIN")
    assert value["stage"] == "REJECTED"
    assert "FINAL_REVIEW_ODDS_NOT_REFRESHED" in value["rejection_reasons"]


def test_cheap_discovery_defers_history_and_preserves_budget():
    client = CostProvider({"2026-08-01": [fixture(1), fixture(2), fixture(3)]},
                          {i: odds(i) for i in range(1, 4)}, minute=300)
    value = asyncio.run(discover_current_fixture(
        client, now=NOW.replace(month=8, day=1), horizon_days=1,
        maximum_fixtures=3, require_team_baseline=False,
    ))
    assert len(value["selected_fixtures"]) == 3
    assert client.history_calls == []
    assert value["api_call_count"] == 5
    assert all(item["required_order"] == ["CURRENT_ODDS"] for item in value["request_cost_report"])


def test_combo_policy_multiple_disjoint_deterministic_and_not_forced():
    assert combined_odds_eligible("1.01")
    assert combined_odds_eligible("1.99")
    assert not combined_odds_eligible("15.01")
    values = [approved(i) for i in range(1, 10)]
    first = select_combo_batch(values, used_leg_keys=set(), now=NOW)
    reverse = select_combo_batch(list(reversed(values)), used_leg_keys=set(), now=NOW)
    assert first == reverse
    assert len(first) == MAX_COMBOS_PER_DISCOVERY_CYCLE == 3
    assert all(len(combo["legs"]) == 3 for combo in first)
    keys = [leg["candidate_id"] for combo in first for leg in combo["legs"]]
    assert len(keys) == len(set(keys))
    fixtures = [leg["fixture_id"] for combo in first for leg in combo["legs"]]
    assert len(fixtures) == len(set(fixtures))
    assert select_combo_batch(values[:2], used_leg_keys=set(), now=NOW) == []
    reused_fixture = [approved(1), approved(1, market="DRAW"), approved(2)]
    assert select_combo_batch(reused_fixture, used_leg_keys=set(), now=NOW) == []
    shared_team = [approved(i) for i in range(1, 4)]
    shared_team[1]["home_team_id"] = shared_team[0]["home_team_id"]
    assert select_combo_batch(shared_team, used_leg_keys=set(), now=NOW) == []
    used = {f"{i}:HOME_WIN" for i in range(1, 4)}
    assert all(leg["fixture_id"] not in {"1", "2", "3"}
               for combo in select_combo_batch(values, used_leg_keys=used, now=NOW) for leg in combo["legs"])

    low_odds = [approved(i, odds=value) for i, value in enumerate(("1.10", "1.15", "1.20"), 20)]
    low_combo = select_combo_batch(low_odds, used_leg_keys=set(), now=NOW)
    assert len(low_combo) == 1
    assert Decimal(low_combo[0]["combined_odds"]) == Decimal("1.518000")


def test_single_selection_no_duplicate_publication_and_one_market_per_fixture():
    values = [approved(1), approved(1, market="DRAW"), approved(2)]
    result = select_single_predictions(values, existing_keys={"2:HOME_WIN"}, now=NOW)
    assert len(result) == 1 and result[0]["fixture_id"] == "1"


def test_independent_ledgers_statistics_partial_void_and_immutable_odds():
    directory, ledger = ledger_fixture()
    try:
        single = {**approved(1), "prediction_id": "s1", "publication_key": "1:HOME_WIN"}
        ledger.append("single_prediction", "s1", single)
        ledger.append("receipt", "single_prediction:s1", {"sent": True})
        ledger.append("single_settlement", "s1", {"prediction_id": "s1", "status": "WON", "unit_result": "0.70"})
        combo = {"prediction_id": "c1", "combined_odds": "4.913", "legs": [approved(i) for i in range(1, 4)]}
        ledger.append("prediction", "c1", combo)
        ledger.append("receipt", "combo_prediction:c1", {"sent": True})
        ledger.append("settlement", "c1", {"prediction_id": "c1", "status": "PARTIAL_VOID", "unit_result": "1.89"})
        assert single_statistics(ledger)["WON"] == 1
        assert single_statistics(ledger)["hypothetical_profit_loss"] == "0.70"
        assert statistics(ledger, published_only=True)["PARTIAL_VOID"] == 1
        assert statistics(ledger, published_only=True)["hypothetical_profit_loss"] == "1.89"
        assert not ledger.append("single_prediction", "s1", single)
        changed = dict(single); changed["captured_odds"] = "9.99"
        try:
            ledger.append("single_prediction", "s1", changed)
            assert False
        except ValueError:
            pass
    finally:
        ledger.close(); directory.cleanup()


def test_lineup_recheck_and_exactly_once_experimental_delivery():
    directory, ledger = ledger_fixture()
    try:
        snap = snapshot(lineup=False)
        ledger.append("fixture_watch", snap.snapshot_id, {"fixture_id": "1", "snapshot_id": snap.snapshot_id,
            "kickoff_utc": (NOW + timedelta(minutes=60)).isoformat(), "lineup_status": "MISSING",
            "evaluated_at_utc": NOW.isoformat()})
        assert _recheck_fixture_ids(ledger, NOW) == [1]
        prediction = {**approved(1), "prediction_id": "s1", "publication_key": "1:HOME_WIN",
                      "published_at_utc": NOW.isoformat(), "kickoff_utc": (NOW + timedelta(hours=1)).isoformat()}
        ledger.append("single_prediction", "s1", prediction)
        ledger.append("single_preview", "s1", {"message": "qualified"})
        class Transport:
            calls = 0
            async def send_message_receipt(self, **kwargs):
                self.calls += 1
                return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=1)
        service = LabComboService(ledger, None, clock=lambda: NOW)
        config = LabTelegramConfig("token", LAB_CHAT_ID, True)
        transport = Transport()
        assert asyncio.run(service.publish_experimental("single_prediction", "s1", config, transport))["sent"]
        assert not asyncio.run(service.publish_experimental("single_prediction", "s1", config, transport))["sent"]
        settlement = {"prediction_id": "s1", "status": "WON", "unit_result": "0.70"}
        ledger.append("single_settlement", "s1", settlement)
        ledger.append("single_settlement_preview", "s1", {"message": "result"})
        assert asyncio.run(service.publish_experimental("single_settlement", "s1", config, transport))["sent"]
        assert not asyncio.run(service.publish_experimental("single_settlement", "s1", config, transport))["sent"]
        assert transport.calls == 2
    finally:
        ledger.close(); directory.cleanup()


def test_publication_requires_recent_final_review_and_refreshed_odds():
    directory, ledger = ledger_fixture()
    try:
        prediction = {
            **approved(1), "prediction_id": "expired", "publication_key": "1:HOME_WIN",
            "kickoff_utc": (NOW + timedelta(minutes=40)).isoformat(),
            "final_review_completed_at_utc": (NOW - timedelta(minutes=6)).isoformat(),
        }
        ledger.append("single_prediction", "expired", prediction)
        ledger.append("single_preview", "expired", {"message": "qualified"})
        class Transport:
            calls = 0
            async def send_message_receipt(self, **kwargs):
                self.calls += 1
                return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=1)
        transport = Transport()
        service = LabComboService(ledger, None, clock=lambda: NOW)
        config = LabTelegramConfig("fictional", LAB_CHAT_ID, True)
        value = asyncio.run(service.publish_experimental(
            "single_prediction", "expired", config, transport,
        ))
        assert value["status"] == "FINAL_REVIEW_EXPIRED"
        assert transport.calls == 0
    finally:
        ledger.close(); directory.cleanup()


def test_concise_latvian_single_combo_format_and_public_rounding():
    single = {
        **approved(1), "home_team": "Stade Brestois 29", "away_team": "PSG",
        "market": "BTTS_YES", "captured_odds": "1.750000000000000000",
        "kickoff_utc": "2026-09-13T18:45:00+00:00",
        "experimental_signal": "0.7140478090772047651247758919",
    }
    message = single_message(single)
    assert message == ("🧪 GoalVision AI Lab\n⚽ Mačs: Stade Brestois 29 – PSG\n"
                       "🏆 Līga: League 1\n🎯 Likme: Abas gūs – Jā\n💰 Koef.: 1.75\n"
                       "⏰ Starts: 21:45\n"
                       "🔎 Pamatojums: sastāvs apstiprināts; komandas un tirgus signāli saskan.\n"
                       "⭐ Pārliecība: HIGH")
    assert single["experimental_signal"] not in message
    assert "0.555555" not in message
    assert public_decimal("2.006666666666") == "2.01"

    legs = [{**approved(i), "home_team": f"Team {i}A", "away_team": f"Team {i}B",
             "kickoff_utc": f"2026-09-13T{16+i:02d}:30:00+00:00"} for i in range(1, 4)]
    combo = {"legs": legs, "combined_odds": "4.913000000000"}
    combo_text = combo_message(combo, 1)
    assert combo_text.startswith("🧪 GoalVision AI Lab Combo #1\n1️⃣")
    assert "🔥 Kopējais koef.: 4.91" in combo_text
    assert "⏰ Pirmais starts: 20:30" in combo_text
    assert "reasoning" not in combo_text.casefold()


def test_win_loss_void_public_messages_and_separate_statistics():
    stats = {"WON": 2, "LOST": 1, "VOID": 1,
             "hypothetical_profit_loss": "0.700000", "roi_yield": "0.233333333"}
    base = {"fixture_id": "1", "home_team": "Home", "away_team": "Away",
            "market": "HOME_WIN", "captured_odds": "1.7000",
            "fulltime_home": 2, "fulltime_away": 1}
    win = single_result_message({**base, "status": "WON"}, stats)
    loss = single_result_message({**base, "status": "LOST"}, stats)
    void = single_result_message({**base, "status": "VOID",
                                  "fulltime_home": None, "fulltime_away": None}, stats)
    assert "✅ UZVARA" in win and "📊 Rezultāts: 2:1" in win
    assert "❌ ZAUDĒJUMS" in loss
    assert "⚪ ATCELTS" in void and "📊 Rezultāts: —" in void
    assert "📈 Single statistika:" in win and "Combo statistika" not in win
    assert "💵 P/L: +0.70u" in win and "📊 ROI: 23.3%" in win

    combo = {"status": "LOST", "effective_combined_odds": "2.8400",
             "legs": [{**base, "outcome": result} for result in ("WON", "LOST", "VOID")]}
    combo_text = combo_result_message(combo, {**stats, "PARTIAL_VOID": 0})
    assert "📈 Combo statistika:" in combo_text and "Single statistika" not in combo_text


def test_result_image_missing_falls_back_to_text_only():
    directory, ledger = ledger_fixture()
    try:
        ledger.append("single_settlement", "s1", {"prediction_id": "s1", "status": "WON"})
        ledger.append("single_settlement_preview", "s1", {"message": "result"})
        class Transport:
            text_calls = 0
            photo_calls = 0
            async def send_message_receipt(self, **kwargs):
                self.text_calls += 1
                return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=1)
            async def send_photo_receipt(self, **kwargs):
                self.photo_calls += 1
                return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=2)
        transport = Transport()
        paths = ResultImagePaths(
            Path("does-not-exist-win.png"), Path("does-not-exist-loss.png"),
            Path("does-not-exist-void.png"),
        )
        service = LabComboService(ledger, None, clock=lambda: NOW, result_images=paths)
        config = LabTelegramConfig("fictional", LAB_CHAT_ID, True)
        assert asyncio.run(service.publish_experimental(
            "single_settlement", "s1", config, transport,
        ))["sent"]
        assert transport.text_calls == 1 and transport.photo_calls == 0
    finally:
        ledger.close(); directory.cleanup()


def test_available_result_image_uses_optional_photo_transport():
    directory, ledger = ledger_fixture()
    try:
        image = Path(directory.name) / "win.png"
        image.write_bytes(b"not-a-real-network-image")
        ledger.append("single_settlement", "s1", {"prediction_id": "s1", "status": "WON"})
        ledger.append("single_settlement_preview", "s1", {"message": "result"})
        class Transport:
            text_calls = 0
            photo_calls = 0
            async def send_message_receipt(self, **kwargs):
                self.text_calls += 1
                return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=1)
            async def send_photo_receipt(self, **kwargs):
                self.photo_calls += 1
                assert kwargs["image_path"] == image
                return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=2)
        transport = Transport()
        service = LabComboService(
            ledger, None, clock=lambda: NOW, result_images=ResultImagePaths(win=image),
        )
        config = LabTelegramConfig("fictional", LAB_CHAT_ID, True)
        assert asyncio.run(service.publish_experimental(
            "single_settlement", "s1", config, transport,
        ))["sent"]
        assert transport.photo_calls == 1 and transport.text_calls == 0
    finally:
        ledger.close(); directory.cleanup()


def test_single_win_loss_void_settlement_uses_captured_odds():
    prediction = {**approved(1), "prediction_id": "s1", "captured_odds": "1.70",
                  "kickoff_utc": (NOW - timedelta(hours=3)).isoformat()}
    def payload(status, home=None, away=None):
        return {"response": [{"fixture": {"id": 1, "status": {"short": status}},
                              "score": {"fulltime": {"home": home, "away": away}}}]}
    assert resolve_single(prediction, payload("FT", 2, 1), NOW)["status"] == "WON"
    assert resolve_single(prediction, payload("FT", 0, 1), NOW)["status"] == "LOST"
    assert resolve_single(prediction, payload("CANC"), NOW)["status"] == "VOID"
    assert resolve_single(prediction, payload("FT", 2, 1), NOW)["unit_result"] == "0.70"


def test_lab_transport_logging_redacts_bot_credential():
    token = "123456:fictional-secret"
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1,
                               "POST https://api.telegram.org/bot%s/sendMessage", (token,), None)
    assert SecretRedactionFilter((token,)).filter(record)
    assert token not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()
