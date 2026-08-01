"""Regression coverage for the 48 First-Lab operational acceptance categories."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.current_odds_forward_test.input import parse_current_odds
from app.current_odds_forward_test.operations import (
    FirstLabOperationsRepository, build_lab_preview, build_pro_readiness,
    build_publication_review, build_result_preview,
    validate_manual_send_authorization,
)
from app.current_odds_forward_test.repository import ForwardTestConflictError, SQLiteForwardTestRepository
from app.current_odds_forward_test.service import ForwardTestService
from app.current_odds_forward_test.statistics import build_statistics
from app.current_odds_forward_test.workflow import FirstLabDryRunWorkflow
from app.database import Database
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint
from app.real_match_lab_analysis.models import LAB_BOT_USERNAME, LAB_CHAT_ID, SEND_CONFIRMATION


NOW = datetime(2026, 8, 11, 12, 10, tzinfo=timezone.utc)
CAPTURE = NOW - timedelta(minutes=5)
KICKOFF = NOW + timedelta(hours=4)


def readiness(status="PRO_PLAN_READY"):
    return {"status": status, "ready_for_genuine_forward_test": status == "PRO_PLAN_READY", "capability_cache": {"status": "VALID", "fingerprint": "c" * 64}}


def odds_contract(captured=CAPTURE):
    return {"schema_version": "goalvision-current-odds-snapshot-v1", "fixture_id": "101", "kickoff_utc": KICKOFF.isoformat(), "fixture_status": "SCHEDULED", "provider_source_id": "API_FOOTBALL", "source_type": "API_FOOTBALL_CURRENT_ODDS", "bookmaker": "Book A", "provider_event_id": "101", "source_selected_at_utc": (captured-timedelta(seconds=1)).isoformat(), "captured_at_utc": captured.isoformat(), "source_retrieval_timestamp_utc": captured.isoformat(), "provider_origin_timestamp_utc": captured.isoformat(), "captured_at_by_goalvision": False, "direct_bookmaker": True, "provenance": "API-Football current exact fixture odds", "markets": [{"market": "HOME_WIN", "decimal_odds": "2.10"}, {"market": "DRAW", "decimal_odds": "3.20"}, {"market": "OVER_2_5", "decimal_odds": "1.90"}]}


def selected_fixture(captured=CAPTURE):
    raw = odds_contract(captured)
    snapshot = parse_current_odds(raw, now=captured)
    form = {"match_count": 5, "wins": 3, "draws": 1, "losses": 1, "goals_scored": 9, "goals_conceded": 5, "clean_sheets": 2, "failed_to_score": 0}
    return {"provider_fixture_id": 101, "fixture_selected_at_utc": (captured-timedelta(seconds=1)).isoformat(), "competition_id": 39, "competition": "Premier League", "season": 2026, "home_team_id": 1, "home_team": "Alpha", "away_team_id": 2, "away_team": "Beta", "kickoff_utc": KICKOFF.isoformat(), "venue_name": "Ground", "api_retrieval_timestamp_utc": captured.isoformat(), "provider_update_timestamp_utc": captured.isoformat(), "odds_contract": raw, "odds_snapshot_id": snapshot.snapshot_id, "feature_baseline": {"home_recent_matches": 5, "away_recent_matches": 5, "home_recent_form": form, "away_recent_form": form}}


class FakeAnalyzer:
    def __init__(self, database, *, controlled=True, actionable=True, probability="0.60"):
        self.database = database; self.controlled = controlled; self.actionable = actionable; self.probability = probability; self.calls = 0

    def __call__(self, command):
        self.calls += 1
        market = "HOME_WIN"
        evaluation = {"market": market, "raw_probability": "0.58", "calibrated_probability": self.probability, "fair_odds": "1.67", "bookmaker_odds": "2.10", "expected_value": "0.26", "confidence": "MEDIUM", "actionable": self.actionable, "selected": self.actionable}
        quality = {"controlled_synthetic": self.controlled, "lab_outcome": "CALIBRATION_QUALITY_ACCEPTABLE", "send_eligible": True, "distribution_shift": {"status": "DISTRIBUTION_SHIFT_ACCEPTABLE", "completeness": "1.0"}}
        evidence = {"feature_fingerprint": "f"*64, "model_input_fingerprint": "i"*64, "model_artifact_id": "live-78", "model_artifact_fingerprint": "m"*64, "calibration_set_id": "cal-1", "calibration_fingerprint": "c"*64, "evaluations": [evaluation], "mathematically_top_ranked_market": market, "calibration_quality_report": quality, "send_eligible": not self.controlled}
        status = "COMPLETED" if self.actionable else "NO_SELECTION"; selected = market if self.actionable else None
        result = {"evidence": evidence, "rejection_reasons": [] if self.actionable else ["NO_ACTIONABLE_SELECTION"]}
        request = json.loads(canonical_json(command)); message = "🧪 GoalVision AI Lab\nExperimental; no guarantee." if self.actionable else None; message_fp = fingerprint(message) if message else None
        analysis_id = "analysis-" + fingerprint(command.request_id)
        self.database.connection.execute("INSERT OR IGNORE INTO real_match_lab_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (analysis_id, command.request_id, fingerprint(command), fingerprint(result), status, command.match_id, command.kickoff_utc.isoformat(), "LAB", "OFFICIAL_GLOBAL", LAB_CHAT_ID, LAB_BOT_USERNAME, selected, message, message_fp, canonical_json(request), canonical_json(result), command.collected_at.isoformat()))
        self.database.connection.commit()
        return SimpleNamespace(analysis_id=analysis_id, status=SimpleNamespace(value=status), result_fingerprint=fingerprint(result))


class FirstLabOperationalReadinessTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:"); self.ops = FirstLabOperationsRepository(self.db); self.repo = SQLiteForwardTestRepository(self.db, migrate=False)

    def tearDown(self): self.db.close()

    def run_workflow(self, *, status="PRO_PLAN_READY", controlled=True, actionable=True, captured=CAPTURE, run_id="run-1"):
        analyzer = FakeAnalyzer(self.db, controlled=controlled, actionable=actionable)
        async def discover(): return {"terminal_result": "CURRENT_FIXTURE_SELECTED", "candidate_fixture_count": 1, "api_call_count": 7, "selected_fixture": selected_fixture(captured)}
        result = asyncio.run(FirstLabDryRunWorkflow(self.ops, self.repo, analyzer).run(run_id=run_id, readiness=readiness(status), discover=discover, parameters={"max_calls": 40}, now=NOW, mode="CONTROLLED_REHEARSAL" if controlled else "GENUINE"))
        return result, analyzer

    def test_01_free_plan_blocks_before_discovery(self):
        called = False
        async def discover():
            nonlocal called; called = True; return {}
        result = asyncio.run(FirstLabDryRunWorkflow(self.ops, self.repo, FakeAnalyzer(self.db)).run(run_id="free", readiness=readiness("FREE_PLAN_CURRENT_SEASON_BLOCKED"), discover=discover, parameters={}, now=NOW))
        self.assertFalse(called); self.assertEqual(result["status"], "FREE_PLAN_CURRENT_SEASON_BLOCKED")

    def test_02_pro_ready_proceeds_and_orders_fixture_odds_before_analysis(self):
        result, analyzer = self.run_workflow()
        names = [item["stage_name"] for item in result["stages"]]
        self.assertLess(names.index("CANDIDATE_SELECTED"), names.index("ANALYSIS_COMPLETED")); self.assertLess(names.index("ODDS_CAPTURED"), names.index("ANALYSIS_COMPLETED")); self.assertEqual(analyzer.calls, 1)

    def test_03_no_credential_leak_and_offline_no_network(self):
        with patch("app.current_odds_forward_test.operations.api_football_credential_status", return_value="CONFIGURED"):
            report = build_pro_readiness(env_file=Path("missing"), cache_path=Path("missing"), now=NOW)
        self.assertFalse(report["secret_fields_present"]); self.assertNotIn("key", canonical_json(report).lower()); self.assertEqual(report["network_verification"], "NOT_EXECUTED")

    def test_04_readiness_typed_outcomes(self):
        with patch("app.current_odds_forward_test.operations.api_football_credential_status", return_value="NOT_CONFIGURED"):
            self.assertEqual(build_pro_readiness(now=NOW)["status"], "CONFIGURATION_INCOMPLETE")
        with patch("app.current_odds_forward_test.operations.api_football_credential_status", return_value="INVALID"):
            self.assertEqual(build_pro_readiness(now=NOW)["status"], "CREDENTIAL_INVALID")
        with patch("app.current_odds_forward_test.operations.api_football_credential_status", return_value="CONFIGURED"):
            self.assertEqual(build_pro_readiness(now=NOW, network_verified=True, authenticated=True, detected_plan="FREE")["status"], "FREE_PLAN_CURRENT_SEASON_BLOCKED")

    def test_05_quota_is_checked_before_discovery(self):
        result, analyzer = self.run_workflow(status="QUOTA_INSUFFICIENT", run_id="quota")
        self.assertEqual(analyzer.calls, 0); self.assertEqual(len(result["stages"]), 2)

    def test_06_checkpoint_persistence_and_recovery(self):
        result, _ = self.run_workflow(); replay, analyzer = self.run_workflow()
        self.assertEqual(result["stages"], replay["stages"]); self.assertEqual(analyzer.calls, 0); self.assertTrue(replay["recovered"]); self.assertEqual(len(self.ops.stages("run-1")), 11)

    def test_07_conflicting_replay_rejected(self):
        self.run_workflow()
        with self.assertRaises(ForwardTestConflictError):
            self.ops.begin("run-1", {"max_calls": 39}, mode="CONTROLLED_REHEARSAL", occurred_at=NOW)

    def test_08_stale_odds_not_reused(self):
        with self.assertRaisesRegex(Exception, "STALE_CURRENT_ODDS"):
            self.run_workflow(captured=NOW-timedelta(minutes=16), run_id="stale")

    def test_09_observation_and_preview_created_without_send(self):
        result, _ = self.run_workflow()
        self.assertTrue(result["observation_id"]); self.assertFalse(result["telegram_send_executed"]); self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM real_match_lab_deliveries").fetchone()[0], 0)

    def test_10_controlled_preview_is_diagnostic_and_blockers_visible(self):
        result, _ = self.run_workflow()
        self.assertEqual(result["preview"]["status"], "LAB_PREVIEW_INTERNAL_DIAGNOSTIC"); self.assertTrue(result["preview"]["quality_blockers_visible"])

    def test_11_unsupported_extreme_is_not_trusted(self):
        result, _ = self.run_workflow(controlled=False, run_id="extreme")
        obs = json.loads(self.repo.load_observation(result["observation_id"])["observation_json"]); obs["market_evaluations"][0]["calibrated_probability"] = "0.999"
        request = json.loads(self.db.connection.execute("SELECT request_snapshot FROM real_match_lab_analyses WHERE analysis_id=?", (obs["analysis_id"],)).fetchone()[0]); odds = json.loads(self.repo.load_odds(obs["odds_snapshot_id"])["snapshot_json"])
        preview = build_lab_preview(obs, request, odds); self.assertFalse(preview["publishable"]); self.assertIn("WITHHELD", preview["message_html"])

    def test_12_publication_review_blocks_synthetic_and_never_sends(self):
        result, _ = self.run_workflow(); report = build_publication_review(self.repo, result["observation_id"], reviewed_at=NOW, persist=self.ops)
        self.assertEqual(report["status"], "LAB_PUBLICATION_REVIEW_BLOCKED"); self.assertIn("CALIBRATION_EVIDENCE_PRODUCTION", report["blocker_codes"]); self.assertFalse(report["telegram_send_executed"])

    def test_13_publication_review_passes_production_evidence(self):
        result, _ = self.run_workflow(controlled=False); report = build_publication_review(self.repo, result["observation_id"], reviewed_at=NOW, persist=self.ops)
        self.assertEqual(report["status"], "LAB_PUBLICATION_REVIEW_PASSED"); self.assertTrue(report["review_fingerprint"])

    def test_14_wrong_destination_confirmation_and_message_rejected(self):
        result, _ = self.run_workflow(controlled=False); obs = json.loads(self.repo.load_observation(result["observation_id"])["observation_json"]); review = build_publication_review(self.repo, result["observation_id"], reviewed_at=NOW, persist=self.ops)
        report = validate_manual_send_authorization(self.repo, observation_id=result["observation_id"], review_fingerprint=review["review_fingerprint"], message_fingerprint="wrong", confirmation="wrong", environment="PROD", chat_id="wrong", bot="wrong", now=NOW)
        self.assertEqual(report["status"], "LAB_MANUAL_SEND_REJECTED"); self.assertIn("WRONG_DESTINATION", report["blocker_codes"]); self.assertIn("MESSAGE_FINGERPRINT_CONFLICT", report["blocker_codes"])

    def test_15_exact_manual_send_readiness_links_all_fingerprints_but_does_not_send(self):
        result, _ = self.run_workflow(controlled=False); obs = json.loads(self.repo.load_observation(result["observation_id"])["observation_json"]); review = build_publication_review(self.repo, result["observation_id"], reviewed_at=NOW, persist=self.ops)
        report = validate_manual_send_authorization(self.repo, observation_id=result["observation_id"], review_fingerprint=review["review_fingerprint"], message_fingerprint=obs["message_fingerprint"], confirmation=SEND_CONFIRMATION, environment="LAB", chat_id=LAB_CHAT_ID, bot=LAB_BOT_USERNAME, now=NOW)
        self.assertEqual(report["status"], "LAB_MANUAL_SEND_AUTHORIZED"); self.assertFalse(report["transport_constructed"]); self.assertFalse(report["telegram_send_executed"])

    def test_16_non_actionable_observation_cannot_send(self):
        result, _ = self.run_workflow(controlled=False, actionable=False); review = build_publication_review(self.repo, result["observation_id"], reviewed_at=NOW, persist=self.ops)
        report = validate_manual_send_authorization(self.repo, observation_id=result["observation_id"], review_fingerprint=review["review_fingerprint"], message_fingerprint="", confirmation=SEND_CONFIRMATION, environment="LAB", chat_id=LAB_CHAT_ID, bot=LAB_BOT_USERNAME, now=NOW)
        self.assertIn("NON_ACTIONABLE_OBSERVATION", report["blocker_codes"])

    def test_17_result_append_settlement_preview_and_statistics_include_loss(self):
        result, _ = self.run_workflow(controlled=False); service = ForwardTestService(self.repo); oid = result["observation_id"]
        service.record_result(oid, {"schema_version": "goalvision-forward-test-result-v1", "fixture_id": "101", "final_home_score": 0, "final_away_score": 1, "final_status": "FT", "result_source": "MANUAL", "result_retrieval_timestamp_utc": (KICKOFF+timedelta(hours=2)).isoformat(), "provenance": "Operator-confirmed final score"})
        settlement = service.settle(oid, settled_at_utc=KICKOFF+timedelta(hours=2, minutes=1)); preview = build_result_preview(self.repo, oid, created_at=KICKOFF+timedelta(hours=2, minutes=2), persist=self.ops); stats = build_statistics(self.repo)
        self.assertEqual(settlement.outcome.value, "LOST"); self.assertIn("LOST", preview["message"]); self.assertEqual(stats.losses, 1); self.assertEqual(stats.sample_status.value, "FORWARD_TEST_SAMPLE_INSUFFICIENT")

    def test_18_result_and_preview_conflicts_are_rejected(self):
        result, _ = self.run_workflow(controlled=False); service = ForwardTestService(self.repo); oid = result["observation_id"]
        raw = {"schema_version": "goalvision-forward-test-result-v1", "fixture_id": "101", "final_home_score": 1, "final_away_score": 0, "final_status": "FT", "result_source": "MANUAL", "result_retrieval_timestamp_utc": (KICKOFF+timedelta(hours=2)).isoformat(), "provenance": "Final"}; service.record_result(oid, raw)
        with self.assertRaises(ForwardTestConflictError): service.record_result(oid, {**raw, "final_home_score": 2})

    def test_19_operational_tables_are_append_only_and_foreign_key_safe(self):
        self.ops.begin("append", {}, mode="CONTROLLED_REHEARSAL", occurred_at=NOW)
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("UPDATE first_lab_run_executions SET execution_state='STARTED' WHERE run_id='append'")
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("DELETE FROM first_lab_run_executions WHERE run_id='append'")
        self.assertEqual(self.db.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_20_official_bankroll_publication_activation_and_scheduling_unchanged(self):
        before = {name: self.db.connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in ("bankroll_transactions", "official_prediction_publication_events", "real_match_lab_deliveries", "model_champion_generations")}
        result, _ = self.run_workflow(); after = {name: self.db.connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in before}
        self.assertEqual(before, after); self.assertFalse(result["scheduling_enabled"])

    def test_21_deterministic_json_fingerprints_and_terminal_safe_text(self):
        result, _ = self.run_workflow(); self.assertEqual(fingerprint(result["preview"]["message_html"]), fingerprint(result["preview"]["message_html"])); result["preview"]["message_html"].encode("ascii", errors="backslashreplace")

    def test_22_schema_37_and_zero_startup_execution(self):
        self.assertEqual(self.db.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 38); self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM first_lab_run_executions").fetchone()[0], 0)

    def test_23_interrupted_after_provider_call_recovers_without_discovery(self):
        run_id = "interrupted"; parameters = {"max_calls": 40}; selected = selected_fixture()
        self.ops.begin(run_id, parameters, mode="CONTROLLED_REHEARSAL", occurred_at=NOW)
        self.ops.stage(run_id, "READINESS_CHECKED", "PASSED", readiness(), occurred_at=NOW)
        self.ops.stage(run_id, "CAPABILITIES_RESOLVED", "PASSED", readiness()["capability_cache"], occurred_at=NOW)
        self.ops.stage(run_id, "FIXTURES_DISCOVERED", "PASSED", {"terminal_result": "CURRENT_FIXTURE_SELECTED", "candidate_count": 1, "request_count": 7}, occurred_at=NOW)
        self.ops.stage(run_id, "CANDIDATE_SELECTED", "PASSED", selected, occurred_at=NOW)
        calls = 0
        async def discover():
            nonlocal calls; calls += 1; return {}
        analyzer = FakeAnalyzer(self.db)
        result = asyncio.run(FirstLabDryRunWorkflow(self.ops, self.repo, analyzer).run(run_id=run_id, readiness=readiness(), discover=discover, parameters=parameters, now=NOW, mode="CONTROLLED_REHEARSAL"))
        self.assertEqual(calls, 0); self.assertEqual(analyzer.calls, 1); self.assertEqual(result["status"], "FIRST_LAB_DRY_RUN_COMPLETED")


if __name__ == "__main__": unittest.main()
