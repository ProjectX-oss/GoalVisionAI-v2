"""Deterministic isolated fictional console demonstration evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from app.database import Database, MigrationManager
from app.forward_test_monitoring import MonitoringService, SQLiteMonitoringRepository
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint


DEMO_VERSION="goalvision-lab-operator-console-demo-v1"
DEMO_TIME="2026-08-02T09:00:00+00:00"
MARKETS=("HOME_WIN","DRAW","AWAY_WIN","OVER_1_5","UNDER_1_5","OVER_2_5","UNDER_2_5","OVER_3_5","UNDER_3_5","BTTS_YES","BTTS_NO")


def build_demo(database:Database) -> dict:
    MigrationManager(database.connection).migrate(); connection=database.connection
    existing=connection.execute("SELECT manifest_json FROM lab_operator_console_demo_manifests WHERE demo_version=?",(DEMO_VERSION,)).fetchone()
    if existing:return json.loads(existing[0])
    for index,outcome in enumerate(("WON","LOST","VOID","NO_SELECTION","CALIBRATION_BLOCKED","SHIFT_BLOCKED"),1):_seed_chain(connection,index,outcome)
    _seed_runs(connection); _seed_incidents(connection)
    monitor=MonitoringService(SQLiteMonitoringRepository(database,migrate=False)); cutoff=datetime(2026,8,2,12,tzinfo=timezone.utc); weekly=monitor.report("WEEKLY",cutoff); cumulative=monitor.report("CUMULATIVE",cutoff)
    material={"schema_version":DEMO_VERSION,"evidence_class":"CONTROLLED_FICTIONAL_DEMO_DATA","database_identity":"ISOLATED_DEMO_DATABASE","fixture_count":6,"observation_count":6,"result_count":3,"settlement_count":3,"weekly_report_id":weekly["report_id"],"cumulative_report_id":cumulative["report_id"],"incident_count":2,"unresolved_count":len(monitor.unresolved(cutoff)),"network_call_count":0,"telegram_call_count":0,"delivery_record_count":0,"official_mutation_count":0,"bankroll_mutation_count":0,"statistics_mutation_count":0,"scheduling_enabled":False,"created_at_utc":DEMO_TIME}; fp=fingerprint(material); material.update({"manifest_id":"lab-console-demo-"+fp,"manifest_fingerprint":fp})
    with connection:connection.execute("INSERT INTO lab_operator_console_demo_manifests VALUES (?,?,?,?,?,?,?,?,?,?,?)",(material["manifest_id"],DEMO_VERSION,material["database_identity"],6,6,0,0,0,fp,canonical_json(material),DEMO_TIME))
    return material


def _seed_chain(c,index,outcome):
    suffix=f"demo-{index}"; fixture=f"fictional-fixture-{index}"; analysis=f"fictional-analysis-{index}"; odds_id=f"fictional-odds-{index}"; observation_id=f"fictional-observation-{index}"; kickoff=f"2026-08-01T{10+index:02d}:00:00+00:00"; created=f"2026-08-01T08:{index:02d}:00+00:00"
    evaluations=[]; quotes=[]
    for rank,market in enumerate(MARKETS,1):
        probability=Decimal("0.62") if market=="HOME_WIN" else Decimal("0.38") if market in {"DRAW","AWAY_WIN"} else Decimal("0.55"); odds=Decimal("2.10") if market=="HOME_WIN" else Decimal("1.90")
        evaluations.append({"market":market,"raw_probability":str(probability-Decimal("0.02")),"calibrated_probability":str(probability),"bookmaker_odds":str(odds),"fair_odds":str((Decimal(1)/probability).quantize(Decimal("0.01"))),"implied_probability":str((Decimal(1)/odds).quantize(Decimal("0.0001"))),"expected_value":str((probability*odds-1).quantize(Decimal("0.001"))),"mathematical_rank":rank,"actionable":market=="HOME_WIN" and outcome not in {"NO_SELECTION","CALIBRATION_BLOCKED","SHIFT_BLOCKED"},"selected":market=="HOME_WIN" and outcome not in {"NO_SELECTION","CALIBRATION_BLOCKED","SHIFT_BLOCKED"},"calibration_quality_outcome":"BLOCKED" if outcome=="CALIBRATION_BLOCKED" else "ACCEPTABLE","distribution_shift_status":"BLOCKING" if outcome=="SHIFT_BLOCKED" else "ACCEPTABLE","rejection_reasons":[]})
        quote={"quote_id":f"quote-{suffix}-{rank}","market":market,"selection":market,"decimal_odds":str(odds),"provider_origin_timestamp_utc":None};quote["quote_fingerprint"]=fingerprint(quote);quotes.append(quote)
    request={"schema_version":"goalvision-real-match-lab-input-v1","match_id":fixture,"competition":"Fictional Demo League","season":"2026","home_team":f"Demo Home {index}","away_team":f"Demo Away {index}","kickoff_utc":kickoff,"match_snapshot":{"controlled_fictional":True,"venue":"Demo Ground"}}
    evidence={"feature_fingerprint":fingerprint((suffix,"features")),"model_input_fingerprint":fingerprint((suffix,"input")),"model_artifact_id":"controlled-demo-model","model_artifact_fingerprint":fingerprint("controlled-demo-model"),"calibration_set_id":"controlled-demo-calibration","calibration_fingerprint":fingerprint("controlled-demo-calibration"),"evaluations":evaluations,"calibration_quality_report":{"status":"BLOCKED" if outcome=="CALIBRATION_BLOCKED" else "ACCEPTABLE","lab_outcome":"CALIBRATION_QUALITY_BLOCKED" if outcome=="CALIBRATION_BLOCKED" else "CALIBRATION_QUALITY_ACCEPTABLE","distribution_shift":{"status":"DISTRIBUTION_SHIFT_BLOCKING" if outcome=="SHIFT_BLOCKED" else "DISTRIBUTION_SHIFT_ACCEPTABLE"}},"mathematically_top_ranked_market":"HOME_WIN"}
    result_snapshot={"evidence":evidence,"rejection_reasons":[outcome] if outcome in {"NO_SELECTION","CALIBRATION_BLOCKED","SHIFT_BLOCKED"} else []}; selected=None if outcome in {"NO_SELECTION","CALIBRATION_BLOCKED","SHIFT_BLOCKED"} else "HOME_WIN"; message=f"CONTROLLED FICTIONAL DEMO DATA\nDemo Home {index} vs Demo Away {index}\nMarket: {selected or 'No actionable selection'}\nPREVIEW ONLY — NOTHING HAS BEEN SENT"; message_fp=fingerprint(message)
    analysis_fp=fingerprint(result_snapshot);request_fp=fingerprint(request)
    c.execute("INSERT INTO real_match_lab_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(analysis,f"demo-request-{index}",request_fp,analysis_fp,"NO_SELECTION" if selected is None else "COMPLETED",fixture,kickoff,"LAB","OFFICIAL_GLOBAL","-1003510920417","@GoalVision_AI_Lab_Bot",selected,message,message_fp,canonical_json(request),canonical_json(result_snapshot),created))
    odds={"snapshot_id":odds_id,"schema_version":"goalvision-current-odds-snapshot-v1","canonical_fixture_id":fixture,"kickoff_utc":kickoff,"fixture_status":"SCHEDULED","provider_source_id":"CONTROLLED_DEMO","provider_type":"OPERATOR_SUPPLIED_CURRENT_ODDS","bookmaker_name":"FICTIONAL_BOOK","source_selected_at_utc":"2026-08-01T07:50:00+00:00","captured_at_utc":"2026-08-01T07:55:00+00:00","sealed_at_utc":"2026-08-01T07:56:00+00:00","freshness_status":"FRESH","quotes":quotes};odds_fp=fingerprint(odds);odds["snapshot_fingerprint"]=odds_fp
    c.execute("INSERT INTO forward_test_odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(odds_id,fixture,kickoff,"CONTROLLED_DEMO","OPERATOR_SUPPLIED_CURRENT_ODDS","FICTIONAL_BOOK",odds["source_selected_at_utc"],odds["captured_at_utc"],odds["sealed_at_utc"],"FRESH",odds_fp,canonical_json(odds)))
    status="NO_SELECTION" if outcome=="NO_SELECTION" else "BLOCKED" if outcome in {"CALIBRATION_BLOCKED","SHIFT_BLOCKED"} else "ANALYSIS_COMPLETED"; actionable=selected is not None
    observation={"observation_id":observation_id,"schema_version":"goalvision-forward-test-observation-v1","evidence_tier":"FORWARD_TEST_REAL_TIME","request_id":f"demo-forward-{index}","request_fingerprint":fingerprint((suffix,"observation-request")),"analysis_id":analysis,"analysis_result_fingerprint":analysis_fp,"odds_snapshot_id":odds_id,"odds_snapshot_fingerprint":odds_fp,"canonical_fixture_id":fixture,"fixture_snapshot_fingerprint":fingerprint((fixture,"snapshot")),"feature_snapshot_fingerprint":evidence["feature_fingerprint"],"model_input_fingerprint":evidence["model_input_fingerprint"],"model_artifact_id":evidence["model_artifact_id"],"model_artifact_fingerprint":evidence["model_artifact_fingerprint"],"calibration_id":evidence["calibration_set_id"],"calibration_fingerprint":evidence["calibration_fingerprint"],"calibration_quality":evidence["calibration_quality_report"],"distribution_shift":evidence["calibration_quality_report"]["distribution_shift"],"market_evaluations":evaluations,"mathematical_top_market":"HOME_WIN","actionable_market":selected,"status":status,"analysis_completed":True,"actionable":actionable,"forward_test_recorded":True,"preview_available":True,"lab_send_eligible":False,"official_eligible":False,"message_preview":message,"message_fingerprint":message_fp,"rejection_reasons":result_snapshot["rejection_reasons"],"inference_at_utc":created,"created_at_utc":created};obs_fp=fingerprint(observation);observation["observation_fingerprint"]=obs_fp
    c.execute("INSERT INTO forward_test_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(observation_id,observation["request_id"],observation["request_fingerprint"],analysis,odds_id,fixture,"FORWARD_TEST_REAL_TIME",status,int(actionable),1,0,0,obs_fp,canonical_json(observation),created))
    review_status="LAB_PUBLICATION_REVIEW_PASSED" if index==1 else "LAB_PUBLICATION_REVIEW_BLOCKED";review={"review_id":f"demo-review-{index}","observation_id":observation_id,"review_status":review_status,"message_fingerprint":message_fp,"reviewed_at_utc":created};review_fp=fingerprint(review);review["review_fingerprint"]=review_fp;c.execute("INSERT INTO forward_test_publication_reviews VALUES (?,?,?,?,?,?,?)",(review["review_id"],observation_id,review_status,message_fp,created,review_fp,canonical_json(review)))
    if outcome in {"WON","LOST","VOID"}:
        result_id=f"demo-result-{index}";home,away=(2,1) if outcome=="WON" else (0,1) if outcome=="LOST" else (1,1);result={"result_id":result_id,"schema_version":"goalvision-forward-test-result-v1","observation_id":observation_id,"canonical_fixture_id":fixture,"final_home_score":home,"final_away_score":away,"final_status":"FT","result_source":"CONTROLLED_DEMO","result_retrieval_timestamp_utc":f"2026-08-01T{17+index:02d}:00:00+00:00","provenance":"CONTROLLED FICTIONAL DEMO DATA"};result_fp=fingerprint(result);result["result_fingerprint"]=result_fp;c.execute("INSERT INTO forward_test_results VALUES (?,?,?,?,?,?,?,?,?)",(result_id,observation_id,fixture,home,away,"FT",result["result_retrieval_timestamp_utc"],result_fp,canonical_json(result)))
        settlement={"settlement_id":f"demo-settlement-{index}","observation_id":observation_id,"result_id":result_id,"market":"HOME_WIN","outcome":outcome,"quoted_odds":"2.10","hypothetical_flat_stake":"1","hypothetical_net_return":"1.10" if outcome=="WON" else "-1" if outcome=="LOST" else "0","reason_code":"CONTROLLED_DEMO","settled_at_utc":f"2026-08-01T{17+index:02d}:01:00+00:00"};settlement_fp=fingerprint(settlement);settlement["settlement_fingerprint"]=settlement_fp;c.execute("INSERT INTO forward_test_settlements VALUES (?,?,?,?,?,?,?,?)",(settlement["settlement_id"],observation_id,result_id,outcome,"HOME_WIN",settlement_fp,canonical_json(settlement),settlement["settled_at_utc"]))
    c.commit()


def _seed_runs(c):
    raw={"run_id":"demo-discovery-free-blocked","request_fingerprint":fingerprint("demo-free"),"mode":"CONTROLLED_REHEARSAL","execution_state":"STARTED","created_at_utc":DEMO_TIME};fp=fingerprint(raw);raw["run_fingerprint"]=fp;c.execute("INSERT INTO first_lab_run_executions VALUES (?,?,?,?,?,?,?)",(raw["run_id"],raw["request_fingerprint"],raw["mode"],raw["execution_state"],DEMO_TIME,fp,canonical_json(raw)))
    for order,(name,status) in enumerate((("PROVIDER_READINESS","BLOCKED"),("CANDIDATE_REVIEW","COMPLETED"),("TELEGRAM_BOUNDARY","PASSED"))):
        event={"run_id":raw["run_id"],"stage_order":order,"stage_name":name,"stage_status":status,"occurred_at_utc":DEMO_TIME,"detail":"CONTROLLED FICTIONAL DEMO DATA"}
        if name=="CANDIDATE_REVIEW":event.update({"candidate_id":"demo-candidate-1","fixture_id":"fictional-fixture-1","competition":"Fictional Demo League","kickoff_utc":"2026-08-01T11:00:00+00:00","status":"ELIGIBLE_BEFORE_INFERENCE","reason_code":"CONTROLLED_DEMO"})
        efp=fingerprint(event);c.execute("INSERT INTO first_lab_run_stage_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",(f"demo-stage-{order}",raw["run_id"],order,name,status,"CONTROLLED_DEMO",None,None,DEMO_TIME,efp,canonical_json(event)))
    c.commit()


def _seed_incidents(c):
    for index,(code,severity,target) in enumerate((("CONTROLLED_RESULT_CONFLICT","CORRUPT","fictional-observation-1"),("CONTROLLED_SETTLEMENT_CONFLICT","BLOCKING","fictional-observation-3")),1):
        raw={"incident_code":code,"severity":severity,"affected_identifier":target,"detected_at_utc":DEMO_TIME,"detail":"CONTROLLED FICTIONAL DEMO DATA"};fp=fingerprint(raw);raw.update({"incident_id":f"demo-incident-{index}","incident_fingerprint":fp});c.execute("INSERT INTO forward_test_monitoring_incidents VALUES (?,?,?,?,?,?,?)",(raw["incident_id"],code,severity,target,DEMO_TIME,fp,canonical_json(raw)))
    c.commit()
