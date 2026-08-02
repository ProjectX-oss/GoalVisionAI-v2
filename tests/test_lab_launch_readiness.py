from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.forward_test_governance.policy import DEFAULT_POLICY
from app.forward_test_governance_review import APPROVE_CONFIRMATION, REVOKE_CONFIRMATION as POLICY_REVOKE, GovernancePolicyReviewService, review_governance_policy
from app.forward_test_governance_review.service import GovernanceReviewConflict
from app.lab_launch_readiness import AUTHORIZE_CONFIRMATION, LabBackupService, LabLaunchService, LaunchConflict
from app.lab_launch_readiness.backup import BackupConflict
from app.lab_launch_readiness.controlled import EVIDENCE_CLASS, run_controlled_rehearsal
from app.lab_launch_readiness.service import REVOKE_CONFIRMATION

NOW=datetime(2026,8,2,12,tzinfo=timezone.utc)


class FinalLabLaunchReadinessTests(unittest.TestCase):
    def setUp(self):
        self.root=Path.cwd()/"var"/f"lab-launch-test-{uuid.uuid4().hex}";self.root.mkdir(parents=True);self.path=self.root/"lab.sqlite3";self.db=Database(self.path);MigrationManager(self.db.connection).migrate();self.review_service=GovernancePolicyReviewService(self.db.connection);self.launch=LabLaunchService(self.db.connection)

    def tearDown(self):self.db.close();shutil.rmtree(self.root)

    def approved(self):
        review=self.review_service.persist_review(review_governance_policy(reviewed_at_utc=NOW));approval=self.review_service.approve(review["review_id"],DEFAULT_POLICY.fingerprint,"operator",APPROVE_CONFIRMATION,approved_at_utc=NOW+timedelta(seconds=1));return review,approval

    def authorized(self):
        review,approval=self.approved();auth=self.launch.authorize(approval["approval_id"],"operator",AUTHORIZE_CONFIRMATION,authorized_at_utc=NOW+timedelta(seconds=2),expires_at_utc=NOW+timedelta(hours=72),champion_generation_id="champion-1",calibration_artifact_id="calibration-1");return review,approval,auth

    def test_review_is_deterministic_complete_and_warns(self):
        left=review_governance_policy(reviewed_at_utc=NOW);right=review_governance_policy(reviewed_at_utc=NOW)
        self.assertEqual(left,right);self.assertEqual(left["outcome"],"PASSED_WITH_WARNINGS");self.assertEqual(left["policy_fingerprint"],DEFAULT_POLICY.fingerprint);self.assertTrue(all(left["checks"].values()));self.assertGreaterEqual(len(left["findings"]),len(DEFAULT_POLICY.__dataclass_fields__))

    def test_review_replay_and_immutable_findings(self):
        value=review_governance_policy(reviewed_at_utc=NOW);self.assertFalse(self.review_service.persist_review(value)["replayed"]);self.assertTrue(self.review_service.persist_review(value)["replayed"])
        with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute("UPDATE governance_policy_reviews SET outcome='PASSED'")

    def test_approval_confirmation_fingerprint_and_revocation(self):
        review=self.review_service.persist_review(review_governance_policy(reviewed_at_utc=NOW))
        with self.assertRaises(GovernanceReviewConflict):self.review_service.approve(review["review_id"],"wrong","operator",APPROVE_CONFIRMATION,approved_at_utc=NOW)
        with self.assertRaises(GovernanceReviewConflict):self.review_service.approve(review["review_id"],DEFAULT_POLICY.fingerprint,"operator","wrong",approved_at_utc=NOW)
        approval=self.review_service.approve(review["review_id"],DEFAULT_POLICY.fingerprint,"operator",APPROVE_CONFIRMATION,approved_at_utc=NOW);self.assertTrue(self.review_service.is_active(approval["approval_id"]));self.review_service.revoke(approval["approval_id"],"operator",POLICY_REVOKE,occurred_at_utc=NOW+timedelta(seconds=1));self.assertFalse(self.review_service.is_active(approval["approval_id"]))

    def test_authorization_binding_replay_expiry_revocation_capacity(self):
        _,_,auth=self.authorized();same=self.launch.authorize(auth["approval_id"],"operator",AUTHORIZE_CONFIRMATION,authorized_at_utc=NOW+timedelta(seconds=2),expires_at_utc=NOW+timedelta(hours=72),champion_generation_id="champion-1",calibration_artifact_id="calibration-1")
        self.assertTrue(same["replayed"]);self.assertEqual(auth["environment"],"LAB");self.assertEqual(auth["chat_id"],"-1003510920417");self.assertEqual(auth["minimum_decimal_odds"],"1.60");self.assertFalse(auth["correct_score_allowed"]);self.assertFalse(auth["combo_allowed"]);self.assertEqual(self.launch.status(auth["authorization_id"],now=NOW+timedelta(hours=1))["remaining_publications"],1)
        self.launch.consume(auth["authorization_id"],"observation-1","operator",occurred_at_utc=NOW+timedelta(hours=2),send_succeeded=True);self.assertEqual(self.launch.status(auth["authorization_id"],now=NOW+timedelta(hours=3))["remaining_publications"],0)
        with self.assertRaises(LaunchConflict):self.launch.consume(auth["authorization_id"],"observation-2","operator",occurred_at_utc=NOW+timedelta(hours=4),send_succeeded=True)

    def test_authorization_requires_active_approval_and_exact_confirmation(self):
        _,approval=self.approved()
        with self.assertRaises(LaunchConflict):self.launch.authorize(approval["approval_id"],"operator","wrong",authorized_at_utc=NOW,expires_at_utc=NOW+timedelta(hours=1),champion_generation_id="c",calibration_artifact_id="k")
        self.review_service.revoke(approval["approval_id"],"operator",POLICY_REVOKE,occurred_at_utc=NOW+timedelta(seconds=2))
        with self.assertRaises(LaunchConflict):self.launch.authorize(approval["approval_id"],"operator",AUTHORIZE_CONFIRMATION,authorized_at_utc=NOW,expires_at_utc=NOW+timedelta(hours=1),champion_generation_id="c",calibration_artifact_id="k")

    def test_authorization_expiry_and_revocation(self):
        _,_,auth=self.authorized();self.assertTrue(self.launch.status(auth["authorization_id"],now=NOW+timedelta(days=4))["expired"]);self.launch.revoke(auth["authorization_id"],"operator",REVOKE_CONFIRMATION,occurred_at_utc=NOW+timedelta(hours=1));self.assertTrue(self.launch.status(auth["authorization_id"],now=NOW+timedelta(hours=2))["revoked"])

    def test_readiness_ready_warning_and_blocks(self):
        _,_,auth=self.authorized();ready=self.launch.readiness_audit(auth["authorization_id"],audited_at_utc=NOW+timedelta(minutes=1),facts={"champion_registry_verified":True});self.assertEqual(ready["outcome"],"LAB_LAUNCH_READY")
        warning=self.launch.readiness_audit(auth["authorization_id"],audited_at_utc=NOW+timedelta(minutes=2),facts={"capability_cache_stale":True,"champion_registry_verified":True});self.assertEqual(warning["outcome"],"LAB_LAUNCH_READY_WITH_WARNINGS")
        blocked=self.launch.readiness_audit(auth["authorization_id"],audited_at_utc=NOW+timedelta(minutes=3),facts={"synthetic_evidence":True,"scheduler_enabled":True,"automatic_send_enabled":True,"official_mutations":1,"champion_generation_id":"wrong"});self.assertEqual(blocked["outcome"],"LAB_LAUNCH_BLOCKED");self.assertGreaterEqual(len(blocked["blockers"]),5)

    def test_preflight_is_inert_and_typed(self):
        inert=self.launch.preflight(checked_at_utc=NOW,network_verified=False);self.assertEqual(inert["provider_call_count"],0);self.assertEqual(inert["outcome"],"PRO_PREFLIGHT_NETWORK_NOT_REQUESTED")
        self.assertEqual(self.launch.preflight(checked_at_utc=NOW,network_verified=True,provider_facts={"authenticated":True,"plan":"PRO","current_season_access":True,"quota_remaining":20,"required_calls":12,"provider_call_count":1})["outcome"],"PRO_PLAN_READY")
        self.assertEqual(self.launch.preflight(checked_at_utc=NOW,network_verified=True,provider_facts={"authenticated":True,"plan":"FREE","provider_call_count":1})["outcome"],"PROVIDER_PLAN_BLOCKED")
        self.assertEqual(self.launch.preflight(checked_at_utc=NOW,network_verified=True,provider_facts={"authenticated":False,"provider_call_count":1})["outcome"],"CREDENTIAL_INVALID")

    def test_backup_verify_restore_hash_and_no_overwrite(self):
        service=LabBackupService(self.db.connection,self.path,self.root/"backups");backup=service.create(created_at_utc=NOW);self.assertEqual(backup["outcome"],"BACKUP_CREATED");self.assertEqual(service.verify(backup["backup_id"],verified_at_utc=NOW)["outcome"],"BACKUP_VERIFIED");restore=service.restore_rehearsal(backup["backup_id"],self.root/"backups"/"restore.sqlite3");self.assertEqual(restore["outcome"],"RESTORE_REHEARSAL_PASSED");self.assertFalse(restore["live_database_overwritten"])
        with self.assertRaises(BackupConflict):service.create(created_at_utc=NOW)

    def test_backup_root_and_corruption_fail_closed(self):
        service=LabBackupService(self.db.connection,self.path,self.root/"backups");backup=service.create(created_at_utc=NOW);Path(backup["backup_path"]).write_bytes(b"corrupt");self.assertEqual(service.verify(backup["backup_id"],verified_at_utc=NOW+timedelta(seconds=1))["outcome"],"BACKUP_FAILED")
        with self.assertRaises(BackupConflict):service.restore_rehearsal(backup["backup_id"],self.root/"outside.sqlite3")

    def test_stage_replay_conflict_send_gate_and_post_run_audit(self):
        _,_,auth=self.authorized();ready=self.launch.readiness_audit(auth["authorization_id"],audited_at_utc=NOW+timedelta(minutes=1),facts={"champion_registry_verified":True});execution=self.launch.start_execution(auth["authorization_id"],ready,started_at_utc=NOW+timedelta(minutes=2),request={"max_calls":40});stage=self.launch.append_stage(execution["execution_id"],1,"BACKUP","PASSED",occurred_at_utc=NOW+timedelta(minutes=3));self.assertEqual(self.launch.append_stage(execution["execution_id"],1,"BACKUP","PASSED",occurred_at_utc=NOW+timedelta(minutes=3)),stage)
        with self.assertRaises(LaunchConflict):self.launch.append_stage(execution["execution_id"],1,"INFERENCE","PASSED",occurred_at_utc=NOW+timedelta(minutes=3))
        rejected=self.launch.validate_send(auth["authorization_id"],observation_id="o",confirmation="wrong",environment="PROD",chat_id="wrong",bot="wrong",fingerprints={},now=NOW+timedelta(minutes=4));self.assertEqual(rejected["status"],"LAB_MANUAL_SEND_REJECTED");self.assertFalse(rejected["transport_constructed"])
        facts={key:True for key in ("backup_before_run","fixture_before_inference","odds_before_inference","odds_before_kickoff","baseline_compatible","exact_model_generation","exact_calibration_artifact","reasoning_audit_passed","governance_snapshot_present","publication_review_linked","database_integrity")};audit=self.launch.post_run_audit(execution["execution_id"],audited_at_utc=NOW+timedelta(minutes=5),facts=facts);self.assertEqual(audit["outcome"],"LAB_RUN_AUDIT_PASSED")

    def test_controlled_rehearsal_has_all_39_checks_and_zero_real_effects(self):
        result=run_controlled_rehearsal(self.db,self.path,self.root/"controlled-backups",NOW);self.assertEqual(result["evidence_class"],EVIDENCE_CLASS);self.assertEqual(len(result["checks"]),39);self.assertEqual(result["outcome"],"CONTROLLED_REHEARSAL_PASSED");self.assertEqual(result["real_provider_calls"],0);self.assertEqual(result["real_telegram_sends"],0);self.assertEqual(result["official_publications"],0)

    def test_schema_42_fresh_foreign_keys_and_append_only(self):
        self.assertEqual(MIGRATIONS[-1].version,42);self.assertEqual(self.db.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],42);self.assertEqual(self.db.connection.execute("PRAGMA foreign_key_check").fetchall(),[])
        tables={row[0] for row in self.db.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")};self.assertIn("lab_launch_post_match_reviews",tables);self.assertIn("governance_policy_reviews",tables)

    def test_v41_upgrade(self):
        other=Database(self.root/"upgrade.sqlite3");manager=MigrationManager(other.connection);original=MIGRATIONS
        from app.database import migrations
        try:migrations.MIGRATIONS=original[:-1];manager.migrate();self.assertEqual(other.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],41);migrations.MIGRATIONS=original;manager.migrate();self.assertEqual(other.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],42)
        finally:migrations.MIGRATIONS=original;other.close()


if __name__=="__main__":unittest.main()
