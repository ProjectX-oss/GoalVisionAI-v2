"""Typed presentation service; templates never access SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.database import Database
from app.forward_test_monitoring import MonitoringService, SQLiteMonitoringRepository

from .models import PageModel, TableModel


class ConsoleReadService:
    def __init__(self,database:Database,database_path:Path,*,controlled_demo:bool=False,page_size:int=100) -> None:
        self.database=database; self.connection=database.connection; self.path=database_path; self.demo=controlled_demo; self.page_size=page_size

    def page(self,name:str,identifier:str|None=None) -> PageModel:
        method:Callable[[str|None],PageModel]=getattr(self,f"_{name}",self._not_found); return method(identifier)

    def _overview(self,_):
        health=self._health(None); counts=self._counts(); activity=[]
        for table,time_col,id_col in (("first_lab_run_executions","created_at_utc","run_id"),("forward_test_observations","created_at_utc","observation_id"),("forward_test_results","result_retrieval_timestamp_utc","result_id"),("forward_test_settlements","settled_at_utc","settlement_id"),("forward_test_monitoring_reports","generated_at_utc","report_id"),("forward_test_monitoring_incidents","detected_at_utc","incident_id")):
            row=self._one(f"SELECT {id_col},{time_col} FROM {table} ORDER BY {time_col} DESC LIMIT 1") if self._table(table) else None
            activity.append((table,row[0] if row else "NONE",row[1] if row else "N/A"))
        warnings=["API-Football Free does not provide compatible 2026 team history; no genuine discovery should run before plan review."]
        if counts["pending_results"]:warnings.append(f"{counts['pending_results']} observations await results.")
        schema=self._one("SELECT MAX(version) FROM schema_migrations")[0]
        return PageModel("Overview",health.status,(("database_schema",schema),("database",str(self.path)))+tuple(counts.items()),(TableModel("Latest activity",("source","identifier","timestamp"),tuple(activity)),),tuple(warnings),self.demo)

    def _readiness(self,_):
        cache=self._latest_json_file(Path("var/api_football_capabilities.json")); runs=self._rows("SELECT run_id,mode,execution_state,created_at_utc FROM first_lab_run_executions ORDER BY created_at_utc DESC LIMIT ?",(self.page_size,)) if self._table("first_lab_run_executions") else ()
        from app.football.configuration import api_football_credential_status
        summary=("credential_status",api_football_credential_status()),("persisted_plan",self._json_find(cache,"plan","UNKNOWN")),("current_season_access",self._json_find(cache,"current_season_access","BLOCKED_OR_UNKNOWN")),("quota",self._json_find(cache,"quota","NOT_PERSISTED")),("capability_cache","AVAILABLE" if cache else "NOT_AVAILABLE"),("network_calls_current_request",0),("free_plan_example","FREE_PLAN_BLOCKED"),("simulated_pro_example","CONTROLLED_PRO_READY" if self.demo else "NOT_APPLICABLE"),("readiness_outcome","FREE_PLAN_BLOCKED" if not self.demo else "CONTROLLED_PRO_READY_AND_FREE_BLOCK_EXAMPLES")
        return PageModel("Readiness","BLOCKED" if not self.demo else "WARNING",summary,(TableModel("Persisted readiness runs",("run","mode","state","created"),runs),),("Opening this page performs no provider request.",),self.demo)

    def _discovery(self,_):
        runs=self._rows("SELECT run_id,mode,execution_state,created_at_utc,run_fingerprint FROM first_lab_run_executions ORDER BY created_at_utc DESC LIMIT ?",(self.page_size,)) if self._table("first_lab_run_executions") else ()
        stages=self._rows("SELECT run_id,stage_order,stage_name,stage_status,artifact_type,artifact_id,occurred_at_utc FROM first_lab_run_stage_events ORDER BY occurred_at_utc DESC,stage_order LIMIT ?",(self.page_size,)) if self._table("first_lab_run_stage_events") else ()
        return PageModel("Discovery runs","READ_ONLY",(("automatic_discovery",False),("network_calls_current_request",0)),(TableModel("Runs",("run","mode","state","created","fingerprint"),runs),TableModel("Stage and cost trace",("run","order","stage","status","artifact type","artifact","time"),stages)),("A bounded discovery requires an explicit confirmed POST action.",),self.demo)

    def _candidates(self,_): return self._evidence_search("Candidates",("candidate","fixture","competition","kickoff","status","reason"),("candidate_id","fixture_id","competition","kickoff_utc","status","reason_code"))
    def _fixtures(self,_): return self._evidence_search("Fixtures and baselines",("fixture","competition","season","kickoff","source","fingerprint"),("canonical_fixture_id","competition","season","kickoff_utc","provider_source_id","snapshot_fingerprint"))

    def _odds(self,identifier):
        query="SELECT odds_snapshot_id,canonical_fixture_id,kickoff_utc,provider_source_id,bookmaker_name,captured_at_utc,freshness_status,snapshot_fingerprint,snapshot_json FROM forward_test_odds_snapshots"; params=[]
        if identifier:query+=" WHERE odds_snapshot_id=?";params.append(identifier)
        query+=" ORDER BY captured_at_utc DESC LIMIT ?";params.append(self.page_size); rows=[]
        for row in self._rows(query,tuple(params)) if self._table("forward_test_odds_snapshots") else ():
            raw=json.loads(row[8]); markets=", ".join(f"{q.get('market')}={q.get('decimal_odds')}" for q in raw.get("quotes",()))
            rows.append(tuple(row[:8])+(markets,))
        return PageModel("Odds snapshots","READ_ONLY",(("credentials_displayed",False),("raw_provider_payloads_displayed",False)),(TableModel("Immutable odds",("snapshot","fixture","kickoff","provider","bookmaker","captured","freshness","fingerprint","canonical markets"),tuple(rows)),),(),self.demo)

    def _analyses(self,identifier):
        query="SELECT analysis_id,match_id,kickoff_utc,status,selected_market,result_snapshot,result_fingerprint,created_at FROM real_match_lab_analyses";params=[]
        if identifier:query+=" WHERE analysis_id=?";params.append(identifier)
        query+=" ORDER BY created_at DESC LIMIT ?";params.append(self.page_size); rows=[]
        for row in self._rows(query,tuple(params)) if self._table("real_match_lab_analyses") else ():
            result=json.loads(row[5]); evidence=result.get("evidence") or {}; evaluations=evidence.get("evaluations") or []
            safe=[item for item in evaluations if item.get("market") and "SCORE" not in item["market"] and "COMBO" not in item["market"]]
            markets=" | ".join(f"{e.get('market')}: raw {e.get('raw_probability')}, calibrated {e.get('calibrated_probability')}, odds {e.get('bookmaker_odds')}, EV {e.get('expected_value')}, rank {e.get('mathematical_rank')}, actionable {e.get('actionable')}" for e in safe)
            rows.append((row[0],row[1],row[2],row[3],row[4],evidence.get("model_artifact_id","UNKNOWN"),evidence.get("calibration_set_id","UNKNOWN"),markets,row[6],row[7]))
        return PageModel("Analysis and market comparison","READ_ONLY",(("canonical_market_maximum",11),("browser_inference",False)),(TableModel("Analyses",("analysis","fixture","kickoff","outcome","selected","model","calibration","market evaluations","fingerprint","created"),tuple(rows)),),(),self.demo)

    def _reasoning(self,identifier):
        query="""SELECT r.reasoning_id,r.observation_id,r.analysis_id,r.selected_market,r.reasoning_status,r.public_reasoning_fingerprint,r.reasoning_fingerprint,r.created_at_utc,r.reasoning_json,a.status,a.audit_fingerprint FROM prediction_reasoning_records r LEFT JOIN prediction_reasoning_audits a ON a.reasoning_id=r.reasoning_id""";params=[]
        if identifier:query+=" WHERE r.reasoning_id=? OR r.analysis_id=? OR r.observation_id=?";params.extend((identifier,identifier,identifier))
        query+=" ORDER BY r.created_at_utc DESC,r.reasoning_id LIMIT ?";params.append(self.page_size);rows=[]
        for row in self._rows(query,tuple(params)) if self._table("prediction_reasoning_records") else ():
            raw=json.loads(row[8]);rows.append(tuple(row[:8])+(raw.get("contribution_reproduction_status"),raw.get("explanation_stability_status"),raw.get("supporting_factors"),raw.get("opposing_factors"),raw.get("risk_factors"),raw.get("missing_data_disclosures"),raw.get("calibration_explanation"),raw.get("shift_explanation"),raw.get("confidence_explanation"),raw.get("counterfactuals"),raw.get("market_explanations"),raw.get("public_reasoning_html"),raw.get("operator_reasoning_json"),row[9],row[10]))
        columns=("reasoning","observation","analysis","market","status","public fingerprint","fingerprint","created","reproduction","stability","positive evidence","negative evidence","risks","missing data","calibration","shift","confidence","counterfactuals","rejected markets","public preview","operator JSON","audit","audit fingerprint")
        return PageModel("Prediction reasoning","READ_ONLY",(("browser_recalculation",False),("network_calls_current_request",0),("telegram_calls_current_request",0)),(TableModel("Immutable reasoning and audit",columns,tuple(rows)),),("Reasoning is coefficient evidence, not causation or proof of profitability.",),self.demo)

    def _observations(self,identifier):
        query="SELECT observation_id,canonical_fixture_id,analysis_id,odds_snapshot_id,status,actionable,preview_available,lab_send_eligible,official_eligible,evidence_tier,observation_fingerprint,created_at_utc FROM forward_test_observations";params=[]
        if identifier:query+=" WHERE observation_id=?";params.append(identifier)
        query+=" ORDER BY created_at_utc DESC LIMIT ?";params.append(self.page_size)
        return PageModel("Forward-test observations","READ_ONLY",(("official_eligibility_required",False),("evidence_tier","FORWARD_TEST_REAL_TIME")),(TableModel("Immutable observations",("observation","fixture","analysis","odds","status","actionable","preview","Lab eligible","Official eligible","tier","fingerprint","created"),self._rows(query,tuple(params)) if self._table("forward_test_observations") else ()),),(),self.demo)

    def _previews(self,identifier):
        query="SELECT observation_id,analysis_id,observation_json,created_at_utc FROM forward_test_observations WHERE preview_available=1";params=[]
        if identifier:query+=" AND observation_id=?";params.append(identifier)
        query+=" ORDER BY created_at_utc DESC LIMIT ?";params.append(self.page_size)
        rows=[]
        from app.prediction_explainability.presentation import compose_reasoned_message
        from app.prediction_explainability.repository import SQLiteReasoningRepository
        reasoning_repository=SQLiteReasoningRepository.from_connection(self.connection) if self._table("prediction_reasoning_records") else None
        for row in self._rows(query,tuple(params)) if self._table("forward_test_observations") else ():
            raw=json.loads(row[2]);reasoning=reasoning_repository.for_observation(row[0]) if reasoning_repository else None;audit=reasoning_repository.audit_for(reasoning.reasoning_id) if reasoning else None;reasoned=compose_reasoned_message(raw.get("message_preview") or "",reasoning) if reasoning else None
            rows.append((row[0],row[1],raw.get("message_preview"),raw.get("message_fingerprint"),reasoning.public_reasoning_html if reasoning else "REASONING_REQUIRED",reasoned["message_fingerprint"] if reasoned else None,audit.status if audit else "REASONING_AUDIT_REQUIRED",row[3]))
        return PageModel("LAB previews","PREVIEW_ONLY",(("telegram_sent",False),("notice","PREVIEW ONLY — NOTHING HAS BEEN SENT")),(TableModel("Telegram-safe previews",("observation","analysis","escaped source","original fingerprint","public reasoning","reasoned fingerprint","reasoning audit","created"),tuple(rows)),),("Copying a preview does not authorize publication.",),self.demo)

    def _reviews(self,identifier):
        query="SELECT review_id,observation_id,review_status,message_fingerprint,reviewed_at_utc,review_fingerprint,review_snapshot FROM forward_test_publication_reviews";params=[]
        if identifier:query+=" WHERE review_id=? OR observation_id=?";params.extend((identifier,identifier))
        query+=" ORDER BY reviewed_at_utc DESC LIMIT ?";params.append(self.page_size)
        return PageModel("Publication reviews","READ_ONLY",(("review_sends_telegram",False),),(TableModel("Rules and outcomes",("review","observation","status","message fingerprint","reviewed","fingerprint","rule snapshot"),self._rows(query,tuple(params)) if self._table("forward_test_publication_reviews") else ()),),(),self.demo)

    def _send_readiness(self,identifier):
        observations=self._observations(identifier).tables[0].rows; reviews=self._reviews(identifier).tables[0].rows
        enabled=bool(observations and reviews and reviews[0][2]=="LAB_PUBLICATION_REVIEW_PASSED" and observations[0][5] and not observations[0][7] and not observations[0][8])
        return PageModel("Manual send readiness","DISABLED",(("send_form_visible",enabled),("real_transport_available_from_console",False),("required_confirmation","SEND_TO_GOALVISION_AI_LAB"),("delivery_state","NOT_SENT")),(TableModel("Observation",self._observations(identifier).tables[0].columns,observations),TableModel("Review",self._reviews(identifier).tables[0].columns,reviews)),("This foundation never performs a real Telegram send.",),self.demo)

    def _results(self,identifier): return self._simple("Results","forward_test_results",("result_id","observation_id","canonical_fixture_id","final_home_score","final_away_score","final_status","result_retrieval_timestamp_utc","result_fingerprint"),"result_retrieval_timestamp_utc",identifier)
    def _settlements(self,identifier): return self._simple("Settlements","forward_test_settlements",("settlement_id","observation_id","result_id","market","outcome","settled_at_utc","settlement_fingerprint"),"settled_at_utc",identifier)

    def _monitoring(self,_):
        service=MonitoringService(SQLiteMonitoringRepository(self.database,migrate=False)); cutoff=datetime.now(timezone.utc); report=service.report("CUMULATIVE",cutoff,generated_at_utc=cutoff,persist=False); metrics=report["metrics"]
        explainability=report.get("explainability",{});summary=tuple(metrics["volume"].items())+(("sample_status",metrics["sample_status"]),("hypothetical_label","HYPOTHETICAL_FLAT_STAKE"),("net_units",metrics["hypothetical_flat_stake"]["net_profit_units"]),("roi",metrics["hypothetical_flat_stake"]["roi"]),("drawdown",metrics["hypothetical_flat_stake"]["maximum_drawdown"]),("calibration_status",metrics["calibration"]["status"]),("reasoning_records",explainability.get("reasoning_records_created",0)),("reasoning_audits",explainability.get("audit_status_counts",{})),("explanation_stability",explainability.get("stability_distribution",{})),("network_calls_current_request",0))
        findings=tuple((f["severity"],f["code"],f["affected_identifier"],f["detail"]) for f in report["data_quality"]["findings"])
        return PageModel("Monitoring",report["data_quality"]["status"],summary,(TableModel("Data quality",("severity","code","identifier","detail"),findings),),("Hypothetical results are not proof of profitability.",),self.demo)

    def _reports(self,identifier):
        query="SELECT report_id,report_kind,period_start_utc,period_end_utc,policy_version,report_fingerprint,report_json FROM forward_test_monitoring_reports";params=[]
        if identifier:query+=" WHERE report_id=?";params.append(identifier)
        query+=" ORDER BY generated_at_utc DESC LIMIT ?";params.append(self.page_size); rows=[]
        for row in self._rows(query,tuple(params)) if self._table("forward_test_monitoring_reports") else ():
            raw=json.loads(row[6]); rows.append(tuple(row[:6])+(raw.get("metrics",{}).get("sample_status"),raw.get("explainability",{}),raw.get("limitations",[])))
        return PageModel("Weekly and cumulative reports","READ_ONLY",(("automatic_publication",False),),(TableModel("Reports",("report","kind","start","end","policy","fingerprint","sample","explainability","limitations"),tuple(rows)),),(),self.demo)

    def _unresolved(self,_):
        service=MonitoringService(SQLiteMonitoringRepository(self.database,migrate=False)); rows=service.unresolved(datetime.now(timezone.utc)); values=tuple((r["state"],"WARNING" if r["overdue"] else "INFO",r["observation_id"],r["due_at_utc"],"Inspect linked immutable evidence; do not auto-resolve.") for r in rows)
        return PageModel("Unresolved items","WARNING" if values else "HEALTHY",(("count",len(values)),),(TableModel("Manual queue",("group","severity","identifier","due","recommended action"),values),),(),self.demo)

    def _incidents(self,identifier):
        incidents=self._rows("SELECT incident_id,incident_code,severity,affected_identifier,detected_at_utc,incident_fingerprint FROM forward_test_monitoring_incidents ORDER BY detected_at_utc DESC LIMIT ?",(self.page_size,)) if self._table("forward_test_monitoring_incidents") else (); events=self._rows("SELECT incident_id,event_type,operator_identity,reason,occurred_at_utc,event_fingerprint FROM forward_test_monitoring_incident_events ORDER BY occurred_at_utc DESC LIMIT ?",(self.page_size,)) if self._table("forward_test_monitoring_incident_events") else ()
        return PageModel("Incidents","WARNING" if incidents else "HEALTHY",(("incident_count",len(incidents)),),(TableModel("Incidents",("incident","class","severity","linked identifier","created","fingerprint"),incidents),TableModel("Acknowledgements and resolutions",("incident","event","operator","reason","occurred","fingerprint"),events)),("Acknowledgement never repairs corrupt evidence.",),self.demo)

    def _health(self,_):
        service=MonitoringService(SQLiteMonitoringRepository(self.database,migrate=False)); raw=service.health(datetime.now(timezone.utc)); latest=self._counts(); summary=tuple(raw.items())+tuple(("count_"+k,v) for k,v in latest.items())+(("database",str(self.path)),("network_calls_current_request",0))
        return PageModel("Operational health",raw["status"].removeprefix("FORWARD_TEST_"),summary,(),(),self.demo)

    def _actions(self,_):
        actions=self._rows("SELECT action_id,action_type,operator_identifier,source_page,target_identifier,requested_at_utc,maximum_provider_calls,telegram_possible,mutation_scope,action_fingerprint FROM lab_operator_console_actions ORDER BY requested_at_utc DESC LIMIT ?",(self.page_size,)) if self._table("lab_operator_console_actions") else (); events=self._rows("SELECT action_id,event_sequence,outcome,provider_call_count,telegram_call_count,created_record_type,created_record_id,occurred_at_utc,event_fingerprint FROM lab_operator_console_action_events ORDER BY occurred_at_utc DESC LIMIT ?",(self.page_size,)) if self._table("lab_operator_console_action_events") else ()
        return PageModel("Operator action audit","READ_ONLY",(("actions",len(actions)),),(TableModel("Actions",("id","type","operator","source","target","requested","max provider calls","Telegram possible","scope","fingerprint"),actions),TableModel("Events",("action","sequence","outcome","provider calls","Telegram calls","record type","record","time","fingerprint"),events)),(),self.demo)

    def _simple(self,title,table,columns,time_col,identifier):
        query=f"SELECT {','.join(columns)} FROM {table}";params=[]
        if identifier:query+=f" WHERE {columns[0]}=? OR observation_id=?";params.extend((identifier,identifier))
        query+=f" ORDER BY {time_col} DESC LIMIT ?";params.append(self.page_size)
        return PageModel(title,"READ_ONLY",(("immutable",True),),(TableModel(title,columns,self._rows(query,tuple(params)) if self._table(table) else ()),),(),self.demo)

    def _evidence_search(self,title,columns,keys):
        rows=[]
        for table,json_col in (("first_lab_run_stage_events","event_snapshot"),("forward_test_rejections","rejection_json")):
            if not self._table(table):continue
            for raw, in self._rows(f"SELECT {json_col} FROM {table} LIMIT ?",(self.page_size,)):
                value=json.loads(raw); rows.append(tuple(self._json_find(value,key,"N/A") for key in keys))
        return PageModel(title,"READ_ONLY",(("persisted_only",True),),(TableModel(title,columns,tuple(rows)),),(),self.demo)

    def _counts(self):
        def count(table,where="1=1"):return self._one(f"SELECT COUNT(*) FROM {table} WHERE {where}")[0] if self._table(table) else 0
        return {"discovery_runs":count("first_lab_run_executions"),"candidates":count("first_lab_run_stage_events","stage_name LIKE '%CANDIDATE%'"),"observations":count("forward_test_observations"),"actionable":count("forward_test_observations","actionable=1"),"blocked":count("forward_test_observations","status='BLOCKED'"),"no_selections":count("forward_test_observations","status='NO_SELECTION'"),"reviews":count("forward_test_publication_reviews"),"lab_publications":count("real_match_lab_deliveries","status='SENT'"),"pending_results":count("forward_test_observations")-count("forward_test_results"),"settlements":count("forward_test_settlements"),"incidents":count("forward_test_monitoring_incidents")}

    def _not_found(self,_):return PageModel("Not found","NOT_FOUND",(),(),("Unknown console page.",),self.demo)
    def _table(self,name):return self._one("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)) is not None
    def _rows(self,query,params=()):return tuple(tuple(row) for row in self.connection.execute(query,params).fetchall())
    def _one(self,query,params=()):return self.connection.execute(query,params).fetchone()
    def _latest_json_file(self,path):
        try:return json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):return {}
    @classmethod
    def _json_find(cls,value,key,default=None):
        if isinstance(value,dict):
            if key in value:return value[key]
            for item in value.values():
                found=cls._json_find(item,key,None)
                if found is not None:return found
        elif isinstance(value,list):
            for item in value:
                found=cls._json_find(item,key,None)
                if found is not None:return found
        return default
