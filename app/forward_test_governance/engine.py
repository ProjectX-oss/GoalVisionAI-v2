"""Deterministic forward-test governance evaluation engine."""

from __future__ import annotations

import json
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.real_match_lab_analysis.fingerprint import fingerprint

from .metrics import calibration,d,distribution,predictive,psi
from .policy import DEFAULT_POLICY,GovernancePolicy


class GovernanceError(RuntimeError):pass


CANONICAL_MARKETS=("HOME_WIN","DRAW","AWAY_WIN","OVER_1_5","UNDER_1_5","OVER_2_5","UNDER_2_5","OVER_3_5","UNDER_3_5","BTTS_YES","BTTS_NO")


def _time(value):
    parsed=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.tzinfo is None:raise GovernanceError("GOVERNANCE_TIMESTAMP_OFFSET_REQUIRED")
    return parsed.astimezone(timezone.utc)


def maturity(sample:int,policy:GovernancePolicy)->str:
    if sample==0:return "NO_EVIDENCE"
    if sample<policy.warm_up_sample:return "GOVERNANCE_SAMPLE_INSUFFICIENT"
    if sample<policy.minimum_recent_window_sample:return "WARM_UP"
    if sample<policy.minimum_total_settled_sample:return "MONITORING"
    if sample<policy.minimum_total_settled_sample*2:return "REVIEWABLE"
    return "POLICY_MINIMUM_MET"


def _status(metric,warning,blocked,prefix,sample,minimum):
    if sample<minimum:return f"{prefix}_SAMPLE_INSUFFICIENT"
    if metric is None:return f"{prefix}_UNDEFINED"
    value=abs(d(metric))
    if value>=blocked:return f"{prefix}_BLOCKED"
    if value>=warning:return f"{prefix}_WARNING"
    return f"{prefix}_CLEAR"


def _windows(rows,cutoff,policy):
    settled=[row for row in rows if row.get("settlement_id")];settled.sort(key=lambda row:(row["settled_at_utc"],row["observation_id"]));result=[]
    def add(kind,values,scope_type="SYSTEM",scope_value="ALL"):
        ids=tuple(row["observation_id"] for row in values);settlements=tuple(row["settlement_id"] for row in values if row.get("settlement_id"));material={"kind":kind,"scope_type":scope_type,"scope_value":scope_value,"cutoff_utc":cutoff.isoformat(),"observation_ids":ids,"settlement_ids":settlements,"model_generations":sorted({row["model_generation"] for row in values}),"calibration_artifacts":sorted({row["calibration_artifact"] for row in values}),"evidence_tier":"FORWARD_TEST_REAL_TIME","sample_size":len(settlements),"sample_maturity":maturity(len(settlements),policy)};material["window_fingerprint"]=fingerprint(material);result.append(material)
    add("LIFETIME",settled)
    for count in policy.rolling_observation_windows:add(f"ROLLING_{count}_SETTLED",settled[-count:])
    for days in policy.rolling_day_windows:add(f"ROLLING_{days}_DAYS",[row for row in settled if _time(row["settled_at_utc"])>=cutoff-timedelta(days=days)])
    try:local=cutoff.astimezone(ZoneInfo(policy.timezone))
    except Exception:
        march_end=max(day for day in range(25,32) if date(cutoff.year,3,day).weekday()==6);october_end=max(day for day in range(25,32) if date(cutoff.year,10,day).weekday()==6);summer=(cutoff.month,cutoff.day)>=(3,march_end) and (cutoff.month,cutoff.day)<(10,october_end);local=cutoff.astimezone(timezone(timedelta(hours=3 if summer else 2)))
    week_start=(local-timedelta(days=local.weekday(),hours=local.hour,minutes=local.minute,seconds=local.second,microseconds=local.microsecond)).astimezone(timezone.utc);previous=week_start-timedelta(days=7)
    add("CURRENT_CALENDAR_WEEK",[row for row in settled if _time(row["settled_at_utc"])>=week_start]);add("PREVIOUS_CALENDAR_WEEK",[row for row in settled if previous<=_time(row["settled_at_utc"])<week_start])
    for scope,key in (("MODEL_GENERATION","model_generation"),("CALIBRATION_ARTIFACT","calibration_artifact"),("MARKET","market"),("COMPETITION","competition"),("BOOKMAKER","bookmaker")):
        grouped=defaultdict(list)
        for row in settled:grouped[row[key]].append(row)
        for value in sorted(grouped):add(f"BY_{scope}",grouped[value],scope,value)
    return result


