import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout,redirect_stderr
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from app.database import Database,MigrationManager
from app.database.migrations import MIGRATIONS
from app.lab_operator_console.actions import ConsoleActionConflict,ConsoleActionService
from app.lab_operator_console.cli import build_parser,main as cli_main
from app.lab_operator_console.config import ConsoleConfig
from app.lab_operator_console.demo import build_demo
from app.lab_operator_console.models import ActionRequest
from app.lab_operator_console.security import SessionSecurity
from app.lab_operator_console.web import ConsoleApplication,NAV


class LabOperatorConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.path=self.root/"demo.db";self.db=Database(str(self.path));self.manifest=build_demo(self.db);self.db.close()
        self.read_config=ConsoleConfig.build(self.path,allowed_database_roots=(self.root,),controlled_demo=True)
        self.action_config=ConsoleConfig.build(self.path,allowed_database_roots=(self.root,),controlled_demo=True,read_only=False)
    def tearDown(self):self.temp.cleanup()

    def test_001_configuration_localhost_read_only_and_ephemeral_defaults(self):
        self.assertEqual(self.read_config.host,"127.0.0.1");self.assertEqual(self.read_config.port,8765);self.assertTrue(self.read_config.read_only);self.assertTrue(self.read_config.ephemeral_session);self.assertEqual(self.read_config.timezone,"Europe/Riga")
    def test_002_external_and_invalid_bindings_fail_closed(self):
        for changes in ({"host":"0.0.0.0"},{"host":"localhost"},{"port":80},{"port":70000}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):ConsoleConfig.build(self.path,allowed_database_roots=(self.root,),**changes)
    def test_003_database_root_and_missing_database_enforced(self):
        with self.assertRaises(ValueError):ConsoleConfig.build(self.path,allowed_database_roots=(self.root/"other",))
        with self.assertRaises(ValueError):ConsoleConfig.build(self.root/"missing.db",allowed_database_roots=(self.root,))
    def test_004_public_configuration_redacts_session_secret(self):
        value=self.read_config.public_view();self.assertNotIn("session_secret",value);self.assertNotIn(self.read_config.session_secret.hex(),json.dumps(value))
    def test_005_session_signature_expiry_and_cookie_policy(self):
        security=SessionSecurity(b"s"*32,ttl_seconds=60);session,cookie=security.create("operator",now=100);self.assertEqual(security.load(cookie,now=159),session);self.assertIsNone(security.load(cookie,now=161));self.assertIsNone(security.load(cookie+"x",now=101));header=security.cookie_header(cookie);self.assertIn("HttpOnly",header);self.assertIn("SameSite=Strict",header)
    def test_006_csrf_is_session_action_and_time_bound(self):
        security=SessionSecurity(b"s"*32,csrf_ttl_seconds=60);session,_=security.create("operator",now=100);token=security.csrf_token(session,"SETTLE",100);self.assertTrue(security.verify_csrf(session,"SETTLE",token,100));self.assertFalse(security.verify_csrf(session,"OTHER",token,100));self.assertFalse(security.verify_csrf(session,"SETTLE",None,100));self.assertFalse(security.verify_csrf(session,"SETTLE",token,300))
    def test_007_all_navigation_pages_render_with_demo_label(self):
        app=ConsoleApplication(self.read_config)
        for page in NAV:
            with self.subTest(page=page):status,headers,body=app.render_get("/"+page.replace("_","-"));self.assertEqual(status,200);self.assertIn(b"CONTROLLED FICTIONAL DEMO DATA",body);self.assertIn(b"LOCAL OPERATOR CONSOLE",body);self.assertIn("Content-Security-Policy",headers)
    def test_008_overview_health_database_and_sample_warning_render(self):
        body=ConsoleApplication(self.read_config).render_get("/")[2];self.assertIn(b"Schema",body);self.assertIn(b"Pending Results",body);self.assertIn(b"Free",body)
    def test_009_readiness_is_offline_and_free_plan_warning_visible(self):
        with patch("httpx.AsyncClient.get") as network:body=ConsoleApplication(self.read_config).render_get("/readiness")[2]
        network.assert_not_called();self.assertIn(b"Opening this page performs no provider request",body);self.assertIn(b"FREE_PLAN_BLOCKED",body)
    def test_010_discovery_candidate_and_fixture_views_are_persisted_only(self):
        app=ConsoleApplication(self.read_config)
        for page in ("discovery","candidates","fixtures"):
            body=app.render_get("/"+page)[2];self.assertIn(b"READ_ONLY",body);self.assertIn(b"network calls by page request: 0",body)
    def test_011_odds_view_has_all_markets_provenance_and_no_secret(self):
        body=ConsoleApplication(self.read_config).render_get("/odds")[2];
        for market in (b"HOME_WIN",b"DRAW",b"AWAY_WIN",b"OVER_2_5",b"BTTS_NO"):self.assertIn(market,body)
        self.assertNotIn(b"FOOTBALL_API_KEY",body);self.assertNotIn(b"Bearer ",body)
    def test_012_analysis_view_has_11_markets_and_no_prohibited_markets(self):
        body=ConsoleApplication(self.read_config).render_get("/analyses?id=fictional-analysis-1")[2];self.assertEqual(body.count(b"raw "),11);self.assertNotIn(b"CORRECT_SCORE",body);self.assertNotIn(b"COMBO",body);self.assertIn(b"calibrated",body)
    def test_013_observation_links_and_eligibility_are_visible(self):
        body=ConsoleApplication(self.read_config).render_get("/observations?id=fictional-observation-1")[2];self.assertIn(b"fictional-analysis-1",body);self.assertIn(b"fictional-odds-1",body);self.assertIn(b"FORWARD_TEST_REAL_TIME",body)
    def test_014_preview_escapes_source_and_has_preview_only_notice(self):
        body=ConsoleApplication(self.read_config).render_get("/previews")[2];self.assertIn("PREVIEW ONLY — NOTHING HAS BEEN SENT".encode(),body);self.assertNotIn(b"<script>alert",body)
    def test_015_review_pass_and_block_are_visible_and_no_send_occurs(self):
        with patch("httpx.AsyncClient.post") as post:body=ConsoleApplication(self.read_config).render_get("/reviews")[2]
        post.assert_not_called();self.assertIn(b"LAB_PUBLICATION_REVIEW_PASSED",body);self.assertIn(b"LAB_PUBLICATION_REVIEW_BLOCKED",body)
    def test_016_send_readiness_remains_fake_only_and_disabled(self):
        body=ConsoleApplication(self.action_config).render_get("/send-readiness?id=fictional-observation-1")[2];self.assertIn(b"real transport available from console",body.lower());self.assertIn(b"False",body);self.assertIn(b"never performs a real Telegram send",body)
    def test_017_results_and_settlements_show_win_loss_void(self):
        app=ConsoleApplication(self.read_config);results=app.render_get("/results")[2];settlements=app.render_get("/settlements")[2];self.assertIn(b"demo-result-1",results)
        for outcome in (b"WON",b"LOST",b"VOID"):self.assertIn(outcome,settlements)
    def test_018_monitoring_and_reports_show_hypothetical_sample_warning(self):
        app=ConsoleApplication(self.read_config);monitor=app.render_get("/monitoring")[2];reports=app.render_get("/reports")[2];self.assertIn(b"HYPOTHETICAL_FLAT_STAKE",monitor);self.assertIn(b"FORWARD_TEST_SAMPLE_INSUFFICIENT",monitor);self.assertIn(b"WEEKLY",reports);self.assertIn(b"CUMULATIVE",reports)
    def test_019_unresolved_incidents_and_health_are_offline(self):
        app=ConsoleApplication(self.read_config)
        with patch("httpx.AsyncClient.get") as network:
            for page in ("unresolved","incidents","health"):self.assertEqual(app.render_get("/"+page)[0],200)
        network.assert_not_called();self.assertIn(b"CONTROLLED_RESULT_CONFLICT",app.render_get("/incidents")[2])
    def test_020_get_requests_never_mutate_database(self):
        connection=sqlite3.connect(self.path);before=connection.total_changes;counts=tuple(connection.execute("select count(*) from lab_operator_console_actions").fetchone());connection.close();app=ConsoleApplication(self.action_config)
        for page in NAV:app.render_get("/"+page.replace("_","-"))
        connection=sqlite3.connect(self.path);self.assertEqual(tuple(connection.execute("select count(*) from lab_operator_console_actions").fetchone()),counts);connection.close();self.assertEqual(before,0)
    def test_021_post_requires_valid_session_and_csrf(self):
        app=ConsoleApplication(self.action_config);self.assertEqual(app.handle_post("/action",b"action_type=SETTLE",None)[0],403);session,cookie=app.security.create("op");self.assertEqual(app.handle_post("/action",b"action_type=SETTLE",cookie)[0],403)
    def test_022_read_only_mode_blocks_valid_confirmed_action(self):
        app=ConsoleApplication(self.read_config);session,cookie=app.security.create("op");action="GENERATE_WEEKLY_REPORT";body=urlencode({"action_type":action,"csrf_token":app.security.csrf_token(session,action),"confirmation":"GENERATE_WEEKLY_REPORT"}).encode();status,_,raw=app.handle_post("/action",body,cookie);self.assertEqual(status,409);self.assertEqual(json.loads(raw)["status"],"ACTION_BLOCKED_READ_ONLY")
    def test_023_wrong_confirmation_fails_without_audit_mutation(self):
        app=ConsoleApplication(self.action_config);session,cookie=app.security.create("op");action="SETTLE";body=urlencode({"action_type":action,"csrf_token":app.security.csrf_token(session,action),"confirmation":"wrong","target_identifier":"fictional-observation-4"}).encode();self.assertEqual(app.handle_post("/action",body,cookie)[0],409);db=Database(str(self.path));self.assertEqual(db.connection.execute("select count(*) from lab_operator_console_actions").fetchone()[0],0);db.close()
    def test_024_report_action_is_audited_idempotent_and_zero_call(self):
        service_db=Database(str(self.path));service=ConsoleActionService(service_db,actions_enabled=True);request=ActionRequest("report-request","GENERATE_CUMULATIVE_REPORT","operator","/reports",None,"GENERATE_CUMULATIVE_REPORT",{},"2026-08-02T12:30:00+00:00");first=service.execute(request);second=service.execute(request);self.assertEqual(first["event_fingerprint"],second["event_fingerprint"]);self.assertEqual(first["provider_call_count"],0);self.assertEqual(first["telegram_call_count"],0);self.assertEqual(service_db.connection.execute("select count(*) from lab_operator_console_actions").fetchone()[0],1);service_db.close()
    def test_025_action_conflicting_replay_rejected(self):
        db=Database(str(self.path));service=ConsoleActionService(db,actions_enabled=True);base=ActionRequest("same","FAKE_LAB_SEND","operator","/send","x","FAKE_LAB_SEND_ONLY",{},"2026-08-02T12:30:00+00:00");service.execute(base)
        with self.assertRaises(ConsoleActionConflict):service.execute(ActionRequest("same","FAKE_LAB_SEND","operator","/send","different","FAKE_LAB_SEND_ONLY",{},"2026-08-02T12:30:00+00:00"))
        db.close()
    def test_026_fake_send_path_uses_zero_real_telegram_calls(self):
        db=Database(str(self.path));service=ConsoleActionService(db,actions_enabled=True)
        with patch("httpx.AsyncClient.post") as transport:value=service.execute(ActionRequest("fake-send","FAKE_LAB_SEND","operator","/send","fictional-observation-1","FAKE_LAB_SEND_ONLY",{},"2026-08-02T12:31:00+00:00"))
        transport.assert_not_called();self.assertEqual(value["telegram_call_count"],0);self.assertEqual(db.connection.execute("select count(*) from real_match_lab_deliveries").fetchone()[0],0);db.close()
    def test_027_incident_acknowledgement_does_not_repair_incident(self):
        db=Database(str(self.path));service=ConsoleActionService(db,actions_enabled=True);value=service.execute(ActionRequest("ack","ACKNOWLEDGE_INCIDENT","operator","/incidents","demo-incident-1","ACKNOWLEDGE_INCIDENT",{"reason":"reviewed, not repaired"},"2026-08-02T12:32:00+00:00"));self.assertEqual(value["status"],"COMPLETED");self.assertEqual(db.connection.execute("select severity from forward_test_monitoring_incidents where incident_id='demo-incident-1'").fetchone()[0],"CORRUPT");db.close()
    def test_028_provider_actions_are_bounded_and_inert_without_executor(self):
        db=Database(str(self.path));service=ConsoleActionService(db,actions_enabled=True);value=service.execute(ActionRequest("provider","READINESS_NETWORK_VERIFY","operator","/readiness",None,"VERIFY_API_FOOTBALL_ONCE",{},"2026-08-02T12:33:00+00:00"));self.assertEqual(value["status"],"BLOCKED");self.assertEqual(value["provider_call_count"],0);db.close()
    def test_029_action_redaction_prevents_secret_persistence(self):
        db=Database(str(self.path));service=ConsoleActionService(db,actions_enabled=True);service.execute(ActionRequest("secret","FAKE_LAB_SEND","operator","/send","x","FAKE_LAB_SEND_ONLY",{"api_key":"super-secret","note":"Bearer hidden"},"2026-08-02T12:34:00+00:00"));raw=db.connection.execute("select action_json from lab_operator_console_actions where request_id='secret'").fetchone()[0];self.assertNotIn("super-secret",raw);self.assertNotIn("Bearer hidden",raw);self.assertIn("[REDACTED]",raw);db.close()
    def test_030_demo_manifest_is_deterministic_idempotent_and_zero_side_effect(self):
        db=Database(str(self.path));self.assertEqual(build_demo(db),build_demo(db));self.assertEqual(self.manifest["network_call_count"],0);self.assertEqual(self.manifest["telegram_call_count"],0);self.assertEqual(self.manifest["official_mutation_count"],0);self.assertEqual(db.connection.execute("select count(*) from lab_operator_console_demo_manifests").fetchone()[0],1);db.close()
    def test_030a_report_compare_reproduce_and_safe_export_actions(self):
        db=Database(str(self.path));service=ConsoleActionService(db,actions_enabled=True,allowed_output_roots=(self.root,));weekly=self.manifest["weekly_report_id"];cumulative=self.manifest["cumulative_report_id"]
        compared=service.execute(ActionRequest("compare","COMPARE_REPORTS","operator","/reports",weekly,"COMPARE_REPORTS",{"comparison_report_id":cumulative},"2026-08-02T12:35:00+00:00"));self.assertEqual(compared["status"],"COMPLETED")
        reproduced=service.execute(ActionRequest("reproduce","REPRODUCE_REPORT","operator","/reports",weekly,"REPRODUCE_REPORT",{},"2026-08-02T12:36:00+00:00"));self.assertEqual(reproduced["status"],"COMPLETED")
        exported=service.execute(ActionRequest("export","CREATE_EXPORT","operator","/reports",weekly,"CREATE_REPORT_EXPORT",{"output_name":"controlled-export"},"2026-08-02T12:37:00+00:00"));self.assertEqual(exported["status"],"COMPLETED");self.assertTrue((self.root/"controlled-export"/"manifest.json").exists());db.close()
    def test_031_schema_39_fresh_upgrade_foreign_keys_and_append_only(self):
        self.assertEqual(max(m.version for m in MIGRATIONS),39);db=Database(str(self.path));self.assertEqual(db.connection.execute("select max(version) from schema_migrations").fetchone()[0],39);self.assertEqual(db.connection.execute("pragma foreign_key_check").fetchall(),[])
        for sql in ("update lab_operator_console_demo_manifests set demo_version='x'","delete from lab_operator_console_demo_manifests"):
            with self.assertRaises(sqlite3.IntegrityError):db.connection.execute(sql)
            db.connection.rollback()
        db.close()
    def test_032_prior_schema_upgrade(self):
        db=Database(":memory:");db.connection.execute("create table schema_migrations(version integer primary key,applied_at text not null)")
        for migration in MIGRATIONS:
            if migration.version>38:break
            for statement in migration.statements:db.connection.execute(statement)
            db.connection.execute("insert into schema_migrations values (?,'existing')",(migration.version,))
        MigrationManager(db.connection).migrate();self.assertEqual(db.connection.execute("select max(version) from schema_migrations").fetchone()[0],39);self.assertEqual(db.connection.execute("pragma foreign_key_check").fetchall(),[]);db.close()
    def test_033_cli_help_config_check_and_ascii_terminal(self):
        self.assertIsNotNone(build_parser().parse_args(["run","--database",str(self.path)]));out=io.StringIO()
        with redirect_stdout(out):code=cli_main(["config-check","--database",str(self.path),"--allowed-root",str(self.root)])
        self.assertEqual(code,0);text=out.getvalue();text.encode("cp1252");self.assertIn("READ_ONLY",text);self.assertNotIn(self.read_config.session_secret.hex(),text)
    def test_034_cli_json_configuration_is_safe(self):
        out=io.StringIO()
        with redirect_stdout(out):code=cli_main(["config-check","--database",str(self.path),"--allowed-root",str(self.root),"--output","json"])
        value=json.loads(out.getvalue());self.assertEqual(code,0);self.assertTrue(value["read_only"]);self.assertEqual(value["session_secret"],"EPHEMERAL_NOT_PRINTED");self.assertFalse(value["external_binding"])
    def test_035_import_startup_is_inert(self):
        import app.lab_operator_console as console
        self.assertTrue(hasattr(console,"ConsoleApplication"));db=Database(str(self.path));self.assertEqual(db.connection.execute("select count(*) from lab_operator_console_actions").fetchone()[0],0);db.close()
    def test_036_official_bankroll_activation_and_scheduling_isolation(self):
        db=Database(str(self.path));tables=("official_prediction_publication_events","bankroll_transactions","model_activation_executions","real_match_lab_deliveries");before={t:db.connection.execute(f"select count(*) from {t}").fetchone()[0] for t in tables};ConsoleActionService(db,actions_enabled=True).execute(ActionRequest("isolation","GENERATE_WEEKLY_REPORT","operator","/reports",None,"GENERATE_WEEKLY_REPORT",{},"2026-08-02T12:35:00+00:00"));after={t:db.connection.execute(f"select count(*) from {t}").fetchone()[0] for t in tables};self.assertEqual(before,after);db.close();self.assertFalse(self.read_config.public_view()["scheduler_enabled"])


if __name__=="__main__":unittest.main()
