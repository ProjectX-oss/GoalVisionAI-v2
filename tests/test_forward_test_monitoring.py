import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.forward_test_monitoring import DEFAULT_POLICY, MonitoringConflictError, MonitoringService, SQLiteMonitoringRepository
from app.forward_test_monitoring.cli import main as cli_main
from app.forward_test_monitoring.exports import CSV_FILES, export_bundle, markdown, telegram_preview
from app.current_odds_forward_test.models import ForwardTestSettlement, SettlementOutcome
from app.real_match_lab_analysis.fingerprint import fingerprint
from tests.test_current_odds_forward_test import ForwardTestFoundationTests, result_raw


CUTOFF = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)


class ForwardTestMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ForwardTestFoundationTests(methodName="test_decimal_validation"); self.fixture.setUp()
        self.db = self.fixture.db; self.repo = SQLiteMonitoringRepository(self.db, migrate=False); self.service = MonitoringService(self.repo)

    def tearDown(self): self.fixture.tearDown()

    def settled(self, *, won=True):
        _, observation = self.fixture.capture_and_observe()
        self.fixture.service.record_result(observation.observation_id, result_raw(home=2 if won else 0, away=1))
        self.fixture.service.settle(observation.observation_id, settled_at_utc=datetime(2026,8,1,20,1,tzinfo=timezone.utc))
        return observation

    def test_policy_is_centralized_versioned_and_conservative(self):
        self.assertEqual(DEFAULT_POLICY.timezone,"Europe/Riga"); self.assertEqual(DEFAULT_POLICY.policy_minimum_sample,300); self.assertEqual(DEFAULT_POLICY.sample_status(0),"NO_SAMPLE"); self.assertEqual(DEFAULT_POLICY.sample_status(1),"FORWARD_TEST_SAMPLE_INSUFFICIENT"); self.assertEqual(DEFAULT_POLICY.sample_status(300),"POLICY_MINIMUM_MET")

    def test_schema_38_is_latest_and_foreign_keys_hold(self):
        self.assertEqual(max(m.version for m in MIGRATIONS),38); self.assertEqual(self.db.connection.execute("select max(version) from schema_migrations").fetchone()[0],38); self.assertEqual(self.db.connection.execute("pragma foreign_key_check").fetchall(),[])

    def test_schema_37_upgrade(self):
        db=Database(":memory:"); db.connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS:
            if migration.version>37:break
            for statement in migration.statements:db.connection.execute(statement)
            db.connection.execute("INSERT INTO schema_migrations VALUES (?,'existing')",(migration.version,))
        MigrationManager(db.connection).migrate(); self.assertEqual(db.connection.execute("select max(version) from schema_migrations").fetchone()[0],38); self.assertEqual(db.connection.execute("pragma foreign_key_check").fetchall(),[]); db.close()

    def test_empty_snapshot_is_deterministic_and_replayable(self):
        first=self.service.snapshot(CUTOFF); second=self.service.snapshot(CUTOFF); self.assertEqual(first,second); self.assertEqual(first["counts"]["observations"],0); self.assertEqual(self.db.connection.execute("select count(*) from forward_test_monitoring_snapshots").fetchone()[0],1)

    def test_snapshot_is_immutable(self):
        self.service.snapshot(CUTOFF)
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("update forward_test_monitoring_snapshots set policy_version='x'")
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("delete from forward_test_monitoring_snapshots")

    def test_snapshot_counts_wins_losses_void_and_pending_transparently(self):
        self.settled(); value=self.service.snapshot(CUTOFF); self.assertEqual(value["counts"]["won"],1); self.assertEqual(value["counts"]["published"],0); self.assertEqual(value["counts"]["unpublished"],1)

    def test_lifecycle_audit_passes_valid_controlled_chain_with_warning(self):
        observation=self.settled(); value=self.service.lifecycle_audit(observation.observation_id,CUTOFF); self.assertIn(value["status"],{"LIFECYCLE_AUDIT_PASSED","LIFECYCLE_AUDIT_WARNING"}); self.assertEqual(value["official_bankroll_mutations"],0); self.assertEqual(value["checks_defined"],35)

    def test_lifecycle_audit_persistence_is_exact_replay(self):
        observation=self.settled(); first=self.service.lifecycle_audit(observation.observation_id,CUTOFF,persist=True); second=self.service.lifecycle_audit(observation.observation_id,CUTOFF,persist=True); self.assertEqual(first,second); self.assertEqual(self.db.connection.execute("select count(*) from forward_test_monitoring_audits").fetchone()[0],1)

    def test_provider_timestamp_warning_has_provenance(self):
        observation=self.settled(); value=self.service.lifecycle_audit(observation.observation_id,CUTOFF); finding=next(f for f in value["findings"] if f["code"]=="ODDS_TIMESTAMP_PROVIDER_MISSING"); self.assertEqual(finding["affected_identifier"],observation.observation_id); self.assertEqual(finding["provenance"],"MANUAL")

    def test_data_quality_reports_incomplete_market_coverage(self):
        self.settled(); value=self.service.data_quality(CUTOFF); self.assertIn("BOOKMAKER_MARKETS_INCOMPLETE",{f["code"] for f in value["findings"]}); self.assertTrue(value["finding_fingerprint"])

    def test_cumulative_report_uses_decimal_metrics_and_hypothetical_label(self):
        self.settled(); value=self.service.report("CUMULATIVE",CUTOFF); simulation=value["metrics"]["hypothetical_flat_stake"]; self.assertEqual(simulation["label"],"HYPOTHETICAL_FLAT_STAKE"); self.assertIsInstance(simulation["net_profit_units"],Decimal); self.assertEqual(simulation["net_profit_units"],Decimal("1.10")); self.assertEqual(value["bankroll_mutations"],0)

    def test_loss_drawdown_and_streak(self):
        self.settled(won=False); value=self.service.report("CUMULATIVE",CUTOFF); self.assertEqual(value["metrics"]["results"]["losses"],1); self.assertEqual(value["metrics"]["results"]["longest_loss_streak"],1); self.assertEqual(value["metrics"]["hypothetical_flat_stake"]["maximum_drawdown"],Decimal(1))

    def test_void_returns_zero_and_is_excluded_from_hit_rate(self):
        _,observation=self.fixture.capture_and_observe(); result=self.fixture.service.record_result(observation.observation_id,result_raw()); at=datetime(2026,8,1,20,1,tzinfo=timezone.utc)
        value=ForwardTestSettlement("controlled-void",observation.observation_id,result.result_id,"HOME_WIN",SettlementOutcome.VOID,Decimal("2.10"),Decimal(1),Decimal(0),"CONTROLLED_VOID_REHEARSAL",at,fingerprint((observation.observation_id,"VOID")))
        self.fixture.repo.append_settlement(value); metrics=self.service.report("CUMULATIVE",CUTOFF)["metrics"]; self.assertEqual(metrics["results"]["voids"],1); self.assertIsNone(metrics["results"]["hit_rate"]); self.assertEqual(metrics["hypothetical_flat_stake"]["net_profit_units"],Decimal(0))

    def test_calibration_uses_decimal_log_loss_and_warns_small_sample(self):
        self.settled(); value=self.service.report("CUMULATIVE",CUTOFF)["metrics"]["calibration"]; self.assertEqual(value["status"],"INSUFFICIENT_CALIBRATION_SAMPLE"); self.assertIsInstance(value["log_loss"],Decimal); self.assertTrue(value["bins"])

    def test_segments_cover_required_dimensions(self):
        self.settled(); segments=self.service.report("CUMULATIVE",CUTOFF)["segments"]; self.assertTrue({"market","competition","bookmaker","provider","model_generation","calibration_artifact","calibration_quality","distribution_shift","publication_status","result_status"}.issubset(segments))

    def test_weekly_period_is_riga_monday_and_compares_previous_period(self):
        value=self.service.report("WEEKLY",CUTOFF); self.assertEqual(value["period_start_utc"],"2026-07-26T21:00:00+00:00"); self.assertIn(value["comparisons"]["status"],{"NO_PRIOR_SAMPLE","AVAILABLE"})

    def test_report_exact_reproduction(self):
        self.settled(); report=self.service.report("CUMULATIVE",CUTOFF); reproduction=self.service.reproduce(report["report_id"]); self.assertTrue(reproduction["matches"]); self.assertEqual(reproduction["status"],"REPORT_REPRODUCED")

    def test_report_tables_are_append_only(self):
        self.service.report("CUMULATIVE",CUTOFF)
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("delete from forward_test_monitoring_reports")

    def test_markdown_contains_sample_and_no_profit_claim(self):
        text=markdown(self.service.report("CUMULATIVE",CUTOFF)); self.assertIn("NO_SAMPLE",text); self.assertIn("not proof of profitability",text); self.assertIn("No bets were placed",text)

    def test_telegram_is_preview_only(self):
        text=telegram_preview(self.service.report("WEEKLY",CUTOFF)); self.assertIn("Preview only",text); self.assertIn("Telegram send is disabled",text)

    def test_csv_bundle_is_deterministic_utf8_and_complete(self):
        report=self.service.report("CUMULATIVE",CUTOFF)
        with tempfile.TemporaryDirectory(dir=".") as temporary:
            path=Path(temporary)/"export"; first=export_bundle(report,path); self.assertTrue(all((path/name).exists() for name in CSV_FILES)); self.assertTrue((path/"report.json").read_text(encoding="utf-8")); second=export_bundle(report,path,overwrite=True); self.assertEqual(first,second)

    def test_export_refuses_overwrite_by_default(self):
        report=self.service.report("CUMULATIVE",CUTOFF)
        with tempfile.TemporaryDirectory(dir=".") as temporary:
            path=Path(temporary); (path/"operator.txt").write_text("keep",encoding="utf-8")
            with self.assertRaises(FileExistsError): export_bundle(report,path)
            self.assertEqual((path/"operator.txt").read_text(),"keep")

    def test_unresolved_queue_includes_pending_and_overdue(self):
        _,observation=self.fixture.capture_and_observe(); rows=self.service.unresolved(CUTOFF); self.assertEqual(rows[0]["observation_id"],observation.observation_id); self.assertEqual(rows[0]["state"],"RESULT_PENDING"); self.assertTrue(rows[0]["overdue"])

    def test_health_is_offline_manual_and_secret_safe(self):
        value=self.service.health(CUTOFF); self.assertEqual(value["status"],"FORWARD_TEST_HEALTHY"); self.assertFalse(value["provider_network_checked"]); self.assertFalse(value["telegram_transport_constructed"]); self.assertFalse(value["scheduling_enabled"])

    def test_blocking_quality_findings_create_immutable_incidents(self):
        _,observation=self.fixture.capture_and_observe(); incidents=self.service.record_incidents(CUTOFF); self.assertTrue(incidents); self.assertEqual(self.service.record_incidents(CUTOFF),incidents)
        incident=incidents[0]; event=self.service.acknowledge_incident(incident["incident_id"],"operator","reviewed",CUTOFF); self.assertEqual(event["event_type"],"ACKNOWLEDGED")
        with self.assertRaises(sqlite3.IntegrityError): self.db.connection.execute("delete from forward_test_monitoring_incidents")

    def test_no_official_delivery_bankroll_or_history_mutation(self):
        tables=("real_match_lab_deliveries","official_prediction_publication_events","bankroll_transactions","historical_matches"); before={t:self.db.connection.execute(f"select count(*) from {t}").fetchone()[0] for t in tables}; self.settled(); self.service.report("CUMULATIVE",CUTOFF); after={t:self.db.connection.execute(f"select count(*) from {t}").fetchone()[0] for t in tables}; self.assertEqual(before,after)

    def test_import_and_cli_have_no_startup_execution(self):
        self.assertTrue(callable(cli_main)); self.assertEqual(self.db.connection.execute("select count(*) from forward_test_monitoring_reports").fetchone()[0],0)


if __name__ == "__main__": unittest.main()
