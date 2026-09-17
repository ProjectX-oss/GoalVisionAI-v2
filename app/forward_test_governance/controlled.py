"""Controlled fictional governance rehearsal."""

from datetime import datetime,timedelta,timezone
from decimal import Decimal

from app.lab_operator_console.demo import build_demo

from app.real_match_lab_analysis.fingerprint import fingerprint

from .reports import build_report,markdown,telegram_preview
from .service import GovernanceService


EVIDENCE_CLASS="CONTROLLED_FICTIONAL_FORWARD_TEST_GOVERNANCE_REHEARSAL"
CONTROLLED_SCENARIOS=("NO_EVIDENCE","INSUFFICIENT_SAMPLE","WARM_UP","CLEAR_GOVERNANCE","WARNING_GOVERNANCE","BLOCKED_GOVERNANCE","PREDICTIVE_DEGRADATION","CALIBRATION_OVERCONFIDENCE","CALIBRATION_UNDERCONFIDENCE","RISING_ECE","EXTREME_PROBABILITY_FAILURE","FEATURE_DRIFT","MISSINGNESS_DRIFT","LINEUP_AVAILABILITY_DETERIORATION","STALE_ODDS_INCREASE","MARKET_CONCENTRATION","BOOKMAKER_COVERAGE_LOSS","ONE_MARKET_BLOCKED","MULTIPLE_MARKETS_BLOCKED","ONE_COMPETITION_BLOCKED","ONE_BOOKMAKER_BLOCKED","EXPLANATION_FRAGILITY_INCREASE","REASONING_AUDIT_DETERIORATION","CURRENT_GENERATION_IMPROVED","CURRENT_GENERATION_DEGRADED","MIXED_COMPARISON","RECALIBRATION_RECOMMENDATION","RETRAINING_RECOMMENDATION","ROLLBACK_REVIEW_RECOMMENDATION","HYSTERESIS_WARNING","HYSTERESIS_BLOCK","RECOVERY_AFTER_CLEAR_EVALUATIONS","STALE_GOVERNANCE_EVIDENCE","PUBLICATION_GOVERNANCE_PASS","PUBLICATION_GOVERNANCE_WARNING","PUBLICATION_GOVERNANCE_BLOCK","REPRODUCTION_PASS","REPRODUCTION_CONFLICT")


def controlled_records(count=60):
    start=datetime(2026,5,1,tzinfo=timezone.utc);markets=("HOME_WIN","DRAW","AWAY_WIN","OVER_2_5","UNDER_2_5","BTTS_YES","BTTS_NO");values=[]
    for index in range(count):
        recent=index>=40;probability=Decimal("0.88") if recent else Decimal("0.58");outcome="LOST" if recent and index%3 else "WON" if index%2==0 else "LOST";created=start+timedelta(days=index);market=markets[index%len(markets)]
        values.append({"observation_id":f"controlled-governance-observation-{index:03d}","created_at_utc":created.isoformat(),"result_id":f"controlled-result-{index:03d}","settlement_id":f"controlled-settlement-{index:03d}","settled_at_utc":(created+timedelta(hours=3)).isoformat(),"outcome":outcome,"market":market,"probability":str(probability),"raw_probability":str(probability-Decimal("0.03")),"odds":"2.10","competition":("Fictional Premier","Fictional Baltic")[index%2],"bookmaker":("FICTIONAL_BOOK_A","FICTIONAL_BOOK_B")[index%2],"provider":"CONTROLLED_PROVIDER","model_generation":"controlled-generation-v2" if index>=30 else "controlled-generation-v1","calibration_artifact":"controlled-calibration-v2" if index>=30 else "controlled-calibration-v1","feature_completeness":"0.60" if recent else "1","required_completeness":"1","lineup_available":not recent,"injury_available":not recent,"stale_odds":recent and index%2==0,"published":False,"blocked":recent and index%4==0,"reasoning_id":f"controlled-reasoning-{index:03d}","reasoning_audit_id":f"controlled-audit-{index:03d}","reasoning_status":"REASONING_CREATED","reasoning_audit":"REASONING_AUDIT_BLOCKED" if recent and index%4==0 else "REASONING_AUDIT_PASSED","explanation_stability":"EXPLANATION_FRAGILE" if recent else "EXPLANATION_STABLE","supporting_groups":["HOME_RECENT_FORM" if not recent else "DATA_AVAILABILITY"],"features":{"home_recent_points_per_match":str(Decimal("3.5") if recent else Decimal("1.5")),"snapshot_completeness_score":str(Decimal("0.6") if recent else Decimal("1"))},"integrity_critical":False})
    return tuple(values)


