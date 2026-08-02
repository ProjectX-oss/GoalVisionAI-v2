"""Explicit operator CLI. No command sends Telegram or schedules work."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database import Database, MigrationManager
from app.forward_test_governance.policy import DEFAULT_POLICY
from app.forward_test_governance_review import GovernancePolicyReviewService, review_governance_policy

from .backup import BackupConflict, LabBackupService
from .service import LabLaunchService, LaunchConflict


def build_parser():
    parser=argparse.ArgumentParser(prog="goalvision-lab-launch",description="Manual-only GoalVision LAB launch governance.");sub=parser.add_subparsers(dest="command",required=True)
    def common(name):
        item=sub.add_parser(name);item.add_argument("--database",type=Path,required=True);item.add_argument("--output",choices=("human","json"),default="human");return item
    item=common("review-governance-policy")
    item=common("approve-governance-policy");item.add_argument("--review-id",required=True);item.add_argument("--policy-fingerprint",required=True);item.add_argument("--operator",required=True);item.add_argument("--confirmation",required=True)
    item=common("revoke-governance-policy");item.add_argument("--approval-id",required=True);item.add_argument("--operator",required=True);item.add_argument("--confirmation",required=True)
    item=common("authorize-first-lab-launch");item.add_argument("--approval-id",required=True);item.add_argument("--champion-generation-id",required=True);item.add_argument("--calibration-artifact-id",required=True);item.add_argument("--operator",required=True);item.add_argument("--confirmation",required=True);item.add_argument("--hours",type=int,default=72)
    item=common("inspect-launch-authorization");item.add_argument("--authorization-id",required=True)
    item=common("revoke-launch-authorization");item.add_argument("--authorization-id",required=True);item.add_argument("--operator",required=True);item.add_argument("--confirmation",required=True)
    item=common("final-readiness-audit");item.add_argument("--authorization-id",required=True)
    item=common("pro-preflight");item.add_argument("--network-verify",action="store_true")
    for name in ("create-backup","verify-backup","restore-rehearsal"):
        item=common(name);item.add_argument("--backup-root",type=Path,required=True)
        if name!="create-backup":item.add_argument("--backup-id",required=True)
        if name=="restore-rehearsal":item.add_argument("--destination",type=Path,required=True)
    item=common("first-genuine-lab-run");item.add_argument("--authorization-id",required=True);item.add_argument("--backup-root",type=Path,required=True);item.add_argument("--env-file",type=Path,default=Path(".env"));item.add_argument("--capability-cache",type=Path,default=Path("var/api_football_capabilities.json"));item.add_argument("--max-candidates",type=int,default=50);item.add_argument("--max-calls",type=int,default=40);item.add_argument("--daily-reserve",type=int,default=20)
    item=common("post-match-review");item.add_argument("--observation-id",required=True)
    item=common("controlled-rehearsal");item.add_argument("--backup-root",type=Path,required=True)
    return parser


def main(argv=None):
    args=build_parser().parse_args(argv);now=datetime.now(timezone.utc);db=Database(args.database)
    try:
        MigrationManager(db.connection).migrate();reviews=GovernancePolicyReviewService(db.connection);launch=LabLaunchService(db.connection)
        if args.command=="review-governance-policy":value=reviews.persist_review(review_governance_policy(reviewed_at_utc=now))
        elif args.command=="approve-governance-policy":value=reviews.approve(args.review_id,args.policy_fingerprint,args.operator,args.confirmation,approved_at_utc=now)
        elif args.command=="revoke-governance-policy":value=reviews.revoke(args.approval_id,args.operator,args.confirmation,occurred_at_utc=now)
        elif args.command=="authorize-first-lab-launch":value=launch.authorize(args.approval_id,args.operator,args.confirmation,authorized_at_utc=now,expires_at_utc=now+timedelta(hours=args.hours),champion_generation_id=args.champion_generation_id,calibration_artifact_id=args.calibration_artifact_id)
        elif args.command=="inspect-launch-authorization":value=launch.status(args.authorization_id,now=now)
        elif args.command=="revoke-launch-authorization":value=launch.revoke(args.authorization_id,args.operator,args.confirmation,occurred_at_utc=now)
        elif args.command=="final-readiness-audit":value=launch.readiness_audit(args.authorization_id,audited_at_utc=now)
        elif args.command=="pro-preflight":
            if args.network_verify:value=asyncio.run(_network_preflight(launch,now))
            else:value=launch.preflight(checked_at_utc=now,network_verified=False)
        elif args.command in {"create-backup","verify-backup","restore-rehearsal"}:
            backup=LabBackupService(db.connection,args.database,args.backup_root)
            if args.command=="create-backup":value=backup.create(created_at_utc=now)
            elif args.command=="verify-backup":value=backup.verify(args.backup_id,verified_at_utc=now)
            else:value=backup.restore_rehearsal(args.backup_id,args.destination)
        elif args.command=="first-genuine-lab-run":value=_first_run_boundary(launch,db,args,now)
        elif args.command=="post-match-review":value=_post_match(db,args.observation_id,now)
        else:
            from .controlled import run_controlled_rehearsal
            value=run_controlled_rehearsal(db,args.database,args.backup_root,now)
        return _render(value,args.output,0)
    except (LaunchConflict,BackupConflict,ValueError,OSError) as exc:return _render({"status":"BLOCKED","reason":str(exc),"telegram_sends":0},args.output,4)
    finally:db.close()


def _first_run_boundary(launch,db,args,now):
    readiness=launch.readiness_audit(args.authorization_id,audited_at_utc=now)
    if readiness["outcome"] not in {"LAB_LAUNCH_READY","LAB_LAUNCH_READY_WITH_WARNINGS"}:return {"outcome":"AUTHORIZATION_INVALID","readiness":readiness,"provider_calls":0,"telegram_sends":0}
    row=db.connection.execute("SELECT preflight_json,checked_at_utc FROM lab_launch_preflights WHERE outcome='PRO_PLAN_READY' ORDER BY checked_at_utc DESC LIMIT 1").fetchone()
    fresh=row and now-datetime.fromisoformat(row[1].replace("Z","+00:00")).astimezone(timezone.utc)<=timedelta(hours=1)
    if not fresh:return {"outcome":"PROVIDER_PLAN_BLOCKED","reason":"Run a fresh explicit bounded Pro preflight first; no network call was made.","readiness":readiness,"provider_calls":0,"telegram_sends":0,"next_command":"python -m app.lab_launch_readiness pro-preflight --network-verify"}
    backup_service=LabBackupService(db.connection,args.database,args.backup_root);backup=backup_service.create(created_at_utc=now);verification=backup_service.verify(backup["backup_id"],verified_at_utc=now)
    if verification["outcome"]!="BACKUP_VERIFIED":return {"outcome":"BACKUP_FAILED","backup":backup,"verification":verification,"provider_calls":0,"telegram_sends":0}
    execution=launch.start_execution(args.authorization_id,readiness,started_at_utc=now,request={"max_candidates":args.max_candidates,"max_calls":args.max_calls,"daily_reserve":args.daily_reserve})
    from app.current_odds_forward_test.cli import _first_lab_dry_run
    args.run_id=execution["execution_id"];buffer=io.StringIO()
    with redirect_stdout(buffer):code=asyncio.run(_first_lab_dry_run(args))
    raw=buffer.getvalue().strip();detail=json.loads(raw) if args.output=="json" and raw else {"operator_output":raw}
    outcome=detail.get("outcome") or detail.get("terminal_outcome") or ("FIRST_LAB_DRY_RUN_COMPLETED" if code==0 else "PUBLICATION_REVIEW_BLOCKED")
    stages=("VERIFY_ENVIRONMENT","VERIFY_POLICY_APPROVAL","VERIFY_AUTHORIZATION","VERIFY_CAPACITY","FINAL_READINESS_AUDIT","VERIFY_PRO_CAPABILITIES","VERIFY_QUOTA","CREATE_BACKUP","VERIFY_BACKUP","START_IMMUTABLE_EXECUTION","DISCOVER_FIXTURE","PREFILTER_CANDIDATES","CAPTURE_BASELINE","CAPTURE_EXACT_ODDS","SEAL_FIXTURE_ODDS","CREATE_MODEL_INPUT","RESOLVE_CHAMPION","INFERENCE","CALIBRATION","CALIBRATION_QUALITY","DISTRIBUTION_SHIFT","EVALUATE_MARKETS","CREATE_OBSERVATION","CREATE_REASONING","AUDIT_REASONING","EVALUATE_GOVERNANCE","PERSIST_GOVERNANCE_SNAPSHOT","CREATE_LAB_PREVIEW","CREATE_PUBLICATION_REVIEW","STOP_BEFORE_TELEGRAM")
    for order,name in enumerate(stages,1):launch.append_stage(execution["execution_id"],order,name,"RECONCILED_COMPLETED" if code==0 else "RECONCILED_STOPPED",occurred_at_utc=now+timedelta(microseconds=order),evidence={"underlying_first_lab_run_id":execution["execution_id"],"terminal_outcome":outcome})
    return {"outcome":outcome,"execution":execution,"backup":backup,"backup_verification":verification,"workflow":detail,"provider_calls":"BOUNDED_BY_MAX_CALLS","telegram_sends":0,"stopped_before_telegram":True}


async def _network_preflight(launch,now):
    from app.football.client import FootballClient
    client=FootballClient(request_limit=1)
    try:
        payload=await client.account_status();response=payload.get("response",{}) if isinstance(payload,dict) else {};subscription=response.get("subscription",{}) if isinstance(response,dict) else {};plan=str(subscription.get("plan") or subscription.get("name") or "UNKNOWN");quota=client.quota_snapshot();limit=quota.get("daily_limit") or (response.get("requests") or {}).get("limit_day")
        if plan.upper()=="UNKNOWN" and isinstance(limit,int):plan="FREE" if limit<=100 else "PRO"
        remaining=quota.get("remaining") if quota.get("remaining") is not None else quota.get("daily_remaining")
        return launch.preflight(checked_at_utc=now,network_verified=True,provider_facts={"authenticated":True,"plan":plan,"current_season_access":plan.upper() not in {"FREE","UNKNOWN"},"quota_remaining":remaining or 0,"required_calls":12,"provider_call_count":1})
    except Exception:return launch.preflight(checked_at_utc=now,network_verified=True,provider_facts={"authenticated":False,"plan":"UNKNOWN","provider_call_count":1})
    finally:await client.close()


def _post_match(database,observation_id,now):
    connection=database.connection
    observation=connection.execute("SELECT observation_json FROM forward_test_observations WHERE observation_id=?",(observation_id,)).fetchone();result=connection.execute("SELECT result_json FROM forward_test_results WHERE observation_id=?",(observation_id,)).fetchone();settlement=connection.execute("SELECT settlement_json FROM forward_test_settlements WHERE observation_id=?",(observation_id,)).fetchone()
    blockers=[]
    if not observation:blockers.append("OBSERVATION_NOT_FOUND")
    if not result:blockers.append("RESULT_REQUIRED")
    if not settlement:blockers.append("SETTLEMENT_REQUIRED")
    artifacts={};warnings=[]
    if not blockers:
        try:
            from app.current_odds_forward_test.audit import audit_observation
            from app.current_odds_forward_test.operations import FirstLabOperationsRepository,build_result_preview
            from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
            repository=SQLiteForwardTestRepository(database,migrate=False);artifacts["lifecycle_audit"]=audit_observation(repository,observation_id);artifacts["result_preview"]=build_result_preview(repository,observation_id,created_at=now,persist=FirstLabOperationsRepository(database,migrate=False))
        except Exception as exc:warnings.append("LIFECYCLE_OR_PREVIEW_REFRESH_FAILED:"+type(exc).__name__)
        try:
            from app.forward_test_monitoring import MonitoringService,SQLiteMonitoringRepository
            monitoring=MonitoringService(SQLiteMonitoringRepository(database,migrate=False));artifacts["monitoring_snapshot"]=monitoring.snapshot(now);artifacts["weekly_report"]=monitoring.report("WEEKLY",now);artifacts["cumulative_report"]=monitoring.report("CUMULATIVE",now)
        except Exception as exc:warnings.append("MONITORING_REFRESH_FAILED:"+type(exc).__name__)
        try:
            from app.forward_test_governance import GovernanceService
            governance=GovernanceService(database);artifacts["governance_reevaluation"]=governance.evaluate(now.isoformat())
        except Exception as exc:warnings.append("GOVERNANCE_REEVALUATION_FAILED:"+type(exc).__name__)
    outcome="POST_MATCH_REVIEW_INCOMPLETE" if blockers else "POST_MATCH_REVIEW_WARNING" if warnings else "POST_MATCH_REVIEW_READY"
    material={"observation_id":observation_id,"outcome":outcome,"blockers":blockers,"warnings":warnings,"result":json.loads(result[0]) if result else None,"settlement":json.loads(settlement[0]) if settlement else None,"artifacts":artifacts,"automatic_result_publication":False,"provider_calls":0,"telegram_sends":0,"reviewed_at_utc":now.isoformat()};from app.real_match_lab_analysis.fingerprint import canonical_json,fingerprint;fp=fingerprint(material);value={**material,"review_id":"lab-post-match-review-"+fp,"review_fingerprint":fp}
    with connection:connection.execute("INSERT OR IGNORE INTO lab_launch_post_match_reviews VALUES (?,?,?,?,?,?)",(value["review_id"],observation_id,value["outcome"],fp,canonical_json(value),value["reviewed_at_utc"]))
    return value


def _render(value,mode,code):
    if mode=="json":print(json.dumps(value,sort_keys=True,ensure_ascii=True,default=str))
    else:
        for key,val in value.items():print(f"{key}: {val}")
    return code
