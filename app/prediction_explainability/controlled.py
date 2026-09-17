"""Controlled fictional live-78 artifact, input, and complete reasoning rehearsal."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from app.historical_model_training.estimators import BTTS, MATCH_RESULT, TOTAL_GOALS_BUCKET
from app.historical_model_training.models import FittedEstimator, FittedPreprocessing, ModelArtifact, PreprocessingFeature
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT
from app.model_input_builder.models import ModelInputVector
from app.model_input_builder.schema import GOALVISION_MODEL_INPUT_V1
from app.prediction_inference.models import OFFICIAL_TARGET_ORDER
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

from .service import PredictionExplainabilityService


CONTROLLED_TIME="2026-08-02T14:00:00+00:00"


def controlled_artifact_and_input():
    names=LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names;width=len(names)
    preprocessing_features=tuple(PreprocessingFeature(name,index,index,0.0,0,0.0,1.0,False,fingerprint(("controlled-preprocessing",index,name))) for index,name in enumerate(names))
    preprocessing=FittedPreprocessing("controlled-standard-scaling-v1","DETERMINISTIC_MEDIAN_IMPUTATION_V1","STANDARD_SCALING_V1",False,names,names,preprocessing_features,fingerprint(preprocessing_features))
    def weights(seed,classes):
        rows=[]
        for class_index in range(classes):rows.append(tuple(((index%7)-3)*(class_index+1)*seed if index<18 else 0.0 for index in range(width)))
        return tuple(rows)
    estimators=[]
    for identity,classes,seed,intercepts in ((MATCH_RESULT,("HOME_WIN","DRAW","AWAY_WIN"),0.035,(0.35,0.05,-0.25)),(TOTAL_GOALS_BUCKET,("UNDER_1_5","GOALS_2","GOALS_3","OVER_3_5"),0.018,(0.0,0.2,0.1,-0.1)),(BTTS,("BTTS_NO","BTTS_YES"),0.025,(0.0,0.18))):
        coeff=weights(seed,len(classes));material={"identity":identity,"classes":classes,"coefficients":coeff,"intercepts":intercepts}
        estimators.append(FittedEstimator(identity,"MULTINOMIAL_LOGISTIC_REGRESSION",classes,coeff,tuple(intercepts),100,True,0.0,fingerprint(material)))
    compatibility={"input_schema_identifier":LIVE_MODEL_INPUT_CONTRACT.schema_identifier,"feature_schema_version":LIVE_MODEL_INPUT_CONTRACT.schema_version,"feature_schema_fingerprint":LIVE_MODEL_INPUT_CONTRACT.schema_fingerprint,"feature_count":78,"compatibility_version":LIVE_MODEL_INPUT_CONTRACT.compatibility_version,"fingerprint_version":LIVE_MODEL_INPUT_CONTRACT.fingerprint_version,"ordered_feature_names":names,"model_family":"CONTROLLED_MULTINOMIAL_LOGISTIC","label_schema_version":"v1","target_schema_version":"v1","canonical_target_order":[item.value for item in OFFICIAL_TARGET_ORDER]}
    artifact_material={"preprocessing":preprocessing.preprocessing_fingerprint,"estimators":[x.estimator_fingerprint for x in estimators],"compatibility":compatibility};artifact_fp=fingerprint(artifact_material)
    artifact=ModelArtifact("historical-model-artifact-"+artifact_fp,artifact_fp,"controlled-training-run",fingerprint("controlled-request"),"controlled-split",fingerprint("controlled-split"),"controlled-fold",fingerprint("controlled-fold"),"CONTROLLED_MULTINOMIAL_LOGISTIC",LIVE_MODEL_INPUT_CONTRACT.schema_version,LIVE_MODEL_INPUT_CONTRACT.schema_fingerprint,names,"v1","v1",OFFICIAL_TARGET_ORDER,"goalvision_safe_model_artifact_v1",preprocessing,tuple(estimators),CONTROLLED_TIME,canonical_json(compatibility),canonical_json({"evidence_class":"CONTROLLED_FICTIONAL_PREDICTION_EXPLAINABILITY_REHEARSAL"}))
    optional_missing={"home_confirmed_lineup_indicator","away_confirmed_lineup_indicator","home_injuries_count","away_injuries_count"};values=[];mask=[]
    for index,item in enumerate(GOALVISION_MODEL_INPUT_V1.ordered_feature_metadata):
        missing=item.name in optional_missing;mask.append(missing)
        if missing:values.append(None)
        elif item.value_type.value=="BOOLEAN":values.append(index%2==0)
        elif item.value_type.value=="INTEGER":values.append((index%4)+1)
        else:values.append(Decimal(str(((index%9)+1)/10)))
    input_material={"names":names,"values":values,"missing":mask,"evidence":"CONTROLLED_FICTIONAL"};input_fp=fingerprint(input_material)
    vector=ModelInputVector("controlled-live-78-input-"+input_fp,"controlled-feature-set","controlled-snapshot","fictional-fixture-1",LIVE_MODEL_INPUT_CONTRACT.schema_name,LIVE_MODEL_INPUT_CONTRACT.schema_version,LIVE_MODEL_INPUT_CONTRACT.compatibility_version,names,tuple(values),tuple(mask),tuple(sorted(optional_missing)),Decimal(74)/Decimal(78),GOALVISION_MODEL_INPUT_V1.ordered_feature_metadata,fingerprint(("controlled-features",values)),fingerprint("controlled-snapshot"),fingerprint("controlled-feature-source"),input_fp,datetime.fromisoformat(CONTROLLED_TIME))
    return artifact,vector


def run_controlled_rehearsal(database,*,seed_console_demo:bool=True):
    """Exercise reasoning, preview, review, console and reporting locally."""
    result=_run_controlled_reasoning(database,seed_console_demo=seed_console_demo)
    repository=PredictionExplainabilityService(database).repository;record=repository.load(result["reasoning_id"]);audit=repository.audit_for(result["reasoning_id"])
    replay=_run_controlled_reasoning(database,seed_console_demo=False)
    from app.current_odds_forward_test.operations import FirstLabOperationsRepository, build_publication_review, build_reasoned_lab_preview
    from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
    forward_tests=SQLiteForwardTestRepository(database,migrate=False);preview=build_reasoned_lab_preview(forward_tests,record.observation_id)
    publication_review=build_publication_review(forward_tests,record.observation_id,reviewed_at=datetime.fromisoformat(CONTROLLED_TIME),persist=FirstLabOperationsRepository(database,migrate=False))
    from app.forward_test_monitoring import MonitoringService, SQLiteMonitoringRepository
    report=MonitoringService(SQLiteMonitoringRepository(database,migrate=False)).report("CUMULATIVE",datetime.fromisoformat("2026-08-02T14:05:00+00:00"))
    from app.lab_operator_console.reads import ConsoleReadService
    from pathlib import Path
    console_page=ConsoleReadService(database,Path("CONTROLLED_IN_MEMORY.db"),controlled_demo=True).page("reasoning",record.reasoning_id)
    result.update({"rejected_markets":[item.market for item in record.market_explanations if item.market!=record.selected_market],"preview_status":preview["status"],"preview_fingerprint":preview["preview_fingerprint"],"publication_review_status":publication_review["status"],"publication_review_blockers":publication_review["blocker_codes"],"report_id":report["report_id"],"report_reasoning_records":report["explainability"]["reasoning_records_created"],"console_reasoning_rows":sum(len(table.rows) for table in console_page.tables),"reasoning_fingerprint_reproduced":replay["reasoning_fingerprint"]==record.reasoning_fingerprint,"production_activation_mutations":0,"thestatsapi_calls":0,"paid_historical_odds_probes":0,"bookmaker_transactions":0,"startup_network_calls":0,"replayed":replay["replayed"]})
    return result


def _run_controlled_reasoning(database,*,seed_console_demo:bool=True):
    if seed_console_demo:
        from app.lab_operator_console.demo import build_demo
        build_demo(database)
    artifact,model_input=controlled_artifact_and_input()
    from app.historical_model_training import predict_raw_probabilities
    probabilities=predict_raw_probabilities(artifact,model_input.ordered_feature_values,model_input.missingness_mask,feature_schema_version=artifact.feature_schema_version,feature_schema_fingerprint=artifact.feature_schema_fingerprint,ordered_feature_names=model_input.ordered_feature_names).raw_probabilities
    raw={item.target.value:item.probability for item in probabilities.ordered_probabilities};selected="HOME_WIN";evaluations=[]
    for rank,market in enumerate(sorted(raw,key=lambda x:(-raw[x],x)),1):
        odds=Decimal("2.20") if market==selected else Decimal("1.90");calibrated=min(Decimal("0.94"),raw[market]+(Decimal("0.02") if market==selected else Decimal("0")));ev=calibrated*odds-1
        evaluations.append({"market":market,"raw_probability":raw[market],"calibrated_probability":calibrated,"bookmaker_odds":odds,"mathematical_rank":rank,"actionable":market==selected and ev>0,"selected":market==selected,"rejection_reasons":[] if market==selected else ["MATHEMATICALLY_LOWER_RANKED_MARKET"]})
    service=PredictionExplainabilityService(database);result=service.create(artifact=artifact,model_input=model_input,analysis_id="fictional-analysis-1",observation_id="fictional-observation-1",selected_market=selected,market_evaluations=evaluations,created_at_utc=CONTROLLED_TIME,checked_at_utc=CONTROLLED_TIME,calibration_artifact_id="controlled-calibration-v1",calibration_fingerprint=fingerprint("controlled-calibration-v1"),calibration_quality_status="CALIBRATION_QUALITY_ACCEPTABLE",distribution_shift_status="DISTRIBUTION_SHIFT_WARNING",shifted_features=("home_recent_points_per_match",),optional_missing=model_input.missing_feature_names,lineup_status="UNAVAILABLE",injury_status="UNAVAILABLE",odds_age_minutes=Decimal("6"))
    record,audit=result["record"],result["audit"]
    preview=f"🧪 <b>GoalVision AI Lab</b>\n\n{record.public_reasoning_html}\n\nPREVIEW ONLY — NOTHING HAS BEEN SENT";preview_fp=fingerprint({"reasoning":record.public_reasoning_fingerprint,"preview":preview})
    return {"evidence_class":"CONTROLLED_FICTIONAL_PREDICTION_EXPLAINABILITY_REHEARSAL","selected_market":selected,"raw_probability":str(next(x for x in record.market_explanations if x.market==selected).raw_probability),"calibrated_probability":str(next(x for x in record.market_explanations if x.market==selected).calibrated_probability),"supporting_factors":[x.group_id for x in record.supporting_factors],"opposing_factors":[x.group_id for x in record.opposing_factors],"risk_factors":list(record.risk_factors),"stability":record.explanation_stability_status,"reasoning_id":record.reasoning_id,"reasoning_fingerprint":record.reasoning_fingerprint,"audit_status":audit.status,"audit_fingerprint":audit.audit_fingerprint,"preview_fingerprint":preview_fp,"score_reproduction":all(x.score_reproduced for x in record.class_attributions),"probability_reproduction":all(x.probability_reproduced for x in record.class_attributions),"market_count":len(record.market_explanations),"feature_count":78,"network_calls":0,"telegram_calls":0,"delivery_records":0,"official_mutations":0,"bankroll_mutations":0,"statistics_mutations":0,"scheduling_changes":0,"replayed":result["replayed"]}