def run_controlled_rehearsal(database):
    build_demo(database);service=GovernanceService(database);records=controlled_records();first=service.evaluate("2026-07-01T00:00:00+00:00",created_at_utc="2026-07-01T00:00:00+00:00",controlled_records=records,evidence_class=EVIDENCE_CLASS);second=service.evaluate("2026-07-02T00:00:00+00:00",created_at_utc="2026-07-02T00:00:00+00:00",controlled_records=records,evidence_class=EVIDENCE_CLASS);reproduction=_controlled_reproduction(service,second,records);report=build_report(second,"CONTROLLED_CUMULATIVE")
    incidents=service.record_incidents(second["evaluation_id"])
    event=service.repository.append_event(second["evaluation_id"],"WARNING_ACKNOWLEDGED","CONTROLLED_OPERATOR","Acknowledged; mathematical status unchanged.","2026-07-02T00:01:00+00:00")
    return {"evidence_class":EVIDENCE_CLASS,"model_generations":["controlled-generation-v1","controlled-generation-v2"],"calibration_artifacts":["controlled-calibration-v1","controlled-calibration-v2"],"observations":len(records),"markets":sorted({row["market"] for row in records}),"competitions":sorted({row["competition"] for row in records}),"bookmakers":sorted({row["bookmaker"] for row in records}),"first_decision":first["decision"]["status"],"decision":second["decision"]["status"],"predictive_status":second["metrics"]["predictive_status"],"calibration_status":second["metrics"]["calibration_status"],"input_drift_status":second["metrics"]["input_drift_status"],"completeness_status":second["metrics"]["data_completeness"]["status"],"odds_status":second["metrics"]["odds_drift"]["status"],"explanation_status":second["metrics"]["explanation_drift"]["status"],"recommendations":second["recommendations"],"incidents":[item["incident_id"] for item in incidents],"evaluation_id":second["evaluation_id"],"evaluation_fingerprint":second["evaluation_fingerprint"],"reproduction":reproduction,"acknowledgement_event":event["event_fingerprint"],"report_fingerprint":report["report_fingerprint"],"markdown_fingerprint":fingerprint(markdown(report)),"telegram_preview_fingerprint":fingerprint(telegram_preview(report)),"network_calls":0,"telegram_calls":0,"deliveries":0,"official_mutations":0,"bankroll_mutations":0,"statistics_mutations":0,"production_activation_mutations":0,"rollback_executions":0,"retraining_executions":0,"recalibration_executions":0,"scheduling_changes":0}


def _controlled_reproduction(service,evaluation,records):
    from .engine import evaluate_records
    prior=[item for item in service.repository.history() if item["cutoff_utc"]<evaluation["cutoff_utc"]];rebuilt=evaluate_records(records,cutoff_utc=evaluation["cutoff_utc"],policy=service.policy,previous_evaluations=prior,evidence_class=EVIDENCE_CLASS);matches=rebuilt["evaluation_fingerprint"]==evaluation["evaluation_fingerprint"];return {"status":"GOVERNANCE_REPRODUCED" if matches else "GOVERNANCE_REPRODUCTION_CONFLICT","matches":matches,"actual_fingerprint":rebuilt["evaluation_fingerprint"]}
