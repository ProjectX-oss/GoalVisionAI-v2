"""Manual-only governance orchestration."""

import json
from datetime import datetime,timezone

from app.database import Database
from app.real_match_lab_analysis.fingerprint import canonical_json,fingerprint

from .engine import evaluate_records
from .policy import DEFAULT_POLICY
from .repository import GovernanceConflictError,SQLiteGovernanceRepository


class GovernanceService:
    def __init__(self,database:Database,policy=DEFAULT_POLICY):self.database=database;self.connection=database.connection;self.policy=policy;self.repository=SQLiteGovernanceRepository(database)

    def records(self,cutoff_utc):
        query="""SELECT o.observation_id,o.observation_json,o.created_at_utc,r.result_id,s.settlement_id,s.outcome,s.settled_at_utc,a.request_snapshot,q.snapshot_json,pr.reasoning_id,pr.reasoning_json,pa.audit_id,pa.status FROM forward_test_observations o LEFT JOIN forward_test_results r ON r.observation_id=o.observation_id LEFT JOIN forward_test_settlements s ON s.observation_id=o.observation_id LEFT JOIN real_match_lab_analyses a ON a.analysis_id=o.analysis_id LEFT JOIN forward_test_odds_snapshots q ON q.odds_snapshot_id=o.odds_snapshot_id LEFT JOIN prediction_reasoning_records pr ON pr.observation_id=o.observation_id LEFT JOIN prediction_reasoning_audits pa ON pa.reasoning_id=pr.reasoning_id WHERE o.created_at_utc<=? ORDER BY o.created_at_utc,o.observation_id"""
        values=[]
        for row in self.connection.execute(query,(cutoff_utc,)):
            observation=json.loads(row[1]);request=json.loads(row[7]);odds=json.loads(row[8]);reasoning=json.loads(row[10]) if row[10] else {};selected=observation.get("actionable_market") or observation.get("mathematical_top_market");evaluation=next((item for item in observation.get("market_evaluations",()) if item.get("market")==selected),{});quotes=odds.get("quotes") or ();quote=next((item for item in quotes if item.get("market")==selected),quotes[0] if quotes else {})
            values.append({"observation_id":row[0],"created_at_utc":row[2],"result_id":row[3],"settlement_id":row[4],"outcome":row[5],"settled_at_utc":row[6],"market":selected or "NO_SELECTION","probability":evaluation.get("calibrated_probability"),"raw_probability":evaluation.get("raw_probability"),"odds":evaluation.get("bookmaker_odds") or quote.get("decimal_odds"),"competition":request.get("competition","UNKNOWN"),"bookmaker":odds.get("bookmaker_name","UNKNOWN"),"provider":odds.get("provider_source_id","UNKNOWN"),"model_generation":observation.get("model_artifact_id","UNKNOWN"),"calibration_artifact":observation.get("calibration_id","UNKNOWN"),"feature_completeness":(observation.get("distribution_shift") or {}).get("completeness",1),"required_completeness":1 if observation.get("feature_snapshot_fingerprint") else 0,"lineup_available":"CONFIRMED" in str(evaluation.get("lineup_freshness_status","")),"injury_available":bool(observation.get("injury_status")),"stale_odds":odds.get("freshness_status") not in {"FRESH","AGING"},"published":bool(self.connection.execute("SELECT 1 FROM real_match_lab_deliveries WHERE analysis_id=? LIMIT 1",(observation["analysis_id"],)).fetchone()),"blocked":observation.get("status")=="BLOCKED","reasoning_id":row[9],"reasoning_audit_id":row[11],"reasoning_status":reasoning.get("reasoning_status"),"reasoning_audit":row[12],"explanation_stability":reasoning.get("explanation_stability_status"),"supporting_groups":[item.get("group_id") for item in reasoning.get("supporting_factors",())],"features":_features(reasoning),"integrity_critical":False})
        return tuple(values)

    def evaluate(self,cutoff_utc,*,created_at_utc=None,persist=True,controlled_records=None,evidence_class="FORWARD_TEST_REAL_TIME"):
        cutoff=_time(cutoff_utc).isoformat();created=created_at_utc or cutoff;records=tuple(controlled_records) if controlled_records is not None else self.records(cutoff);request_fp=fingerprint({"cutoff_utc":cutoff,"policy_fingerprint":self.policy.fingerprint,"evidence_class":evidence_class,"source_fingerprints":[fingerprint(row) for row in records]})
        if persist:
            replay=self.repository.by_request(request_fp)
            if replay is not None:return {**replay,"replayed":True}
            prior_request=self.repository.request_at_cutoff(cutoff,evidence_class,self.policy.fingerprint)
            if prior_request is not None and prior_request[0]!=request_fp:raise GovernanceConflictError("GOVERNANCE_EVALUATION_REQUEST_CONFLICT")
        previous=tuple(item for item in self.repository.history() if item["cutoff_utc"]<cutoff);value=evaluate_records(records,cutoff_utc=cutoff,policy=self.policy,previous_evaluations=previous,evidence_class=evidence_class)
        if not persist:return value
        self.repository.ensure_policy(self.policy,created);stored,replayed=self.repository.append(value,request_fp,created);return {**stored,"replayed":replayed}

    def reproduce(self,evaluation_id,checked_at_utc):
        existing=self.repository.load(evaluation_id)
        if existing is None:raise ValueError("Governance evaluation not found.")
        records=self.records(existing["cutoff_utc"]);previous=tuple(item for item in self.repository.history() if item["cutoff_utc"]<existing["cutoff_utc"]);rebuilt=evaluate_records(records,cutoff_utc=existing["cutoff_utc"],policy=self.policy,previous_evaluations=previous,evidence_class=existing["evidence_class"]);matches=rebuilt["evaluation_fingerprint"]==existing["evaluation_fingerprint"];return self.repository.append_reproduction(evaluation_id,"GOVERNANCE_REPRODUCED" if matches else "GOVERNANCE_REPRODUCTION_CONFLICT",rebuilt["evaluation_fingerprint"],checked_at_utc)

    def publication_status(self,observation_id,at_utc):
        latest=self.repository.latest(at_utc)
        if latest is None:return {"status":"PUBLICATION_GOVERNANCE_REQUIRED","blockers":["GOVERNANCE_EVALUATION_MISSING"],"evaluation_id":None}
        age=(_time(at_utc)-_time(latest["cutoff_utc"])).total_seconds()/3600;observation=json.loads(self.connection.execute("SELECT observation_json FROM forward_test_observations WHERE observation_id=?",(observation_id,)).fetchone()[0]);analysis=json.loads(self.connection.execute("SELECT request_snapshot FROM real_match_lab_analyses WHERE analysis_id=?",(observation["analysis_id"],)).fetchone()[0]);odds=json.loads(self.connection.execute("SELECT snapshot_json FROM forward_test_odds_snapshots WHERE odds_snapshot_id=?",(observation["odds_snapshot_id"],)).fetchone()[0]);scopes={(item["scope_type"],item["scope_value"]):item["status"] for item in latest["scope_statuses"]};critical=self.connection.execute("SELECT 1 FROM forward_test_monitoring_incidents i WHERE (i.severity='CORRUPT' OR i.incident_code LIKE '%INTEGRITY%' OR i.incident_code='GOVERNANCE_REPRODUCTION_CONFLICT') AND NOT EXISTS (SELECT 1 FROM forward_test_monitoring_incident_events e WHERE e.incident_id=i.incident_id AND e.event_type='RESOLVED') LIMIT 1").fetchone();checks=[("GOVERNANCE_EVIDENCE_FRESH",0<=age<=self.policy.maximum_evaluation_age_hours),("SYSTEM_GOVERNANCE",latest["decision"]["publication_impact"]!="BLOCK"),("MARKET_GOVERNANCE",not scopes.get(("MARKET",observation.get("actionable_market")),"").endswith("_BLOCKED")),("COMPETITION_GOVERNANCE",not scopes.get(("COMPETITION",analysis.get("competition","UNKNOWN")),"").endswith("_BLOCKED")),("BOOKMAKER_GOVERNANCE",not scopes.get(("BOOKMAKER",odds.get("bookmaker_name","UNKNOWN")),"").endswith("_BLOCKED")),("MODEL_GENERATION_GOVERNANCE",not scopes.get(("MODEL_GENERATION",observation.get("model_artifact_id","UNKNOWN")),"").endswith("_BLOCKED")),("CALIBRATION_GOVERNANCE",not scopes.get(("CALIBRATION_ARTIFACT",observation.get("calibration_id","UNKNOWN")),"").endswith("_BLOCKED")),("INPUT_DRIFT_GOVERNANCE","BLOCKED" not in latest["metrics"]["input_drift_status"]),("EXPLANATION_DRIFT_GOVERNANCE","BLOCKED" not in latest["metrics"]["explanation_drift"]["status"]),("NO_UNRESOLVED_INTEGRITY_CRITICAL_INCIDENT",critical is None)]
        blockers=[name for name,passed in checks if not passed];warning=latest["decision"]["publication_impact"]=="WARNING";return {"status":"PUBLICATION_GOVERNANCE_BLOCKED" if blockers else "PUBLICATION_GOVERNANCE_WARNING" if warning else "PUBLICATION_GOVERNANCE_PASSED","blockers":blockers,"evaluation_id":latest["evaluation_id"],"evaluation_fingerprint":latest["evaluation_fingerprint"],"checks":[{"name":name,"passed":passed} for name,passed in checks]}

    def snapshot_observation(self,observation_id,created_at_utc):
        status=self.publication_status(observation_id,created_at_utc)
        if not status.get("evaluation_id"):raise ValueError("Current governance evaluation is required.")
        evaluation=self.repository.load(status["evaluation_id"]);observation=json.loads(self.connection.execute("SELECT observation_json FROM forward_test_observations WHERE observation_id=?",(observation_id,)).fetchone()[0]);analysis=json.loads(self.connection.execute("SELECT request_snapshot FROM real_match_lab_analyses WHERE analysis_id=?",(observation["analysis_id"],)).fetchone()[0]);odds=json.loads(self.connection.execute("SELECT snapshot_json FROM forward_test_odds_snapshots WHERE odds_snapshot_id=?",(observation["odds_snapshot_id"],)).fetchone()[0]);scopes={(item["scope_type"],item["scope_value"]):item["status"] for item in evaluation["scope_statuses"]}
        material={"schema_version":"goalvision-observation-governance-snapshot-v1","observation_id":observation_id,"evaluation_id":evaluation["evaluation_id"],"evaluation_fingerprint":evaluation["evaluation_fingerprint"],"model_generation_status":scopes.get(("MODEL_GENERATION",observation.get("model_artifact_id","UNKNOWN")),"GENERATION_SAMPLE_INSUFFICIENT"),"market_status":scopes.get(("MARKET",observation.get("actionable_market")),"MARKET_SAMPLE_INSUFFICIENT"),"competition_status":scopes.get(("COMPETITION",analysis.get("competition","UNKNOWN")),"COMPETITION_SAMPLE_INSUFFICIENT"),"bookmaker_status":scopes.get(("BOOKMAKER",odds.get("bookmaker_name","UNKNOWN")),"BOOKMAKER_SAMPLE_INSUFFICIENT"),"calibration_status":scopes.get(("CALIBRATION_ARTIFACT",observation.get("calibration_id","UNKNOWN")),"CALIBRATION_ARTIFACT_SAMPLE_INSUFFICIENT"),"input_drift_status":evaluation["metrics"]["input_drift_status"],"explanation_drift_status":evaluation["metrics"]["explanation_drift"]["status"],"publication_decision":status["status"],"created_at_utc":created_at_utc};fp=fingerprint(material);material.update({"snapshot_id":"observation-governance-"+fp,"snapshot_fingerprint":fp});stored,replayed=self.repository.append_observation_snapshot(material);return {**stored,"replayed":replayed}

    def record_incidents(self,evaluation_id):
        evaluation=self.repository.load(evaluation_id)
        if evaluation is None:raise ValueError("Governance evaluation not found.")
        codes=[]
        mapping=(("predictive_status","PREDICTIVE_PERFORMANCE_DEGRADED"),("calibration_status","CALIBRATION_DRIFT_BLOCKED"),("input_drift_status","INPUT_DRIFT_BLOCKED"))
        for key,code in mapping:
            if "BLOCKED" in str(evaluation["metrics"].get(key)):codes.append(code)
        for key,code in (("data_completeness","DATA_COMPLETENESS_BLOCKED"),("odds_drift","ODDS_DRIFT_BLOCKED"),("explanation_drift","EXPLANATION_DRIFT_BLOCKED")):
            if "BLOCKED" in str(evaluation["metrics"][key]["status"]):codes.append(code)
        for scope in evaluation["scope_statuses"]:
            if scope["status"].endswith("_BLOCKED"):codes.append(f'{scope["scope_type"]}_GOVERNANCE_BLOCKED')
        for recommendation in evaluation["recommendations"]:
            if "RECOMMENDED" in recommendation["outcome"] or "REVIEW_REQUIRED" in recommendation["outcome"]:codes.append(recommendation["outcome"])
        created=[]
        for code in sorted(set(codes)):
            material={"incident_code":code,"severity":"BLOCKING","affected_identifier":evaluation_id,"detected_at_utc":evaluation["cutoff_utc"],"provenance":"FORWARD_TEST_GOVERNANCE","detail":"Manual governance review required; acknowledgement cannot clear mathematical status."};fp=fingerprint(material);material.update({"incident_id":"forward-test-incident-"+fp,"incident_fingerprint":fp});row=self.connection.execute("SELECT incident_fingerprint FROM forward_test_monitoring_incidents WHERE incident_fingerprint=?",(fp,)).fetchone()
            if not row:
                with self.connection:self.connection.execute("INSERT INTO forward_test_monitoring_incidents VALUES (?,?,?,?,?,?,?)",(material["incident_id"],code,"BLOCKING",evaluation_id,evaluation["cutoff_utc"],fp,canonical_json(material)))
            created.append(material)
        return created


def _features(reasoning):
    result={}
    for attribution in reasoning.get("class_attributions",()):
        for item in attribution.get("contributions",()):
            if item.get("raw_value") is not None:result.setdefault(item["feature_name"],item["raw_value"])
    return result


def _time(value):
    parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"));return parsed.astimezone(timezone.utc)
