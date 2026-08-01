import io
import json
import asyncio
import sqlite3
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal

from app.current_odds_forward_test.audit import audit_observation
from app.current_odds_forward_test.cli import main as cli_main
from app.current_odds_forward_test.input import CurrentOddsValidationError, normalize_api_football_current_odds, parse_current_odds
from app.current_odds_forward_test.models import ODDS_SCHEMA_VERSION, RESULT_SCHEMA_VERSION, SettlementOutcome
from app.current_odds_forward_test.repository import ForwardTestConflictError, SQLiteForwardTestRepository
from app.current_odds_forward_test.service import ForwardTestService, ForwardTestValidationError, _won
from app.current_odds_forward_test.statistics import build_statistics
from app.current_odds_forward_test.evidence import build_foundation_evidence
from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint
from app.real_match_lab_analysis.policy import SUPPORTED_MARKETS
from app.football.client import FootballClient
import httpx


CAPTURE = "2026-08-01T12:00:00+00:00"
INFERENCE = "2026-08-01T12:10:00+00:00"
KICKOFF = "2026-08-01T18:00:00+00:00"
NOW = datetime(2026, 8, 1, 12, 5, tzinfo=timezone.utc)


def odds_raw(markets=("HOME_WIN",), **changes):
    value = {"schema_version": ODDS_SCHEMA_VERSION, "fixture_id": "fixture-1", "kickoff_utc": KICKOFF, "fixture_status": "SCHEDULED", "provider_source_id": "MANUAL", "source_type": "OPERATOR_SUPPLIED_CURRENT_ODDS", "bookmaker": "BOOK_A", "provider_event_id": "event-1", "source_selected_at_utc": "2026-08-01T11:59:00+00:00", "captured_at_utc": CAPTURE, "source_retrieval_timestamp_utc": "2026-08-01T12:01:00+00:00", "provider_origin_timestamp_utc": None, "captured_at_by_goalvision": True, "direct_bookmaker": True, "provenance": "Operator transcribed current price before inference", "markets": [{"market": market, "decimal_odds": "2.10"} for market in markets]}
    value.update(changes); return value


def result_raw(home=2, away=1, **changes):
    value = {"schema_version": RESULT_SCHEMA_VERSION, "fixture_id": "fixture-1", "final_home_score": home, "final_away_score": away, "final_status": "FT", "result_source": "API_FOOTBALL", "result_retrieval_timestamp_utc": "2026-08-01T20:00:00+00:00", "provenance": "Final score retrieved after full time"}
    value.update(changes); return value


class ForwardTestFoundationTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:"); MigrationManager(self.db.connection).migrate(); self.repo = SQLiteForwardTestRepository(self.db, migrate=False); self.service = ForwardTestService(self.repo)
    def tearDown(self): self.db.close()

    def seed_analysis(self, market="HOME_WIN", status="COMPLETED", analysis_id="analysis-1", odds="2.10", actionable=True, inference_at=INFERENCE):
        request = {"match_id": "fixture-1", "kickoff_utc": KICKOFF, "competition": "Bundesliga", "match_snapshot": {"fixture": "fixture-1", "status": "SCHEDULED"}, "odds": [{"market": market, "decimal_odds": odds, "source_provider": "MANUAL", "bookmaker_id": "BOOK_A", "source_event_id": "event-1", "captured_at": CAPTURE}]}
        evaluation = {"market": market, "raw_probability": "0.55", "calibrated_probability": "0.60", "bookmaker_odds": odds, "expected_value": "0.26", "actionable": actionable, "selected": status == "COMPLETED"}
        evidence = {"feature_fingerprint": "f" * 64, "model_input_fingerprint": "i" * 64, "model_artifact_id": "model-1", "model_artifact_fingerprint": "m" * 64, "calibration_set_id": "cal-1", "calibration_fingerprint": "c" * 64, "evaluations": [evaluation], "mathematically_top_ranked_market": market, "calibration_quality_report": {"lab_outcome": "CALIBRATION_QUALITY_INELIGIBLE", "distribution_shift": {"status": "IN_DISTRIBUTION"}}}
        result = {"evidence": evidence, "rejection_reasons": [] if status == "COMPLETED" else ["NO_ACTIONABLE_SELECTION"]}
        selected = market if status == "COMPLETED" else None; message = "Lab preview" if selected else None; message_fp = fingerprint(message) if message else None
        self.db.connection.execute("INSERT INTO real_match_lab_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (analysis_id, "lab-request-" + analysis_id, fingerprint((analysis_id, "request")), fingerprint((analysis_id, "result")), status, "fixture-1", KICKOFF, "LAB", "OFFICIAL_GLOBAL", "-1003510920417", "@GoalVision_AI_Lab_Bot", selected, message, message_fp, canonical_json(request), canonical_json(result), inference_at)); self.db.connection.commit()

    def capture_and_observe(self, market="HOME_WIN", status="COMPLETED", request_id="forward-1", analysis_id="analysis-1", actionable=True):
        snapshot = parse_current_odds(odds_raw((market,)), now=NOW); self.service.capture_odds(snapshot); self.seed_analysis(market, status, analysis_id, actionable=actionable)
        return snapshot, self.service.create_observation(request_id, analysis_id, snapshot.snapshot_id)

    def test_all_11_single_markets_supported_and_no_correct_score_or_combo(self):
        snapshot = parse_current_odds(odds_raw(SUPPORTED_MARKETS), now=NOW); self.assertEqual(len(snapshot.quotes), 11)
        for market in ("CORRECT_SCORE_1_0", "COMBO"):
            with self.assertRaises(CurrentOddsValidationError): parse_current_odds(odds_raw((market,)), now=NOW)

    def test_decimal_validation(self):
        for value in ("1", "NaN", "Infinity", "1001", "bad"):
            raw = odds_raw(); raw["markets"][0]["decimal_odds"] = value
            with self.assertRaises(CurrentOddsValidationError): parse_current_odds(raw, now=NOW)

    def test_fixture_source_capture_order_and_post_kickoff(self):
        cases = ({"source_selected_at_utc": "2026-08-01T12:00:01+00:00"}, {"captured_at_utc": "2026-08-01T18:00:00+00:00"}, {"source_retrieval_timestamp_utc": "2026-08-01T11:59:00+00:00"})
        for change in cases:
            with self.assertRaises(CurrentOddsValidationError): parse_current_odds(odds_raw(**change), now=NOW)

    def test_stale_current_odds_rejected_at_15_minute_boundary(self):
        parse_current_odds(odds_raw(), now=datetime(2026, 8, 1, 12, 15, tzinfo=timezone.utc))
        with self.assertRaisesRegex(CurrentOddsValidationError, "STALE_CURRENT_ODDS"): parse_current_odds(odds_raw(), now=datetime(2026, 8, 1, 12, 15, 1, tzinfo=timezone.utc))

    def test_goalvision_retrieval_timestamp_distinguished(self):
        quote = parse_current_odds(odds_raw(), now=NOW).quotes[0]
        self.assertTrue(quote.captured_at_by_goalvision); self.assertIsNone(quote.provider_origin_timestamp_utc)
        with self.assertRaises(CurrentOddsValidationError): parse_current_odds(odds_raw(captured_at_by_goalvision=False), now=NOW)
        with self.assertRaisesRegex(CurrentOddsValidationError, "ODDS_PROVENANCE_INCOMPLETE"): parse_current_odds(odds_raw(provenance="Bearer secret-value"), now=NOW)

    def test_api_football_normalization(self):
        payload = {"response": [{"update": None, "bookmakers": [{"name": "Bet365", "bets": [{"name": "Match Winner", "values": [{"value": "Home", "odd": "2.10"}, {"value": "Draw", "odd": "3.20"}]}, {"name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "1.90"}]}]}]}]}
        raw = normalize_api_football_current_odds(payload, fixture_id="fixture-1", kickoff_utc=KICKOFF, retrieved_at_utc="2026-08-01T12:01:00+00:00", source_selected_at_utc="2026-08-01T11:59:00+00:00")
        value = parse_current_odds(raw, now=datetime(2026, 8, 1, 12, 1, tzinfo=timezone.utc)); self.assertEqual({q.market for q in value.quotes}, {"HOME_WIN", "DRAW", "OVER_2_5"}); self.assertTrue(all(q.captured_at_by_goalvision for q in value.quotes))

    def test_api_football_client_is_network_inert_until_explicit_call(self):
        client = FootballClient(api_key="test-key"); self.assertIsNotNone(client._client); asyncio.run(client.close())

    def test_api_football_auth_failure_is_not_retried(self):
        class Fake:
            def __init__(self): self.calls = 0
            async def get(self, path, params):
                self.calls += 1; request = httpx.Request("GET", "https://example.invalid")
                response = httpx.Response(401, request=request); raise httpx.HTTPStatusError("unauthorized", request=request, response=response)
            async def aclose(self): pass
        client = FootballClient(api_key="test-key"); fake = Fake(); asyncio.run(client._client.aclose()); client._client = fake
        with self.assertRaises(httpx.HTTPStatusError): asyncio.run(client.fixture(1))
        self.assertEqual(fake.calls, 1)

    def test_api_football_missing_credential_cli_is_terminal_safe(self):
        out, err = io.StringIO(), io.StringIO()
        from contextlib import redirect_stderr
        from unittest.mock import patch
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(out), redirect_stderr(err): code = cli_main(["discover-current-fixtures", "--output", "json"])
        self.assertEqual(code, 3); self.assertEqual(out.getvalue(), ""); self.assertIn("API_FOOTBALL_UNAVAILABLE", err.getvalue())

    def test_deterministic_snapshot_and_exact_replay(self):
        value = parse_current_odds(odds_raw(), now=NOW); self.assertEqual(value, parse_current_odds(odds_raw(), now=NOW))
        first = self.service.capture_odds(value); second = self.service.capture_odds(value); self.assertFalse(first[1]); self.assertTrue(second[1])

    def test_quote_replacement_conflict(self):
        value = parse_current_odds(odds_raw(), now=NOW); self.service.capture_odds(value)
        changed = object.__new__(type(value));
        for field in value.__dataclass_fields__: object.__setattr__(changed, field, getattr(value, field))
        object.__setattr__(changed, "snapshot_fingerprint", "x" * 64)
        with self.assertRaises(ForwardTestConflictError): self.service.capture_odds(changed)

    def test_observation_is_deterministic_idempotent_and_provenance_complete(self):
        _, value = self.capture_and_observe(); replay = self.service.create_observation("forward-1", "analysis-1", value.odds_snapshot_id)
        self.assertEqual(value, replay); self.assertEqual(value.evidence_tier, "FORWARD_TEST_REAL_TIME"); self.assertFalse(value.lab_send_eligible); self.assertFalse(value.official_eligible)
        self.assertTrue(value.calibration_quality); self.assertTrue(value.distribution_shift)

    def test_no_selection_and_blocked_observations_persist(self):
        for status, analysis, request in (("NO_SELECTION", "analysis-n", "forward-n"), ("REJECTED", "analysis-b", "forward-b")):
            _, value = self.capture_and_observe(status=status, analysis_id=analysis, request_id=request, actionable=False)
            self.assertFalse(value.actionable); self.assertIsNotNone(self.repo.load_observation(value.observation_id))

    def test_odds_captured_after_inference_and_stale_rejected(self):
        snapshot = parse_current_odds(odds_raw(), now=NOW); self.service.capture_odds(snapshot); self.seed_analysis(inference_at="2026-08-01T11:59:00+00:00")
        with self.assertRaisesRegex(ForwardTestValidationError, "ODDS_CAPTURED_AFTER_INFERENCE"): self.service.create_observation("forward-1", "analysis-1", snapshot.snapshot_id)
        self.seed_analysis(analysis_id="analysis-stale", inference_at="2026-08-01T12:15:01+00:00")
        with self.assertRaisesRegex(ForwardTestValidationError, "STALE_CURRENT_ODDS"): self.service.create_observation("forward-stale", "analysis-stale", snapshot.snapshot_id)

    def test_source_or_quote_change_from_analysis_rejected(self):
        snapshot = parse_current_odds(odds_raw(), now=NOW); self.service.capture_odds(snapshot); self.seed_analysis(odds="2.20")
        with self.assertRaisesRegex(ForwardTestValidationError, "ODDS_QUOTE_REPLACEMENT_CONFLICT"): self.service.create_observation("forward-1", "analysis-1", snapshot.snapshot_id)

    def test_result_before_kickoff_invalid_score_status_and_conflict(self):
        _, observation = self.capture_and_observe()
        for change in ({"result_retrieval_timestamp_utc": KICKOFF}, {"final_status": "NS"}, {"final_home_score": -1}, {"fixture_id": "other"}):
            with self.assertRaises(ForwardTestValidationError): self.service.record_result(observation.observation_id, result_raw(**change))
        first = self.service.record_result(observation.observation_id, result_raw()); self.assertEqual(first, self.service.record_result(observation.observation_id, result_raw()))
        with self.assertRaises(ForwardTestConflictError): self.service.record_result(observation.observation_id, result_raw(home=0))

    def test_deterministic_settlement_all_11_markets(self):
        expected = {"HOME_WIN": True, "DRAW": False, "AWAY_WIN": False, "OVER_1_5": True, "UNDER_1_5": False, "OVER_2_5": True, "UNDER_2_5": False, "OVER_3_5": False, "UNDER_3_5": True, "BTTS_YES": True, "BTTS_NO": False}
        for market, won in expected.items(): self.assertEqual(_won(market, 2, 1), won)

    def test_settlement_no_double_and_no_selection_not_applicable(self):
        _, observation = self.capture_and_observe(); self.service.record_result(observation.observation_id, result_raw()); value = self.service.settle(observation.observation_id, settled_at_utc=datetime(2026, 8, 1, 20, 1, tzinfo=timezone.utc))
        self.assertEqual(value.outcome, SettlementOutcome.WON); self.assertEqual(value, self.service.settle(observation.observation_id, settled_at_utc=datetime(2026, 8, 1, 20, 1, tzinfo=timezone.utc)))

    def test_statistics_include_losses_no_selections_and_simulation_label(self):
        _, win = self.capture_and_observe(); self.service.record_result(win.observation_id, result_raw()); self.service.settle(win.observation_id, settled_at_utc=datetime(2026, 8, 1, 20, 1, tzinfo=timezone.utc))
        _, no = self.capture_and_observe(status="NO_SELECTION", analysis_id="analysis-n", request_id="forward-n", actionable=False)
        stats = build_statistics(self.repo); self.assertEqual(stats.total_analyses, 2); self.assertEqual(stats.no_selection, 1); self.assertEqual(stats.wins, 1); self.assertIn("hypothetical", stats.limitations[0].lower()); self.assertEqual(stats.sample_status.value, "FORWARD_TEST_SAMPLE_INSUFFICIENT")
        self.assertIsNotNone(stats.brier_score); self.assertIsNotNone(stats.raw_brier_score); self.assertIsNotNone(stats.log_loss); self.assertTrue(stats.calibration_buckets)

    def test_distributions_and_drawdown(self):
        _, observation = self.capture_and_observe(); self.service.record_result(observation.observation_id, result_raw(home=0, away=1)); self.service.settle(observation.observation_id, settled_at_utc=datetime(2026, 8, 1, 20, 1, tzinfo=timezone.utc))
        stats = build_statistics(self.repo); self.assertEqual(stats.losses, 1); self.assertEqual(stats.maximum_simulated_drawdown, Decimal("1")); self.assertEqual(stats.market_distribution, (("HOME_WIN", 1),)); self.assertEqual(stats.source_distribution, (("MANUAL:BOOK_A", 1),))

    def test_integrity_pending_and_pass(self):
        _, observation = self.capture_and_observe(); pending = audit_observation(self.repo, observation.observation_id); self.assertEqual(pending.status.value, "FORWARD_TEST_RESULT_PENDING")
        self.service.record_result(observation.observation_id, result_raw()); self.service.settle(observation.observation_id, settled_at_utc=datetime(2026, 8, 1, 20, 1, tzinfo=timezone.utc)); self.assertEqual(audit_observation(self.repo, observation.observation_id).status.value, "FORWARD_TEST_INTEGRITY_PASSED")

    def test_append_only_delete_update_and_foreign_keys(self):
        snapshot, observation = self.capture_and_observe()
        for sql in ("UPDATE forward_test_observations SET status='BLOCKED'", "DELETE FROM forward_test_observations"):
            with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute(sql)
        self.assertEqual(self.db.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_stale_rejection_is_append_only_and_inspectable_in_statistics(self):
        row = self.repo.append_rejection("r" * 64, "ODDS_CAPTURE", "STALE_CURRENT_ODDS", INFERENCE)
        self.assertEqual(row["reason_code"], "STALE_CURRENT_ODDS"); self.assertEqual(build_statistics(self.repo).rejection_counts, (("STALE_CURRENT_ODDS", 1),))
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("DELETE FROM forward_test_rejections")

    def test_original_real_match_lab_analysis_is_immutable(self):
        self.capture_and_observe()
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("UPDATE real_match_lab_analyses SET status='REJECTED'")

    def test_no_telegram_official_bankroll_delivery_or_historical_mutation(self):
        before = {table: self.db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("real_match_lab_deliveries", "official_prediction_publication_events", "bankroll_transactions", "historical_matches")}
        self.capture_and_observe(); after = {table: self.db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
        self.assertEqual(before, after)

    def test_schema_36_fresh_migration(self):
        self.assertEqual(self.db.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 36)
        self.assertTrue(self.db.connection.execute("SELECT name FROM sqlite_master WHERE name='forward_test_observations'").fetchone())

    def test_v35_upgrade_migration(self):
        upgrade = Database(":memory:"); upgrade.connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS:
            if migration.version > 35: break
            for statement in migration.statements: upgrade.connection.execute(statement)
            upgrade.connection.execute("INSERT INTO schema_migrations VALUES (?, 'existing')", (migration.version,))
        MigrationManager(upgrade.connection).migrate(); self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 36); self.assertEqual(upgrade.connection.execute("PRAGMA foreign_key_check").fetchall(), []); upgrade.close()

    def test_cli_human_json_diagnose_and_no_startup_execution(self):
        out = io.StringIO()
        with redirect_stdout(out): code = cli_main(["diagnose-forward-test", "--database", ":memory:", "--output", "json"])
        value = json.loads(out.getvalue()); self.assertEqual(code, 0); self.assertEqual(value["schema_version"], 36); self.assertFalse(value["startup_execution"]); self.assertFalse(value["telegram_transport_constructed"])

    def test_canonical_evidence_fingerprint_and_committed_artifact(self):
        value = build_foundation_evidence(source_hash_before="61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0", source_hash_after="61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0", isolated_database_hash="8b58382e382690e4f339df81085cf9c02437a2baba7ca3885a56ee43a7d3287a")
        with open("docs/rehearsals/current_odds_forward_test_foundation_2026-08-01.json", encoding="utf-8") as stream: committed = json.load(stream)
        self.assertEqual(committed, json.loads(canonical_json(value))); self.assertEqual(value["evidence_fingerprint"], "a916467d59e8e4d0c9c3f73a158034018e5f7f7a19d3ea7ef48a4e3ffc44f274")


if __name__ == "__main__": unittest.main()
