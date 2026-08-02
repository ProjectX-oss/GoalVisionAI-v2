import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path

from app.database import Database, MigrationManager
from app.forward_test_governance import (
    DEFAULT_POLICY, GovernanceConflictError, GovernancePolicy,
    GovernanceService, evaluate_records, maturity,
)
from app.forward_test_governance.cli import main
from app.forward_test_governance.controlled import EVIDENCE_CLASS, controlled_records, run_controlled_rehearsal
from app.forward_test_governance.metrics import calibration, predictive, psi
from app.forward_test_governance.reports import build_report, csv_text, markdown, telegram_preview
from app.lab_operator_console.config import ConsoleConfig
from app.lab_operator_console.web import ConsoleApplication, NAV
from app.real_match_lab_analysis.fingerprint import fingerprint


class ForwardTestGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.path=Path(self.temporary.name)/"governance.db";self.database=Database(self.path);MigrationManager(self.database.connection).migrate()

    def tearDown(self):
        self.database.close();self.temporary.cleanup()

    def test_001_policy_is_immutable_centralized_and_fingerprinted(self):
        with self.assertRaises(FrozenInstanceError):DEFAULT_POLICY.warm_up_sample=1
        self.assertEqual(DEFAULT_POLICY.fingerprint,fingerprint(DEFAULT_POLICY));self.assertEqual(DEFAULT_POLICY.timezone,"Europe/Riga");self.assertLess(DEFAULT_POLICY.brier_warning,DEFAULT_POLICY.brier_block);self.assertLess(DEFAULT_POLICY.ece_warning,DEFAULT_POLICY.ece_block);self.assertEqual(DEFAULT_POLICY.rolling_observation_windows,(7,20,50));self.assertEqual(DEFAULT_POLICY.recovery_consecutive_evaluations,3)

    def test_002_all_sample_maturity_outcomes(self):
        expected={0:"NO_EVIDENCE",1:"GOVERNANCE_SAMPLE_INSUFFICIENT",10:"WARM_UP",20:"MONITORING",30:"REVIEWABLE",60:"POLICY_MINIMUM_MET"}
        self.assertEqual({value:maturity(value,DEFAULT_POLICY) for value in expected},expected)

    def test_003_decimal_predictive_and_calibration_metrics(self):
        rows=({"probability":"0.8","outcome":"WON"},{"probability":"0.8","outcome":"LOST"})
        pred=predictive(rows);cal=calibration(rows)
        self.assertEqual(pred["brier_score"],"0.34");self.assertEqual(pred["accuracy"],"0.5");self.assertEqual(pred["probability_bias"],"0.3");self.assertEqual(cal["ece"],"0.3");self.assertTrue(cal["overconfidence"]);self.assertEqual(cal["mce"],"0.3")

    def test_004_psi_is_deterministic_and_detects_shift(self):
        clear=psi((1,1,1),(1,1,1));shift=psi(tuple(range(20,40)),tuple(range(20)))
        self.assertEqual(clear,0);self.assertGreater(shift,DEFAULT_POLICY.psi_block);self.assertEqual(shift,psi(tuple(range(20,40)),tuple(range(20))))

    def test_005_windows_cutoff_and_scope_inclusion_are_deterministic(self):
        records=controlled_records();value=evaluate_records(records,cutoff_utc="2026-06-01T00:00:00+00:00")
        kinds={item["kind"] for item in value["windows"]};self.assertTrue({"LIFETIME","ROLLING_7_SETTLED","ROLLING_20_SETTLED","ROLLING_50_SETTLED","ROLLING_7_DAYS","ROLLING_30_DAYS","CURRENT_CALENDAR_WEEK","PREVIOUS_CALENDAR_WEEK","BY_MODEL_GENERATION","BY_CALIBRATION_ARTIFACT","BY_MARKET","BY_COMPETITION","BY_BOOKMAKER"}.issubset(kinds));self.assertTrue(all(identifier<="controlled-governance-observation-031" for identifier in value["included_observation_ids"]));self.assertEqual(value["evaluation_fingerprint"],evaluate_records(records,cutoff_utc="2026-06-01T00:00:00+00:00")["evaluation_fingerprint"])

    def test_006_clear_insufficient_warning_and_blocked_domains(self):
        empty=evaluate_records((),cutoff_utc="2026-07-01T00:00:00+00:00");bad=evaluate_records(controlled_records(),cutoff_utc="2026-07-01T00:00:00+00:00",evidence_class=EVIDENCE_CLASS)
        self.assertEqual(empty["sample_maturity"],"NO_EVIDENCE");self.assertEqual(empty["decision"]["status"],"GOVERNANCE_SAMPLE_INSUFFICIENT");self.assertIn("BLOCKED",bad["metrics"]["predictive_status"]);self.assertIn("BLOCKED",bad["metrics"]["calibration_status"]);self.assertIn("BLOCKED",bad["metrics"]["input_drift_status"]);self.assertIn("WARNING",bad["metrics"]["odds_drift"]["status"]);self.assertIn("WARNING",bad["metrics"]["explanation_drift"]["status"])

    def test_007_market_competition_bookmaker_and_generation_scopes(self):
        value=evaluate_records(controlled_records(),cutoff_utc="2026-07-01T00:00:00+00:00");types={item["scope_type"] for item in value["scope_statuses"]}
        self.assertEqual(types,{"MARKET","COMPETITION","BOOKMAKER","MODEL_GENERATION","CALIBRATION_ARTIFACT"});self.assertEqual(len([x for x in value["scope_statuses"] if x["scope_type"]=="MARKET"]),11);self.assertEqual(len([x for x in value["scope_statuses"] if x["scope_type"]=="COMPETITION"]),2);self.assertEqual(len([x for x in value["scope_statuses"] if x["scope_type"]=="BOOKMAKER"]),2)

    def test_008_hysteresis_recommendations_and_no_automatic_execution(self):
        records=controlled_records();first=evaluate_records(records,cutoff_utc="2026-07-01T00:00:00+00:00");second=evaluate_records(records,cutoff_utc="2026-07-02T00:00:00+00:00",previous_evaluations=(first,))
        self.assertEqual(first["decision"]["status"],"GOVERNANCE_REVIEW_REQUIRED");self.assertEqual(second["decision"]["status"],"GOVERNANCE_PUBLICATION_PAUSED");self.assertEqual(second["decision"]["publication_impact"],"BLOCK");self.assertTrue(all(item["execution_performed"] is False for item in second["recommendations"]));self.assertEqual(second["training_executions"],0);self.assertEqual(second["recalibration_executions"],0);self.assertEqual(second["rollback_executions"],0)

    def test_009_persistence_replay_conflict_foreign_keys_and_immutability(self):
        service=GovernanceService(self.database);records=controlled_records();value=service.evaluate("2026-07-01T00:00:00+00:00",controlled_records=records,evidence_class=EVIDENCE_CLASS);replay=service.evaluate("2026-07-01T00:00:00+00:00",controlled_records=records,evidence_class=EVIDENCE_CLASS)
        self.assertTrue(replay["replayed"]);self.assertEqual(value["evaluation_fingerprint"],replay["evaluation_fingerprint"]);self.assertEqual(self.database.connection.execute("PRAGMA foreign_key_check").fetchall(),[])
        changed=list(records);changed[0]={**changed[0],"probability":"0.61"}
        with self.assertRaises(GovernanceConflictError):service.evaluate("2026-07-01T00:00:00+00:00",controlled_records=changed,evidence_class=EVIDENCE_CLASS)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection:self.database.connection.execute("UPDATE forward_test_governance_evaluations SET governance_status='X'")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.connection:self.database.connection.execute("DELETE FROM forward_test_governance_evaluations")

    def test_010_reproduction_reports_and_incident_deduplication(self):
        result=run_controlled_rehearsal(self.database);evaluation=GovernanceService(self.database).repository.load(result["evaluation_id"]);report=build_report(evaluation)
        self.assertTrue(result["reproduction"]["matches"]);self.assertEqual(markdown(report),markdown(report));self.assertEqual(csv_text(report),csv_text(report));self.assertIn("Preview only",telegram_preview(report));self.assertIn("Sample warnings",markdown(report));service=GovernanceService(self.database);first=service.record_incidents(result["evaluation_id"]);second=service.record_incidents(result["evaluation_id"]);self.assertEqual([x["incident_fingerprint"] for x in first],[x["incident_fingerprint"] for x in second]);self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM forward_test_monitoring_incidents WHERE incident_json LIKE '%FORWARD_TEST_GOVERNANCE%'").fetchone()[0],len(first))

    def test_011_publication_fails_closed_and_observation_snapshot_is_immutable(self):
        from app.lab_operator_console.demo import build_demo
        build_demo(self.database);service=GovernanceService(self.database);observation=self.database.connection.execute("SELECT observation_id FROM forward_test_observations ORDER BY observation_id LIMIT 1").fetchone()[0]
        self.assertEqual(service.publication_status(observation,"2026-08-01T16:30:00+00:00")["status"],"PUBLICATION_GOVERNANCE_REQUIRED")
        service.evaluate("2026-08-01T16:30:00+00:00",controlled_records=controlled_records(),evidence_class=EVIDENCE_CLASS);snapshot=service.snapshot_observation(observation,"2026-08-01T16:30:00+00:00");self.assertEqual(snapshot["observation_id"],observation);self.assertFalse(snapshot["replayed"]);self.assertTrue(service.snapshot_observation(observation,"2026-08-01T16:30:00+00:00")["replayed"])

    def test_012_cli_human_json_invalid_and_help_are_terminal_safe(self):
        output=io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(output):main(["--help"])
        self.assertEqual(raised.exception.code,0);self.assertIn("evaluate-governance",output.getvalue());self.assertTrue(output.getvalue().isascii())

    def test_013_console_governance_page_and_get_are_read_only(self):
        run_controlled_rehearsal(self.database);self.database.close();config=ConsoleConfig.build(self.path,controlled_demo=True,allowed_database_roots=(Path(self.temporary.name),));application=ConsoleApplication(config);status,headers,body=application.render_get("/governance")
        self.assertEqual(status,200);self.assertIn(b"Forward-test governance",body);self.assertIn(b"Generation Comparison",body);self.assertIn(b"Recommendations",body);self.assertIn("governance",NAV);self.assertNotIn(b"Execute bounded action",body);self.database=Database(self.path)

    def test_014_schema_41_fresh_and_v40_upgrade(self):
        self.assertEqual(self.database.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],42);self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM forward_test_governance_evaluations").fetchone()[0],0)
        path=Path(self.temporary.name)/"upgrade.db";upgrade=Database(path)
        try:
            upgrade.connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)")
            for migration in __import__("app.database.migrations",fromlist=["MIGRATIONS"]).MIGRATIONS:
                if migration.version<=40:
                    with upgrade.connection:
                        for statement in migration.statements:upgrade.connection.execute(statement)
                        upgrade.connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?,datetime('now'))",(migration.version,))
            MigrationManager(upgrade.connection).migrate();self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],42);self.assertEqual(upgrade.connection.execute("PRAGMA foreign_key_check").fetchall(),[])
        finally:upgrade.close()


if __name__ == "__main__":
    unittest.main()
