"""Immutable authorization, readiness, orchestration and audit boundaries."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.forward_test_governance.policy import DEFAULT_POLICY
from app.forward_test_governance_review import GovernancePolicyReviewService
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

AUTHORIZE_CONFIRMATION = "AUTHORIZE_FIRST_GOALVISION_LAB_FORWARD_TEST"
REVOKE_CONFIRMATION = "REVOKE_FIRST_GOALVISION_LAB_FORWARD_TEST"
SEND_CONFIRMATION = "SEND_TO_GOALVISION_AI_LAB"
LAB_CHAT_ID = "-1003510920417"
LAB_BOT = "@GoalVision_AI_Lab_Bot"
ALLOWED_MARKETS = ("HOME_WIN", "DRAW", "AWAY_WIN", "OVER_2_5", "UNDER_2_5", "BTTS_YES", "BTTS_NO", "HOME_OR_DRAW", "AWAY_OR_DRAW", "HOME_DRAW_NO_BET", "AWAY_DRAW_NO_BET")


class LaunchConflict(RuntimeError):
    """An immutable launch request or prerequisite conflicts."""


class LabLaunchService:
    def __init__(self, connection) -> None:
        self.connection = connection

    def authorize(self, approval_id: str, operator: str, confirmation: str, *, authorized_at_utc: datetime, expires_at_utc: datetime, champion_generation_id: str, calibration_artifact_id: str, reasoning_policy_version: str = "goalvision-prediction-reasoning-policy-v1") -> dict:
        if confirmation != AUTHORIZE_CONFIRMATION: raise LaunchConflict("Exact launch confirmation is required.")
        if not GovernancePolicyReviewService(self.connection).is_active(approval_id): raise LaunchConflict("An active governance policy approval is required.")
        authorized, expires = _utc(authorized_at_utc), _utc(expires_at_utc)
        if expires <= authorized or expires > authorized + timedelta(days=7): raise LaunchConflict("Authorization expiry must be future and bounded to seven days.")
        material = {"schema_version": "goalvision-first-lab-launch-authorization-v2", "approval_id": approval_id, "environment": "LAB", "chat_id": LAB_CHAT_ID, "bot_username": LAB_BOT, "governance_policy_fingerprint": DEFAULT_POLICY.fingerprint, "reasoning_policy_version": reasoning_policy_version, "publication_policy_version": "goalvision-lab-single-publication-v2", "live_model_schema_fingerprint": LIVE_MODEL_INPUT_CONTRACT.schema_fingerprint, "champion_generation_id": champion_generation_id, "calibration_artifact_id": calibration_artifact_id, "evidence_tier": "FORWARD_TEST_REAL_TIME", "allowed_markets": ALLOWED_MARKETS, "single_bets_only": True, "minimum_decimal_odds": None, "correct_score_allowed": False, "combo_allowed": False, "publication_capacity": 1, "operator_identity": operator, "authorized_at_utc": authorized.isoformat(), "expires_at_utc": expires.isoformat()}
        fp = fingerprint(material); value = {**material, "authorization_id": "lab-launch-authorization-" + fp, "authorization_fingerprint": fp, "status": "LAB_LAUNCH_AUTHORIZED"}
        existing = self.connection.execute("SELECT authorization_json FROM lab_launch_authorizations WHERE authorization_id=?", (value["authorization_id"],)).fetchone()
        if existing:
            if existing[0] != canonical_json(value): raise LaunchConflict("Authorization conflict.")
            return {**value, "replayed": True}
        with self.connection:
            self.connection.execute("INSERT INTO lab_launch_authorizations VALUES (?,?,?,?,?,?,?,?,?,?,?)", (value["authorization_id"], approval_id, "LAB", LAB_CHAT_ID, LAB_BOT, value["expires_at_utc"], 1, operator, fp, canonical_json(value), value["authorized_at_utc"]))
        return {**value, "replayed": False}

    def status(self, authorization_id: str, *, now: datetime) -> dict:
        row = self.connection.execute("SELECT authorization_json FROM lab_launch_authorizations WHERE authorization_id=?", (authorization_id,)).fetchone()
        if not row: return {"status": "AUTHORIZATION_INVALID", "remaining_publications": 0, "reason": "NOT_FOUND"}
        value = json.loads(row[0]); events = self.connection.execute("SELECT event_type,linked_identifier FROM lab_launch_authorization_events WHERE authorization_id=? ORDER BY occurred_at_utc,event_id", (authorization_id,)).fetchall()
        revoked = any(item[0] == "REVOKED" for item in events); consumed = [item[1] for item in events if item[0] == "CONSUMED"]
        expired = _utc(now).isoformat() >= value["expires_at_utc"]
        active_approval = GovernancePolicyReviewService(self.connection).is_active(value["approval_id"])
        active = not revoked and not expired and active_approval and len(consumed) < value["publication_capacity"]
        return {**value, "status": "AUTHORIZATION_ACTIVE" if active else "AUTHORIZATION_INVALID", "revoked": revoked, "expired": expired, "active_policy_approval": active_approval, "consumed_observation_ids": consumed, "remaining_publications": max(0, value["publication_capacity"] - len(consumed))}

    def revoke(self, authorization_id: str, operator: str, confirmation: str, *, occurred_at_utc: datetime) -> dict:
        if confirmation != REVOKE_CONFIRMATION: raise LaunchConflict("Exact revocation confirmation is required.")
        return self._authorization_event(authorization_id, "REVOKED", operator, None, occurred_at_utc)

    def consume(self, authorization_id: str, observation_id: str, operator: str, *, occurred_at_utc: datetime, send_succeeded: bool) -> dict:
        if not send_succeeded: return {"status": "AUTHORIZATION_NOT_CONSUMED", "reason": "SEND_NOT_CONFIRMED_SUCCESSFUL"}
        if self.status(authorization_id, now=occurred_at_utc)["status"] != "AUTHORIZATION_ACTIVE": raise LaunchConflict("Authorization is expired, revoked, or consumed.")
        return self._authorization_event(authorization_id, "CONSUMED", operator, observation_id, occurred_at_utc)

    def readiness_audit(self, authorization_id: str | None, *, audited_at_utc: datetime, facts: dict | None = None, persist: bool = True) -> dict:
        facts = dict(facts or {}); blockers = []; warnings = []
        auth = self.status(authorization_id or "", now=audited_at_utc)
        if auth["status"] != "AUTHORIZATION_ACTIVE": blockers.append("ACTIVE_AUTHORIZATION_REQUIRED")
        version = self.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        if version != 42: blockers.append("SCHEMA_VERSION_MISMATCH")
        if facts.get("synthetic_evidence"): blockers.append("SYNTHETIC_EVIDENCE_PROHIBITED")
        if facts.get("scheduler_enabled"): blockers.append("SCHEDULER_MUST_BE_DISABLED")
        if facts.get("automatic_send_enabled"): blockers.append("AUTOMATIC_SEND_MUST_BE_DISABLED")
        if facts.get("official_mutations", 0): blockers.append("OFFICIAL_ISOLATION_VIOLATION")
        if facts.get("champion_generation_id") and auth.get("champion_generation_id") != facts["champion_generation_id"]: blockers.append("CHAMPION_GENERATION_MISMATCH")
        if facts.get("calibration_artifact_id") and auth.get("calibration_artifact_id") != facts["calibration_artifact_id"]: blockers.append("CALIBRATION_ARTIFACT_MISMATCH")
        if auth.get("live_model_schema_fingerprint")!=LIVE_MODEL_INPUT_CONTRACT.schema_fingerprint:blockers.append("LIVE_MODEL_SCHEMA_MISMATCH")
        if not facts.get("champion_registry_verified"):
            generation=self.connection.execute("SELECT model_scope,generation_number,calibration_artifact_set_id FROM model_champion_generations WHERE champion_generation_id=?",(auth.get("champion_generation_id"),)).fetchone()
            if not generation:blockers.append("CHAMPION_GENERATION_NOT_REGISTERED")
            else:
                current=self.connection.execute("SELECT champion_generation_id FROM model_champion_generations WHERE model_scope=? ORDER BY generation_number DESC LIMIT 1",(generation[0],)).fetchone()
                if not current or current[0]!=auth.get("champion_generation_id"):blockers.append("CHAMPION_GENERATION_NOT_CURRENT")
                if generation[2]!=auth.get("calibration_artifact_id"):blockers.append("CALIBRATION_ARTIFACT_NOT_BOUND_TO_CHAMPION")
        if facts.get("capability_cache_stale"): warnings.append("CAPABILITY_CACHE_REFRESH_REQUIRED")
        outcome = "LAB_LAUNCH_BLOCKED" if blockers else "LAB_LAUNCH_READY_WITH_WARNINGS" if warnings else "LAB_LAUNCH_READY"
        material = {"schema_version": "goalvision-lab-final-readiness-audit-v1", "authorization_id": authorization_id, "outcome": outcome, "schema_version_observed": version, "checks": {"manual_only": True, "telegram_transport_constructed": False, "scheduling_enabled": False, "official_isolated": not facts.get("official_mutations", 0)}, "warnings": warnings, "blockers": blockers, "audited_at_utc": _utc(audited_at_utc).isoformat()}
        fp = fingerprint(material); value = {**material, "audit_id": "lab-readiness-audit-" + fp, "audit_fingerprint": fp}
        if persist:
            with self.connection: self.connection.execute("INSERT OR IGNORE INTO lab_launch_readiness_audits VALUES (?,?,?,?,?,?)", (value["audit_id"], authorization_id, outcome, fp, canonical_json(value), value["audited_at_utc"]))
        return value

    def preflight(self, *, checked_at_utc: datetime, provider_facts: dict | None = None, network_verified: bool = False, persist: bool = True) -> dict:
        facts = dict(provider_facts or {}); calls = int(facts.get("provider_call_count", 0))
        if not network_verified: outcome = "PRO_PREFLIGHT_NETWORK_NOT_REQUESTED"
        elif not facts.get("authenticated"): outcome = "CREDENTIAL_INVALID"
        elif str(facts.get("plan", "UNKNOWN")).upper() in {"FREE", "UNKNOWN"}: outcome = "PROVIDER_PLAN_BLOCKED"
        elif facts.get("current_season_access") is False: outcome = "CURRENT_SEASON_ACCESS_BLOCKED"
        elif int(facts.get("quota_remaining", 0)) < int(facts.get("required_calls", 12)): outcome = "QUOTA_INSUFFICIENT"
        else: outcome = "PRO_PLAN_READY"
        material = {"schema_version": "goalvision-lab-pro-preflight-v1", "outcome": outcome, "network_verified": network_verified, "provider_call_count": calls, "maximum_provider_calls": 1 if network_verified else 0, "plan": str(facts.get("plan", "NOT_CHECKED")), "quota_remaining": facts.get("quota_remaining"), "current_season_access": facts.get("current_season_access"), "secrets_present": False, "checked_at_utc": _utc(checked_at_utc).isoformat()}
        if calls > material["maximum_provider_calls"]: material["outcome"] = "PREFLIGHT_CALL_BOUND_EXCEEDED"
        fp = fingerprint(material); value = {**material, "preflight_id": "lab-preflight-" + fp, "preflight_fingerprint": fp}
        if persist:
            with self.connection: self.connection.execute("INSERT OR IGNORE INTO lab_launch_preflights VALUES (?,?,?,?,?,?,?)", (value["preflight_id"], value["outcome"], int(network_verified), calls, fp, canonical_json(value), value["checked_at_utc"]))
        return value

    def validate_send(self, authorization_id: str, *, observation_id: str, confirmation: str, environment: str, chat_id: str, bot: str, fingerprints: dict, now: datetime) -> dict:
        blockers=[]; status=self.status(authorization_id, now=now)
        if status["status"] != "AUTHORIZATION_ACTIVE": blockers.append("AUTHORIZATION_INVALID")
        if confirmation != SEND_CONFIRMATION: blockers.append("WRONG_CONFIRMATION")
        if environment != "LAB": blockers.append("WRONG_ENVIRONMENT")
        if chat_id != LAB_CHAT_ID: blockers.append("WRONG_DESTINATION")
        if bot != LAB_BOT: blockers.append("WRONG_BOT")
        for name in ("preview", "reasoning", "reasoning_audit", "governance_evaluation", "observation_governance", "publication_review"):
            if not fingerprints.get(name): blockers.append(name.upper() + "_FINGERPRINT_REQUIRED")
        observation=self.connection.execute("SELECT observation_json FROM forward_test_observations WHERE observation_id=?",(observation_id,)).fetchone()
        if not observation:blockers.append("OBSERVATION_NOT_FOUND")
        elif json.loads(observation[0]).get("message_fingerprint")!=fingerprints.get("preview"):blockers.append("PREVIEW_FINGERPRINT_MISMATCH")
        reasoning=self.connection.execute("SELECT reasoning_id,reasoning_status FROM prediction_reasoning_records WHERE observation_id=? AND reasoning_fingerprint=?",(observation_id,fingerprints.get("reasoning"))).fetchone()
        if not reasoning or reasoning[1]!="REASONING_CREATED":blockers.append("REASONING_FINGERPRINT_MISMATCH")
        audit=self.connection.execute("SELECT status FROM prediction_reasoning_audits WHERE reasoning_id=? AND audit_fingerprint=?",(reasoning[0] if reasoning else "",fingerprints.get("reasoning_audit"))).fetchone()
        if not audit or audit[0] not in {"REASONING_AUDIT_PASSED","REASONING_AUDIT_WARNING"}:blockers.append("REASONING_AUDIT_BLOCKED")
        governance=self.connection.execute("SELECT evaluation_id,cutoff_utc FROM forward_test_governance_evaluations WHERE evaluation_fingerprint=?",(fingerprints.get("governance_evaluation"),)).fetchone()
        if not governance:blockers.append("GOVERNANCE_FINGERPRINT_MISMATCH")
        else:
            age=_utc(now)-datetime.fromisoformat(governance[1].replace("Z","+00:00")).astimezone(timezone.utc)
            if age.total_seconds()<0 or age>timedelta(hours=DEFAULT_POLICY.maximum_evaluation_age_hours):blockers.append("GOVERNANCE_EVIDENCE_STALE")
            decision=self.connection.execute("SELECT publication_impact FROM forward_test_governance_decisions WHERE evaluation_id=?",(governance[0],)).fetchone()
            if not decision or decision[0]=="BLOCK":blockers.append("GOVERNANCE_BLOCKED")
        snapshot=self.connection.execute("SELECT publication_decision FROM forward_test_observation_governance_snapshots WHERE observation_id=? AND evaluation_id=? AND snapshot_fingerprint=?",(observation_id,governance[0] if governance else "",fingerprints.get("observation_governance"))).fetchone()
        if not snapshot or snapshot[0] not in {"ALLOW","WARNING","GOVERNANCE_PUBLICATION_ALLOWED","GOVERNANCE_WARNING"}:blockers.append("OBSERVATION_GOVERNANCE_BLOCKED")
        review=self.connection.execute("SELECT review_status FROM forward_test_publication_reviews WHERE observation_id=? AND review_fingerprint=?",(observation_id,fingerprints.get("publication_review"))).fetchone()
        if not review or review[0]!="LAB_PUBLICATION_REVIEW_PASSED":blockers.append("PUBLICATION_REVIEW_BLOCKED")
        if observation_id in status.get("consumed_observation_ids", ()): blockers.append("AUTHORIZATION_ALREADY_CONSUMED")
        return {"status": "LAB_MANUAL_SEND_AUTHORIZED" if not blockers else "LAB_MANUAL_SEND_REJECTED", "authorization_id": authorization_id, "observation_id": observation_id, "blocker_codes": sorted(set(blockers)), "transport_constructed": False, "telegram_send_executed": False}

    def start_execution(self, authorization_id: str, readiness: dict, *, started_at_utc: datetime, request: dict) -> dict:
        if readiness["outcome"] not in {"LAB_LAUNCH_READY", "LAB_LAUNCH_READY_WITH_WARNINGS"}: raise LaunchConflict("A passing final readiness audit is required.")
        material={"authorization_id":authorization_id,"readiness_audit_id":readiness["audit_id"],"request":request,"outcome":"EXECUTION_STARTED","started_at_utc":_utc(started_at_utc).isoformat(),"telegram_sends":0};fp=fingerprint(material);value={**material,"execution_id":"lab-launch-execution-"+fp,"execution_fingerprint":fp}
        with self.connection: self.connection.execute("INSERT OR IGNORE INTO lab_launch_executions VALUES (?,?,?,?,?,?,?)",(value["execution_id"],authorization_id,readiness["audit_id"],value["outcome"],fp,canonical_json(value),value["started_at_utc"]))
        return value

    def append_stage(self, execution_id: str, order: int, name: str, status: str, *, occurred_at_utc: datetime, evidence: dict | None = None) -> dict:
        material={"execution_id":execution_id,"stage_order":order,"stage_name":name,"stage_status":status,"evidence":evidence or {},"occurred_at_utc":_utc(occurred_at_utc).isoformat()};fp=fingerprint(material);value={**material,"event_id":"lab-launch-stage-"+fp,"event_fingerprint":fp}
        try:
            with self.connection:self.connection.execute("INSERT INTO lab_launch_stage_events VALUES (?,?,?,?,?,?,?,?)",(value["event_id"],execution_id,order,name,status,fp,canonical_json(value),value["occurred_at_utc"]))
        except Exception:
            row=self.connection.execute("SELECT event_json FROM lab_launch_stage_events WHERE execution_id=? AND stage_order=?",(execution_id,order)).fetchone()
            if not row or json.loads(row[0])!=value:raise LaunchConflict("Stage replay conflict.")
        return value

    def post_run_audit(self, execution_id: str, *, audited_at_utc: datetime, facts: dict) -> dict:
        required=("backup_before_run","fixture_before_inference","odds_before_inference","odds_before_kickoff","baseline_compatible","exact_model_generation","exact_calibration_artifact","reasoning_audit_passed","governance_snapshot_present","publication_review_linked","database_integrity")
        blockers=[name.upper() for name in required if not facts.get(name)]
        if facts.get("official_mutations") or facts.get("telegram_sends") or facts.get("scheduling_changes") or facts.get("bookmaker_transactions"):blockers.append("ISOLATION_VIOLATION")
        outcome="LAB_RUN_AUDIT_PASSED" if not blockers else "LAB_RUN_AUDIT_BLOCKED";material={"execution_id":execution_id,"outcome":outcome,"blockers":blockers,"facts":facts,"audited_at_utc":_utc(audited_at_utc).isoformat()};fp=fingerprint(material);value={**material,"run_audit_id":"lab-run-audit-"+fp,"audit_fingerprint":fp}
        with self.connection:self.connection.execute("INSERT OR IGNORE INTO lab_run_audits VALUES (?,?,?,?,?,?)",(value["run_audit_id"],execution_id,outcome,fp,canonical_json(value),value["audited_at_utc"]))
        return value

    def _authorization_event(self, authorization_id: str, event_type: str, operator: str, linked: str | None, occurred: datetime) -> dict:
        if not self.connection.execute("SELECT 1 FROM lab_launch_authorizations WHERE authorization_id=?",(authorization_id,)).fetchone():raise LaunchConflict("Authorization not found.")
        material={"authorization_id":authorization_id,"event_type":event_type,"linked_identifier":linked,"operator_identity":operator,"occurred_at_utc":_utc(occurred).isoformat()};fp=fingerprint(material);value={**material,"event_id":"lab-launch-authorization-event-"+fp,"event_fingerprint":fp}
        with self.connection:self.connection.execute("INSERT OR IGNORE INTO lab_launch_authorization_events VALUES (?,?,?,?,?,?,?,?)",(value["event_id"],authorization_id,event_type,linked,operator,fp,canonical_json(value),value["occurred_at_utc"]))
        return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None: raise ValueError("UTC offset is required.")
    return value.astimezone(timezone.utc)