def _scope(rows,scope_type,scope_value,policy,cutoff_utc):
    settled=[row for row in rows if row.get("outcome") in {"WON","LOST"}];pred=predictive(settled);cal=calibration(settled);sample=pred["sample_size"];minimum=policy.minimum_scope_sample
    performance=_status(pred["brier_score"],policy.brier_warning,policy.brier_block,"PREDICTIVE_PERFORMANCE",sample,minimum);cal_status=_status(cal["ece"],policy.ece_warning,policy.ece_block,"CALIBRATION_DRIFT",sample,minimum)
    blocked="BLOCKED" in performance or "BLOCKED" in cal_status;warning="WARNING" in performance or "WARNING" in cal_status
    prefix={"MARKET":"MARKET","COMPETITION":"COMPETITION","BOOKMAKER":"BOOKMAKER","CALIBRATION_ARTIFACT":"CALIBRATION_ARTIFACT"}.get(scope_type,"GENERATION")
    status=f"{prefix}_SAMPLE_INSUFFICIENT" if sample<minimum else f"{prefix}_BLOCKED" if blocked else f"{prefix}_WARNING" if warning else f"{prefix}_CLEAR"
    returns=[];balance=peak=drawdown=Decimal(0)
    for row in rows:
        if row.get("outcome")=="WON" and row.get("odds") is not None:value=d(row["odds"])-1
        elif row.get("outcome")=="LOST":value=Decimal(-1)
        else:value=Decimal(0)
        if row.get("outcome") in {"WON","LOST","VOID"}:returns.append(value);balance+=value;peak=max(peak,balance);drawdown=max(drawdown,peak-balance)
    metrics={"predictive":pred,"calibration":cal,"observations":len(rows),"actionable_selections":sum(row.get("market") not in {None,"NO_SELECTION"} for row in rows),"settled":len(settled),"wins":sum(row.get("outcome")=="WON" for row in rows),"losses":sum(row.get("outcome")=="LOST" for row in rows),"voids":sum(row.get("outcome")=="VOID" for row in rows),"average_odds":distribution(row.get("odds") for row in rows)["mean"],"hypothetical_roi":str(sum(returns,Decimal(0))/Decimal(len(returns))) if returns else None,"maximum_drawdown":str(drawdown),"publication_count":sum(bool(row.get("published")) for row in rows),"publication_rate":str(Decimal(sum(bool(row.get("published")) for row in rows))/Decimal(len(rows))) if rows else None,"blocker_rate":str(Decimal(sum(bool(row.get("blocked")) for row in rows))/Decimal(len(rows))) if rows else None}
    material={"scope_type":scope_type,"scope_value":scope_value,"cutoff_utc":cutoff_utc,"status":status,"primary_reason":performance if "CLEAR" not in performance else cal_status,"metrics":metrics};material["scope_fingerprint"]=fingerprint(material);return material


