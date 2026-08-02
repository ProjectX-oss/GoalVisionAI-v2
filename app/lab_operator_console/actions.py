"""Central POST-only console action boundary and append-only audit."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.current_odds_forward_test.operations import FirstLabOperationsRepository, build_publication_review
from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
from app.current_odds_forward_test.service import ForwardTestService
from app.database import Database
from app.forward_test_monitoring import MonitoringService, SQLiteMonitoringRepository
from app.forward_test_monitoring.exports import export_bundle
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

from .models import ActionRequest


ACTION_POLICY={
    "CREATE_PUBLICATION_REVIEW":("CREATE_PUBLICATION_REVIEW",0,False,"forward_test_publication_reviews"),
    "IMPORT_RESULT":("IMPORT_FORWARD_TEST_RESULT",0,False,"forward_test_results"),
    "SETTLE":("SETTLE_FORWARD_TEST_OBSERVATION",0,False,"forward_test_settlements"),
    "GENERATE_WEEKLY_REPORT":("GENERATE_WEEKLY_REPORT",0,False,"forward_test_monitoring_reports"),
    "GENERATE_CUMULATIVE_REPORT":("GENERATE_CUMULATIVE_REPORT",0,False,"forward_test_monitoring_reports"),
    "REPRODUCE_REPORT":("REPRODUCE_REPORT",0,False,"none"),
    "COMPARE_REPORTS":("COMPARE_REPORTS",0,False,"none"),
    "CREATE_EXPORT":("CREATE_REPORT_EXPORT",0,False,"forward_test_monitoring_exports"),
    "ACKNOWLEDGE_INCIDENT":("ACKNOWLEDGE_INCIDENT",0,False,"forward_test_monitoring_incident_events"),
    "RESOLVE_INCIDENT":("RESOLVE_INCIDENT",0,False,"forward_test_monitoring_incident_events"),
    "READINESS_NETWORK_VERIFY":("VERIFY_API_FOOTBALL_ONCE",1,False,"lab_operator_console_actions"),
    "BOUNDED_DISCOVERY":("RUN_BOUNDED_DISCOVERY",40,False,"first_lab_run_executions"),
    "FAKE_LAB_SEND":("FAKE_LAB_SEND_ONLY",0,True,"lab_operator_console_action_events"),
}


class ConsoleActionConflict(RuntimeError):pass


class ConsoleActionService:
    def __init__(self,database:Database,*,actions_enabled:bool=False,allowed_output_roots:tuple[Path,...]=(),maximum_export_bytes:int=10_000_000) -> None:
        self.database=database;self.connection=database.connection;self.enabled=actions_enabled
        self.allowed_output_roots=tuple(Path(root).resolve() for root in allowed_output_roots);self.maximum_export_bytes=maximum_export_bytes

    def execute(self,request:ActionRequest) -> dict[str,Any]:
        if not self.enabled: return {"status":"ACTION_BLOCKED_READ_ONLY","provider_calls":0,"telegram_calls":0}
        if request.action_type not in ACTION_POLICY:raise ValueError("Unsupported console action.")
        required,max_calls,telegram_possible,scope=ACTION_POLICY[request.action_type]
        if request.confirmation!=required:return {"status":"ACTION_BLOCKED_CONFIRMATION","required_confirmation":required,"provider_calls":0,"telegram_calls":0}
        normalized=_redact(request.normalized_input); input_fp=fingerprint(normalized); material={"request_id":request.request_id,"action_type":request.action_type,"operator_identifier":request.operator_identifier,"source_page":request.source_page,"target_identifier":request.target_identifier,"requested_at_utc":request.requested_at_utc,"normalized_input":normalized,"input_fingerprint":input_fp,"confirmation_status":"CONFIRMED","expected_side_effects":scope,"maximum_provider_calls":max_calls,"telegram_possible":telegram_possible,"mutation_scope":scope}; action_fp=fingerprint(material); action_id="lab-console-action-"+action_fp; material.update({"action_id":action_id,"action_fingerprint":action_fp})
        existing=self.connection.execute("SELECT * FROM lab_operator_console_actions WHERE request_id=?",(request.request_id,)).fetchone()
        if existing:
            if existing["action_fingerprint"]!=action_fp:raise ConsoleActionConflict("CONSOLE_ACTION_REPLAY_CONFLICT")
            event=self.connection.execute("SELECT event_json FROM lab_operator_console_action_events WHERE action_id=? ORDER BY event_sequence DESC LIMIT 1",(action_id,)).fetchone(); return json.loads(event[0]) if event else {"status":"STARTED","action_id":action_id,"replayed":True}
        with self.connection:
            self.connection.execute("INSERT INTO lab_operator_console_actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(action_id,request.request_id,request.action_type,request.operator_identifier,request.source_page,request.target_identifier,request.requested_at_utc,input_fp,"CONFIRMED",scope,max_calls,int(telegram_possible),scope,action_fp,canonical_json(material)))
            self._event(action_id,0,"STARTED",request.requested_at_utc,0,0,None,None,None,None)
        try:
            outcome=self._dispatch(request); event=self._event(action_id,1,outcome["status"],request.requested_at_utc,outcome.get("provider_calls",0),outcome.get("telegram_calls",0),outcome.get("created_record_type"),outcome.get("created_record_id"),input_fp,outcome.get("after_fingerprint")); return event
        except Exception as exc:
            self._event(action_id,1,"FAILED",request.requested_at_utc,0,0,None,None,input_fp,fingerprint({"error_type":type(exc).__name__})); raise

    def _dispatch(self,request):
        ft=SQLiteForwardTestRepository(self.database,migrate=False); monitoring=MonitoringService(SQLiteMonitoringRepository(self.database,migrate=False)); now=datetime.fromisoformat(request.requested_at_utc.replace("Z","+00:00"))
        if request.action_type=="CREATE_PUBLICATION_REVIEW":
            value=build_publication_review(ft,request.target_identifier or "",reviewed_at=now,persist=FirstLabOperationsRepository(self.database,migrate=False)); return _created("forward_test_publication_reviews",value.get("review_id"),value.get("review_fingerprint"),value["status"])
        if request.action_type=="IMPORT_RESULT":
            value=ForwardTestService(ft).record_result(request.target_identifier or "",request.normalized_input["result"]); return _created("forward_test_results",value.result_id,value.result_fingerprint,"COMPLETED")
        if request.action_type=="SETTLE":
            value=ForwardTestService(ft).settle(request.target_identifier or "",settled_at_utc=now); return _created("forward_test_settlements",value.settlement_id,value.settlement_fingerprint,"COMPLETED")
        if request.action_type in {"GENERATE_WEEKLY_REPORT","GENERATE_CUMULATIVE_REPORT"}:
            kind="WEEKLY" if request.action_type.endswith("WEEKLY_REPORT") else "CUMULATIVE"; value=monitoring.report(kind,now); return _created("forward_test_monitoring_reports",value["report_id"],value["report_fingerprint"],"COMPLETED")
        if request.action_type=="REPRODUCE_REPORT":
            value=monitoring.reproduce(request.target_identifier or ""); return {"status":"COMPLETED" if value["matches"] else "BLOCKED","provider_calls":0,"telegram_calls":0,"after_fingerprint":fingerprint(value)}
        if request.action_type=="COMPARE_REPORTS":
            left=monitoring.repository.report(request.target_identifier or "");right=monitoring.repository.report(str(request.normalized_input.get("comparison_report_id","")))
            value={"left_report_id":left["report_id"],"right_report_id":right["report_id"],"left_metrics":left["metrics"],"right_metrics":right["metrics"]}
            return {"status":"COMPLETED","provider_calls":0,"telegram_calls":0,"after_fingerprint":fingerprint(value)}
        if request.action_type=="CREATE_EXPORT":
            if not self.allowed_output_roots:raise ValueError("No export root is configured.")
            name=str(request.normalized_input.get("output_name","")).strip()
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}",name):raise ValueError("Export name must be a safe local directory name.")
            report=monitoring.repository.report(request.target_identifier or "")
            if len(canonical_json(report).encode("utf-8"))>self.maximum_export_bytes:raise ValueError("Report exceeds the configured export size limit.")
            output=(self.allowed_output_roots[0]/name).resolve()
            if output.parent!=self.allowed_output_roots[0]:raise ValueError("Export destination is outside the allowed root.")
            value=export_bundle(report,output)
            if sum(item["bytes"] for item in value["files"])>self.maximum_export_bytes:raise ValueError("Export exceeds the configured size limit.")
            return _created("forward_test_monitoring_exports",value["manifest_fingerprint"],value["manifest_fingerprint"],"COMPLETED")
        if request.action_type in {"ACKNOWLEDGE_INCIDENT","RESOLVE_INCIDENT"}:
            value=monitoring.acknowledge_incident(request.target_identifier or "",request.operator_identifier,str(request.normalized_input.get("reason","")),now,resolved=request.action_type=="RESOLVE_INCIDENT"); return _created("forward_test_monitoring_incident_events",value["event_id"],value["event_fingerprint"],"COMPLETED")
        if request.action_type=="FAKE_LAB_SEND":return {"status":"COMPLETED","provider_calls":0,"telegram_calls":0,"after_fingerprint":fingerprint({"fake_transport":True,"target":request.target_identifier})}
        return {"status":"BLOCKED","provider_calls":0,"telegram_calls":0,"after_fingerprint":fingerprint({"reason":"Provider action requires a separately injected bounded executor."})}

    def _event(self,action_id,sequence,outcome,occurred,provider_calls,telegram_calls,record_type,record_id,before,after):
        normalized="COMPLETED" if outcome not in {"STARTED","BLOCKED","FAILED"} else outcome; material={"action_id":action_id,"event_sequence":sequence,"outcome":normalized,"provider_call_count":provider_calls,"telegram_call_count":telegram_calls,"created_record_type":record_type,"created_record_id":record_id,"before_fingerprint":before,"after_fingerprint":after,"occurred_at_utc":occurred}; fp=fingerprint(material); material.update({"event_id":"lab-console-event-"+fp,"event_fingerprint":fp,"status":normalized})
        with self.connection:self.connection.execute("INSERT OR IGNORE INTO lab_operator_console_action_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(material["event_id"],action_id,sequence,normalized,provider_calls,telegram_calls,record_type,record_id,before,after,occurred,fp,canonical_json(material)))
        return material


def _created(kind,identifier,value_fp,status):return {"status":"COMPLETED" if "BLOCK" not in status else "BLOCKED","provider_calls":0,"telegram_calls":0,"created_record_type":kind,"created_record_id":identifier,"after_fingerprint":value_fp}
def _redact(value):
    blocked=("secret","token","key","credential","authorization","cookie")
    if isinstance(value,dict):return {str(k):"[REDACTED]" if any(word in str(k).lower() for word in blocked) else _redact(v) for k,v in sorted(value.items())}
    if isinstance(value,list):return [_redact(v) for v in value]
    text=str(value)
    return "[REDACTED]" if any(marker in text.lower() for marker in ("bearer ","api_key=","token=")) else value