def evaluate_records(rows,*,cutoff_utc,policy:GovernancePolicy=DEFAULT_POLICY,previous_evaluations=(),evidence_class="FORWARD_TEST_REAL_TIME"):
    cutoff=_time(cutoff_utc);rows=tuple(sorted((dict(row) for row in rows if _time(row["created_at_utc"])<=cutoff),key=lambda row:(row["created_at_utc"],row["observation_id"])))
    windows=_windows(rows,cutoff,policy);settled=[row for row in rows if row.get("outcome") in {"WON","LOST"}];sample=len(settled);sample_maturity=maturity(sample,policy);pred=predictive(settled);cal=calibration(settled)
    predictive_status=_status(pred["brier_score"],policy.brier_warning,policy.brier_block,"PREDICTIVE_PERFORMANCE",sample,policy.minimum_recent_window_sample)
    calibration_status=_status(cal["ece"],policy.ece_warning,policy.ece_block,"CALIBRATION_DRIFT",sample,policy.minimum_recent_window_sample)
    recent=settled[-policy.minimum_recent_window_sample:];baseline=settled[:-policy.minimum_recent_window_sample] or settled
    feature_names=sorted({name for row in rows for name in (row.get("features") or {})});feature_metrics=[]
    for name in feature_names:
        current=[row.get("features",{}).get(name) for row in recent];base=[row.get("features",{}).get(name) for row in baseline];shift=psi(current,base);missing=Decimal(sum(value is None for value in current))/Decimal(len(current)) if current else None;status="FEATURE_DRIFT_SAMPLE_INSUFFICIENT" if len(recent)<policy.minimum_recent_window_sample else "FEATURE_DRIFT_BLOCKED" if (shift is not None and shift>=policy.psi_block) or (missing is not None and missing>=policy.missingness_block) else "FEATURE_DRIFT_WARNING" if (shift is not None and shift>=policy.psi_warning) or (missing is not None and missing>=policy.missingness_warning) else "FEATURE_DRIFT_CLEAR";feature_metrics.append({"feature":name,"status":status,"psi":str(shift) if shift is not None else None,"missingness_rate":str(missing) if missing is not None else None,"current":distribution(current),"baseline":distribution(base)})
    input_status="INPUT_DRIFT_SAMPLE_INSUFFICIENT" if sample<policy.minimum_recent_window_sample else "INPUT_DRIFT_BLOCKED" if any(x["status"]=="FEATURE_DRIFT_BLOCKED" for x in feature_metrics) else "INPUT_DRIFT_WARNING" if any(x["status"]=="FEATURE_DRIFT_WARNING" for x in feature_metrics) else "INPUT_DRIFT_CLEAR"
    completeness_values=[d(row.get("feature_completeness",1)) for row in rows];required_missing_rate=Decimal(sum(d(row.get("required_completeness",1))<1 for row in rows))/Decimal(len(rows)) if rows else None;optional_missing_rate=Decimal(sum(value<1 for value in completeness_values))/Decimal(len(rows)) if rows else None
    completeness_status="DATA_COMPLETENESS_SAMPLE_INSUFFICIENT" if sample<policy.minimum_recent_window_sample else "DATA_COMPLETENESS_BLOCKED" if required_missing_rate and required_missing_rate>=policy.missingness_block else "DATA_COMPLETENESS_WARNING" if optional_missing_rate and optional_missing_rate>=policy.missingness_warning else "DATA_COMPLETENESS_CLEAR"
    stale_rate=Decimal(sum(bool(row.get("stale_odds")) for row in rows))/Decimal(len(rows)) if rows else None;market_counts=Counter(row["market"] for row in rows if row.get("market"));concentration=Decimal(max(market_counts.values()))/Decimal(sum(market_counts.values())) if market_counts else None
    odds_status="ODDS_DRIFT_SAMPLE_INSUFFICIENT" if sample<policy.minimum_recent_window_sample else "ODDS_DRIFT_BLOCKED" if stale_rate is not None and stale_rate>=policy.stale_odds_block else "ODDS_DRIFT_WARNING" if (stale_rate is not None and stale_rate>=policy.stale_odds_warning) or (concentration is not None and concentration>=policy.market_concentration_warning) else "ODDS_DRIFT_CLEAR"
    reasoning=[row for row in rows if row.get("reasoning_status")];fragile=Decimal(sum(row.get("explanation_stability")=="EXPLANATION_FRAGILE" for row in reasoning))/Decimal(len(reasoning)) if reasoning else None;audit_fail=Decimal(sum(row.get("reasoning_audit") not in {"REASONING_AUDIT_PASSED","REASONING_AUDIT_WARNING"} for row in reasoning))/Decimal(len(reasoning)) if reasoning else None
    explanation_status="EXPLANATION_DRIFT_SAMPLE_INSUFFICIENT" if len(reasoning)<policy.minimum_explanation_sample else "EXPLANATION_DRIFT_BLOCKED" if (fragile is not None and fragile>=policy.explanation_fragile_block) or (audit_fail is not None and audit_fail>=policy.audit_failure_block) else "EXPLANATION_DRIFT_WARNING" if (fragile is not None and fragile>=policy.explanation_fragile_warning) or (audit_fail is not None and audit_fail>=policy.audit_failure_warning) else "EXPLANATION_DRIFT_CLEAR"
    scopes=[]
    for scope_type,key in (("MARKET","market"),("COMPETITION","competition"),("BOOKMAKER","bookmaker"),("MODEL_GENERATION","model_generation"),("CALIBRATION_ARTIFACT","calibration_artifact")):
        grouped=defaultdict(list)
        for row in rows:grouped[row[key]].append(row)
        values=CANONICAL_MARKETS if scope_type=="MARKET" else sorted(grouped)
        scopes.extend(_scope(grouped[value],scope_type,value,policy,cutoff.isoformat()) for value in values)
    current_generations=sorted({row["model_generation"] for row in rows});comparison={"status":"GENERATION_COMPARISON_INSUFFICIENT","current":current_generations[-1] if current_generations else None,"previous":current_generations[-2] if len(current_generations)>1 else None}
    if len(current_generations)>1:
        left=predictive([row for row in settled if row["model_generation"]==current_generations[-1]]);right=predictive([row for row in settled if row["model_generation"]==current_generations[-2]])
        if min(left["sample_size"],right["sample_size"])>=policy.minimum_scope_sample:
            delta=d(left["brier_score"])-d(right["brier_score"]);comparison={"status":"GENERATION_IMPROVED" if delta<=Decimal("-0.03") else "GENERATION_DEGRADED" if delta>=Decimal("0.03") else "GENERATION_NO_MEANINGFUL_CHANGE","current":current_generations[-1],"previous":current_generations[-2],"brier_delta":str(delta)}
    raw_statuses=(predictive_status,calibration_status,input_status,completeness_status,odds_status,explanation_status)
    severe=[status for status in raw_statuses if "BLOCKED" in status];warnings=[status for status in raw_statuses if "WARNING" in status];blocked_scopes=[scope for scope in scopes if scope["status"].endswith("_BLOCKED")]
    mathematical="BLOCKED" if severe or blocked_scopes else "WARNING" if warnings else "CLEAR"
    prior=tuple(previous_evaluations)[-policy.blocking_consecutive_evaluations:];prior_math=[item.get("decision",{}).get("mathematical_status") for item in prior];integrity_critical=any(row.get("integrity_critical") for row in rows)
    if sample_maturity in {"NO_EVIDENCE","GOVERNANCE_SAMPLE_INSUFFICIENT","WARM_UP","MONITORING"}:decision_status="GOVERNANCE_SAMPLE_INSUFFICIENT"
    elif integrity_critical:decision_status="GOVERNANCE_BLOCKED"
    elif mathematical=="BLOCKED" and prior_math.count("BLOCKED")>=policy.blocking_consecutive_evaluations-1:decision_status="GOVERNANCE_PUBLICATION_PAUSED"
    elif mathematical=="BLOCKED":decision_status="GOVERNANCE_REVIEW_REQUIRED"
    elif mathematical=="WARNING" and prior_math.count("WARNING")>=policy.warning_consecutive_evaluations-1:decision_status="GOVERNANCE_WARNING"
    elif mathematical=="WARNING":decision_status="GOVERNANCE_MONITOR"
    elif any(item.get("decision",{}).get("publication_impact")=="BLOCK" for item in tuple(previous_evaluations)[-policy.recovery_consecutive_evaluations:]) and len(tuple(previous_evaluations)[-policy.recovery_consecutive_evaluations:])<policy.recovery_consecutive_evaluations:decision_status="GOVERNANCE_MONITOR"
    else:decision_status="GOVERNANCE_CLEAR"
    recalibration="RECALIBRATION_RECOMMENDED" if "BLOCKED" in calibration_status else "RECALIBRATION_MONITOR" if "WARNING" in calibration_status else "RECALIBRATION_NOT_REQUIRED"
    retraining="RETRAINING_RECOMMENDED" if "BLOCKED" in input_status or len(blocked_scopes)>=2 else "RETRAINING_MONITOR" if warnings else "RETRAINING_NOT_REQUIRED"
    rollback="ROLLBACK_REVIEW_REQUIRED" if comparison["status"]=="GENERATION_DEGRADED" or integrity_critical else "ROLLBACK_MONITOR" if severe else "ROLLBACK_NOT_REQUIRED"
    affected={kind:sorted(scope["scope_value"] for scope in blocked_scopes if scope["scope_type"]==kind) for kind in ("MARKET","COMPETITION","BOOKMAKER","MODEL_GENERATION","CALIBRATION_ARTIFACT")}
    decision={"cutoff_utc":cutoff.isoformat(),"status":decision_status,"mathematical_status":mathematical,"primary_reason":(severe+warnings+[sample_maturity,"ALL_GOVERNANCE_GATES_CLEAR"])[0],"secondary_reasons":tuple((severe+warnings)[1:]),"affected_markets":affected["MARKET"],"affected_competitions":affected["COMPETITION"],"affected_bookmakers":affected["BOOKMAKER"],"affected_model_generations":affected["MODEL_GENERATION"],"publication_impact":"BLOCK" if decision_status in {"GOVERNANCE_PUBLICATION_PAUSED","GOVERNANCE_BLOCKED","GOVERNANCE_REVIEW_REQUIRED","GOVERNANCE_SAMPLE_INSUFFICIENT"} else "WARNING" if "WARNING" in decision_status or "MONITOR" in decision_status else "ALLOW","recommended_operator_action":"REVIEW_GOVERNANCE_EVIDENCE_MANUALLY","next_review_threshold":policy.minimum_total_settled_sample}
    recommendations=({"type":"RETRAINING","outcome":retraining,"execution_performed":False,"minimum_data_requirements":policy.minimum_total_settled_sample,"historical_odds_required":"REVIEW_REQUIRED"},{"type":"RECALIBRATION","outcome":recalibration,"execution_performed":False,"minimum_validation_sample":policy.minimum_total_settled_sample},{"type":"ROLLBACK","outcome":rollback,"execution_performed":False,"linked_activation_review":True})
    metrics={"predictive":pred,"predictive_status":predictive_status,"calibration":cal,"calibration_status":calibration_status,"features":feature_metrics,"top_shifted_features":sorted(feature_metrics,key=lambda item:d(item["psi"] or 0),reverse=True)[:10],"input_drift_status":input_status,"data_completeness":{"required_missing_rate":str(required_missing_rate) if required_missing_rate is not None else None,"optional_missing_rate":str(optional_missing_rate) if optional_missing_rate is not None else None,"lineup_availability_rate":str(Decimal(sum(bool(row.get("lineup_available")) for row in rows))/Decimal(len(rows))) if rows else None,"injury_availability_rate":str(Decimal(sum(bool(row.get("injury_available")) for row in rows))/Decimal(len(rows))) if rows else None,"provider_timestamp_completeness_rate":str(Decimal(sum(bool(row.get("settled_at_utc")) for row in rows))/Decimal(len(rows))) if rows else None,"status":completeness_status},"odds_drift":{"status":odds_status,"stale_rate":str(stale_rate) if stale_rate is not None else None,"quote_count":sum(row.get("odds") is not None for row in rows),"no_odds_rate":str(Decimal(sum(row.get("odds") is None for row in rows))/Decimal(len(rows))) if rows else None,"bookmaker_coverage":len({row.get("bookmaker") for row in rows if row.get("bookmaker")}),"market_coverage":len(market_counts),"selected_market_frequency":dict(sorted(market_counts.items())),"market_concentration":str(concentration) if concentration is not None else None,"odds_distribution":distribution(row.get("odds") for row in rows),"implied_probability_distribution":distribution(Decimal(1)/d(row["odds"]) for row in rows if row.get("odds"))},"explanation_drift":{"status":explanation_status,"sample_size":len(reasoning),"fragile_rate":str(fragile) if fragile is not None else None,"audit_failure_rate":str(audit_fail) if audit_fail is not None else None,"audit_status_distribution":dict(sorted(Counter(row.get("reasoning_audit") for row in reasoning).items())),"top_supporting_groups":Counter(group for row in reasoning for group in row.get("supporting_groups",())).most_common(10)},"generation_comparison":comparison}
    decision["decision_fingerprint"]=fingerprint(decision)
    material={"schema_version":"goalvision-forward-test-governance-evaluation-v1","evidence_class":evidence_class,"cutoff_utc":cutoff.isoformat(),"policy_id":policy.policy_id,"policy_version":policy.version,"policy_fingerprint":policy.fingerprint,"sample_maturity":sample_maturity,"included_observation_ids":tuple(row["observation_id"] for row in rows),"included_settlement_ids":tuple(row["settlement_id"] for row in rows if row.get("settlement_id")),"included_reasoning_ids":tuple(row["reasoning_id"] for row in rows if row.get("reasoning_id")),"included_audit_ids":tuple(row["reasoning_audit_id"] for row in rows if row.get("reasoning_audit_id")),"windows":windows,"metrics":metrics,"scope_statuses":scopes,"decision":decision,"recommendations":recommendations,"network_calls":0,"telegram_calls":0,"training_executions":0,"recalibration_executions":0,"rollback_executions":0}
    material["evaluation_fingerprint"]=fingerprint(material);material["evaluation_id"]="forward-test-governance-"+material["evaluation_fingerprint"];return material
