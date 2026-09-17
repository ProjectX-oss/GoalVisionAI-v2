"""Exact linear-score decomposition and deterministic evidence wording."""

from __future__ import annotations

import html
import json
import math
from dataclasses import asdict, is_dataclass
from decimal import Decimal

from app.historical_model_training import LIVE_TRAINING_FEATURE_CONTRACT, predict_raw_probabilities
from app.historical_model_training.estimators import BTTS, MATCH_RESULT, TOTAL_GOALS_BUCKET, predict_estimator
from app.historical_model_training.preprocessing import transform_vector
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

from .catalog import CATALOG_BY_NAME, CATALOG_FINGERPRINT, CATALOG_VERSION, group_label
from .models import ClassAttribution, EvidenceFactor, FeatureContribution, GroupContribution, MarketExplanation, ReasoningRecord
from .policy import DEFAULT_REASONING_POLICY, ReasoningPolicy


MARKETS=("HOME_WIN","DRAW","AWAY_WIN","OVER_1_5","UNDER_1_5","OVER_2_5","UNDER_2_5","OVER_3_5","UNDER_3_5","BTTS_YES","BTTS_NO")
_TOTAL_INCLUDED={"OVER_1_5":(1,2,3),"UNDER_1_5":(0,),"OVER_2_5":(2,3),"UNDER_2_5":(0,1),"OVER_3_5":(3,),"UNDER_3_5":(0,1,2)}


class ExplainabilityError(ValueError):
    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail); self.status=status


def _d(value) -> Decimal:
    return value if isinstance(value,Decimal) else Decimal(str(value))


def compute_class_attributions(artifact, model_input, *, source_timestamp_utc: str | None=None, policy: ReasoningPolicy=DEFAULT_REASONING_POLICY) -> tuple[ClassAttribution,...]:
    if artifact.artifact_format_version!="goalvision_safe_model_artifact_v1": raise ExplainabilityError("ARTIFACT_INCOMPLETE","Unsupported artifact format.")
    if artifact.feature_schema_fingerprint!=LIVE_TRAINING_FEATURE_CONTRACT.schema_fingerprint or tuple(artifact.ordered_feature_names)!=LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names: raise ExplainabilityError("FEATURE_SCHEMA_MISMATCH","Artifact is not compatible with live-78.")
    if tuple(model_input.ordered_feature_names)!=tuple(artifact.ordered_feature_names): raise ExplainabilityError("FEATURE_SCHEMA_MISMATCH","Model input feature order differs from the artifact.")
    if artifact.preprocessing.original_feature_names!=tuple(model_input.ordered_feature_names): raise ExplainabilityError("PREPROCESSING_MISMATCH","Persisted preprocessing input order differs.")
    try: transformed=transform_vector(model_input.ordered_feature_values,model_input.missingness_mask,artifact.preprocessing)
    except Exception as exc: raise ExplainabilityError("PREPROCESSING_MISMATCH",str(exc)) from exc
    names=artifact.preprocessing.transformed_feature_names
    if len(names)!=len(transformed): raise ExplainabilityError("PREPROCESSING_MISMATCH","Transformed feature declaration differs from its values.")
    raw_by_name=dict(zip(model_input.ordered_feature_names,model_input.ordered_feature_values))
    missing_by_name=dict(zip(model_input.ordered_feature_names,model_input.missingness_mask))
    output=[]
    for estimator in artifact.estimators:
        if estimator.model_type!="MULTINOMIAL_LOGISTIC_REGRESSION": raise ExplainabilityError("MODEL_TYPE_UNSUPPORTED",estimator.model_type)
        if len(estimator.coefficients)!=len(estimator.class_order) or len(estimator.intercepts)!=len(estimator.class_order): raise ExplainabilityError("ARTIFACT_INCOMPLETE","Class parameter dimensions differ.")
        probabilities=predict_estimator(estimator,transformed)
        reconstructed_scores=tuple(_d(intercept)+sum((_d(value)*_d(weight) for value,weight in zip(transformed,weights)),Decimal(0)) for intercept,weights in zip(estimator.intercepts,estimator.coefficients))
        maximum_reconstructed=max(reconstructed_scores);reconstructed_exponentials=tuple(math.exp(float(score-maximum_reconstructed)) for score in reconstructed_scores);reconstructed_total=math.fsum(reconstructed_exponentials);reconstructed_probabilities=tuple(value/reconstructed_total for value in reconstructed_exponentials)
        for class_index,class_name in enumerate(estimator.class_order):
            weights=estimator.coefficients[class_index]
            if len(weights)!=len(transformed): raise ExplainabilityError("ARTIFACT_INCOMPLETE","Coefficient width differs from transformed input.")
            contributions=[]
            for index,(transformed_name,value,weight) in enumerate(zip(names,transformed,weights)):
                base=transformed_name.removesuffix("__missing")
                if base not in CATALOG_BY_NAME: raise ExplainabilityError("FEATURE_SCHEMA_MISMATCH",f"Unknown feature: {base}")
                signed=_d(value)*_d(weight)
                material={"estimator":estimator.estimator_identity,"class":class_name,"index":index,"feature":base,"transformed_feature":transformed_name,"standardized":_d(value),"coefficient":_d(weight),"contribution":signed,"missing":bool(missing_by_name[base])}
                contributions.append(FeatureContribution(estimator.estimator_identity,class_name,base,transformed_name,None if raw_by_name[base] is None else str(raw_by_name[base]),_d(value),_d(weight),signed,bool(missing_by_name[base]),source_timestamp_utc,fingerprint(material)))
            score=_d(estimator.intercepts[class_index])+sum((item.signed_contribution for item in contributions),Decimal(0))
            float_score=estimator.intercepts[class_index]+math.fsum(weight*value for weight,value in zip(weights,transformed))
            score_ok=abs(score-_d(float_score))<=policy.score_tolerance
            probability=_d(probabilities[class_index])
            # Independently softmax the scores reconstructed from contributions.
            probability_ok=abs(probability-_d(reconstructed_probabilities[class_index]))<=policy.probability_tolerance
            if not score_ok: raise ExplainabilityError("SCORE_REPRODUCTION_FAILED",f"{estimator.estimator_identity}/{class_name}")
            if not probability_ok: raise ExplainabilityError("PROBABILITY_REPRODUCTION_FAILED",f"{estimator.estimator_identity}/{class_name}")
            material={"estimator":estimator.estimator_identity,"class":class_name,"intercept":_d(estimator.intercepts[class_index]),"score":score,"probability":probability,"contributions":contributions,"score_reproduced":score_ok,"probability_reproduced":probability_ok}
            output.append(ClassAttribution(estimator.estimator_identity,class_name,_d(estimator.intercepts[class_index]),score,probability,tuple(contributions),score_ok,probability_ok,fingerprint(material)))
    return tuple(output)


def _raw_probabilities(artifact,model_input) -> dict[str,Decimal]:
    prediction=predict_raw_probabilities(artifact,model_input.ordered_feature_values,model_input.missingness_mask,feature_schema_version=artifact.feature_schema_version,feature_schema_fingerprint=artifact.feature_schema_fingerprint,ordered_feature_names=model_input.ordered_feature_names)
    return {item.target.value:item.probability for item in prediction.raw_probabilities.ordered_probabilities}


def _selected_vector(market: str, attributions: tuple[ClassAttribution,...]) -> tuple[str,str,dict[str,Decimal]]:
    by_est={identity:[item for item in attributions if item.estimator_identity==identity] for identity in (MATCH_RESULT,TOTAL_GOALS_BUCKET,BTTS)}
    def contrast(selected, competitor):
        return {a.transformed_feature_name:a.signed_contribution-b.signed_contribution for a,b in zip(selected.contributions,competitor.contributions)}
    if market in {"HOME_WIN","DRAW","AWAY_WIN"}:
        selected=next(item for item in by_est[MATCH_RESULT] if item.class_identity==market); competitor=max((item for item in by_est[MATCH_RESULT] if item is not selected),key=lambda x:(x.probability,x.class_identity))
        return "DIRECT_CLASS_MARGIN",f"{market}_VERSUS_{competitor.class_identity}",contrast(selected,competitor)
    if market in {"BTTS_YES","BTTS_NO"}:
        selected=next(item for item in by_est[BTTS] if item.class_identity==market); competitor=next(item for item in by_est[BTTS] if item.class_identity!=market)
        return ("DIRECT_CLASS_MARGIN" if market=="BTTS_YES" else "COMPLEMENT_INVERSION"),f"{market}_VERSUS_{competitor.class_identity}",contrast(selected,competitor)
    classes=by_est[TOTAL_GOALS_BUCKET]; included=_TOTAL_INCLUDED[market]; excluded=tuple(i for i in range(4) if i not in included)
    def weighted(indices):
        total=sum((classes[i].probability for i in indices),Decimal(0)); result={name:Decimal(0) for name in (item.transformed_feature_name for item in classes[0].contributions)}
        for i in indices:
            weight=classes[i].probability/total
            for item in classes[i].contributions:result[item.transformed_feature_name]+=weight*item.signed_contribution
        return result
    inside,outside=weighted(included),weighted(excluded)
    return ("COMPLEMENT_INVERSION" if market.startswith("UNDER") else "DERIVED_BUCKET_SCORE_CONTRAST"),"TOTAL_GOALS_BUCKET_INCLUDED_VERSUS_EXCLUDED",{name:inside[name]-outside[name] for name in inside}


def _groups(vector: dict[str,Decimal],model_input,policy) -> tuple[GroupContribution,...]:
    members={}; missing=dict(zip(model_input.ordered_feature_names,model_input.missingness_mask))
    for transformed,value in vector.items():
        base=transformed.removesuffix("__missing"); entry=CATALOG_BY_NAME[base]; members.setdefault(entry.explanation_group,[]).append((base,value,missing[base],entry.public_display_eligible))
    preliminary=[]
    for group,items in members.items():
        signed=sum((item[1] for item in items),Decimal(0)); names=tuple(sorted({item[0] for item in items})); material={"group":group,"members":names,"signed":signed}
        preliminary.append((group,signed,names,sum(not item[2] for item in items),sum(item[2] for item in items),all(item[3] for item in items),fingerprint(material)))
    preliminary.sort(key=lambda x:(-abs(x[1]),x[0])); return tuple(GroupContribution(group,group_label(group),signed,abs(signed),rank,"SUPPORTING" if signed>0 else "OPPOSING" if signed<0 else "NEUTRAL",available,missing_count,public,names,fp) for rank,(group,signed,names,available,missing_count,public,fp) in enumerate(preliminary,1))


def _factors(groups,policy):
    material=[g for g in groups if g.public_eligible and g.absolute_contribution>=policy.materiality_threshold]; total=sum((g.absolute_contribution for g in groups),Decimal(0)) or Decimal(1); material=[g for g in material if g.absolute_contribution/total>=policy.materiality_share_threshold]
    positive=[];negative=[]
    for group in material:
        kind="SUPPORTING" if group.signed_contribution>0 else "OPPOSING"; verb="atbalstīja" if kind=="SUPPORTING" else "mazināja"
        text=f"Modeļa ievaddati grupā “{group.display_name_lv}” {verb} izvēlēto tirgu."
        value=EvidenceFactor(kind,group.group_id,group.display_name_lv,group.signed_contribution,group.member_feature_names,text,fingerprint({"group_fingerprint":group.group_fingerprint,"text":text,"type":kind}))
        (positive if kind=="SUPPORTING" else negative).append(value)
    return tuple(positive[:policy.maximum_public_supporting_factors]),tuple(negative[:policy.maximum_public_risk_factors])


def _market_rows(evaluations,raw):
    values=[]
    for index,item in enumerate(evaluations):
        value=asdict(item) if is_dataclass(item) else dict(item);value.setdefault("market",MARKETS[index] if index<len(MARKETS) else "UNKNOWN");value.setdefault("raw_probability",raw.get(value["market"]));values.append(value)
    by={item["market"]:item for item in values};return tuple(by.get(market,{"market":market,"raw_probability":raw[market],"rejection_reasons":["NO_BOOKMAKER_QUOTE"]}) for market in MARKETS)


def explain_prediction(*,artifact,model_input,analysis_id:str,selected_market:str,market_evaluations,created_at_utc:str,observation_id:str|None=None,calibration_artifact_id:str="UNKNOWN",calibration_fingerprint:str="UNKNOWN",calibration_quality_status:str="CALIBRATION_QUALITY_NOT_EVALUATED",distribution_shift_status:str="DISTRIBUTION_SHIFT_NOT_EVALUATED",shifted_features:tuple[str,...]=(),required_missing:tuple[str,...]=(),optional_missing:tuple[str,...]=(),lineup_status:str="UNKNOWN",injury_status:str="UNKNOWN",odds_age_minutes:Decimal|None=None,sample_status:str="FORWARD_TEST_SAMPLE_INSUFFICIENT",policy:ReasoningPolicy=DEFAULT_REASONING_POLICY) -> ReasoningRecord:
    if selected_market not in MARKETS:raise ExplainabilityError("ARTIFACT_INCOMPLETE","Selected market is unsupported.")
    attributions=compute_class_attributions(artifact,model_input,source_timestamp_utc=model_input.created_timestamp.isoformat(),policy=policy);raw=_raw_probabilities(artifact,model_input);rows=_market_rows(market_evaluations,raw);selected=next(item for item in rows if item["market"]==selected_market)
    mode,target,vector=_selected_vector(selected_market,attributions);groups=_groups(vector,model_input,policy);supporting,opposing=_factors(groups,policy)
    calibrated=_d(selected.get("calibrated_probability",raw[selected_market]));adjustment=calibrated-raw[selected_market]
    if calibration_quality_status not in {"CALIBRATION_QUALITY_ACCEPTABLE","ACCEPTABLE"}:calibration_text="Kalibrācijas kvalitāte šim tirgum nav pietiekama publicēšanai."
    elif abs(adjustment)>=policy.large_calibration_adjustment:calibration_text=("Kalibrācija būtiski palielināja" if adjustment>0 else "Kalibrācija būtiski samazināja")+" modeļa sākotnējo varbūtību."
    elif adjustment>0:calibration_text="Kalibrācija nedaudz palielināja modeļa sākotnējo varbūtību."
    elif adjustment<0:calibration_text="Kalibrācija nedaudz samazināja modeļa sākotnējo varbūtību."
    else:calibration_text="Kalibrācija nemainīja modeļa sākotnējo varbūtību."
    shift_block="BLOCK" in distribution_shift_status;shift_warning="WARNING" in distribution_shift_status
    shift_text="Konstatēta būtiska datu nobīde, tāpēc prognoze nav publicējama." if shift_block else "Daļa svarīgāko ievaddatu atšķiras no modeļa treniņu sadalījuma." if shift_warning else "Bloķējoša ievaddatu sadalījuma nobīde nav konstatēta."
    disclosures=[]
    if required_missing:disclosures.append(f"Trūkst {len(required_missing)} obligāto modeļa ievaddatu lauku.")
    if optional_missing:disclosures.append(f"Nav pieejami {len(optional_missing)} no 78 izvēles ievaddatu laukiem; tie aizstāti ar treniņdatos saglabātajām mediānām.")
    if "LINEUP" not in lineup_status.upper() and lineup_status.upper() not in {"CONFIRMED","AVAILABLE"}:disclosures.append("Sastāvi vēl nav pieejami.")
    if injury_status.upper() not in {"AVAILABLE","CONFIRMED"}:disclosures.append("Savainojumu dati nav pieejami vai nav apstiprināti.")
    if odds_age_minutes is not None:disclosures.append(f"Koeficienti tika fiksēti {odds_age_minutes.quantize(Decimal('1'))} minūtes pirms analīzes.")
    blockers=bool(required_missing) or shift_block or calibration_quality_status not in {"CALIBRATION_QUALITY_ACCEPTABLE","ACCEPTABLE"} or calibrated>policy.extreme_probability
    confidence="INELIGIBLE" if blockers else "REVIEW_REQUIRED" if shift_warning or optional_missing else "HIGH" if calibrated>=Decimal("0.70") and selected.get("actionable") else "MEDIUM" if selected.get("actionable") else "LOW"
    confidence_text=f"Pārliecība: {confidence}; tā ietver kalibrēto varbūtību, vērtību, datu pilnīgumu, nobīdi, koeficientu svaigumu un skaidrojuma stabilitāti. Parauga statuss: {sample_status}."
    market_explanations=[]
    for row in rows:
        p=_d(row.get("calibrated_probability",row["raw_probability"]));odds=_d(row["bookmaker_odds"]) if row.get("bookmaker_odds") is not None else None; implied=Decimal(1)/odds if odds else None;fair=Decimal(1)/p if p and calibration_quality_status in {"CALIBRATION_QUALITY_ACCEPTABLE","ACCEPTABLE"} else None;ev=p*odds-1 if odds and fair is not None else None;reasons=tuple(row.get("rejection_reasons") or ())
        if row["market"]!=selected_market and not reasons:reasons=("MATHEMATICALLY_LOWER_RANKED_MARKET",)
        primary=reasons[0] if reasons else None;concise="Tirgus ir izvēlēts pēc deterministiskā matemātiskā ranga." if row["market"]==selected_market else "Tirgus nav izvēlēts: "+(primary or "zemāks matemātiskais rangs")+"."
        material={"market":row["market"],"raw":_d(row["raw_probability"]),"calibrated":p,"odds":odds,"ev":ev,"rank":row.get("mathematical_rank"),"actionable":bool(row.get("actionable")),"reasons":reasons,"calibration":calibration_quality_status,"shift":distribution_shift_status}
        market_explanations.append(MarketExplanation(row["market"],mode if row["market"]==selected_market else "MARKET_EVALUATION",target if row["market"]==selected_market else row["market"],_d(row["raw_probability"]),p,odds,implied,fair,ev,row.get("mathematical_rank"),bool(row.get("actionable")),primary,reasons[1:],calibration_quality_status,distribution_shift_status,concise,canonical_json(material),fingerprint(material)))
    odds=_d(selected["bookmaker_odds"]) if selected.get("bookmaker_odds") is not None else None;breakeven=Decimal(1)/odds if odds else None;margin=calibrated-breakeven if breakeven else None;next_market=min((m for m in market_explanations if m.market!=selected_market),key=lambda x:(abs(x.calibrated_probability-calibrated),x.market))
    stability="EXPLANATION_FRAGILE" if margin is not None and abs(margin)<=policy.ev_sensitivity_interval else "EXPLANATION_MODERATELY_SENSITIVE" if len(groups)>1 and groups[0].absolute_contribution-groups[1].absolute_contribution<policy.stability_perturbation else "EXPLANATION_STABLE"
    counter=("BREAKEVEN_PROBABILITY",str(breakeven) if breakeven is not None else "UNAVAILABLE"),("PROBABILITY_MARGIN_TO_BREAKEVEN",str(margin) if margin is not None else "UNAVAILABLE"),("CLOSEST_COMPETING_MARKET",next_market.market),("EV_SENSITIVITY_INTERVAL",str(policy.ev_sensitivity_interval))
    risks=[item.public_text_lv for item in opposing]+disclosures
    if calibration_quality_status not in {"CALIBRATION_QUALITY_ACCEPTABLE","ACCEPTABLE"}:risks.append(calibration_text)
    if shift_warning or shift_block:risks.append(shift_text)
    support_lines=tuple(item.public_text_lv for item in supporting) or ("Neviena publiski attēlojama faktoru grupa nepārsniedza materialitātes slieksni.",)
    risk_lines=tuple(risks[:policy.maximum_public_risk_factors]) or ("Būtisks pretfaktors virs materialitātes sliekšņa netika identificēts.",)
    public="\n".join(("<b>Pamatojums:</b>",*(f"• {html.escape(line)}" for line in support_lines),"","<b>Riski:</b>",*(f"• {html.escape(line)}" for line in risk_lines),"",f"<b>Kalibrācija:</b> {html.escape(calibration_text)}",f"<b>Datu nobīde:</b> {html.escape(shift_text)}","⚠️ Eksperimentāls LAB skaidrojums; tas nepierāda cēloņsakarību vai peļņu."))
    if len(public)>policy.public_message_character_limit:public=public[:policy.public_message_character_limit-1]+"…"
    trace=fingerprint({"analysis":analysis_id,"observation":observation_id,"input":model_input.model_input_fingerprint,"artifact":artifact.artifact_fingerprint,"catalog":CATALOG_FINGERPRINT,"policy":policy.policy_fingerprint,"selected":selected_market,"markets":[m.market_fingerprint for m in market_explanations]})
    operator=canonical_json({"schema_version":"goalvision-operator-reasoning-v1","analysis_id":analysis_id,"selected_market":selected_market,"attribution_mode":mode,"target_identity":target,"class_attributions":attributions,"groups":groups,"supporting":supporting,"opposing":opposing,"missing_data":disclosures,"calibration":{"raw":raw[selected_market],"calibrated":calibrated,"adjustment":adjustment,"artifact":calibration_artifact_id,"status":calibration_quality_status},"shift":{"status":distribution_shift_status,"shifted_features":shifted_features},"confidence":{"status":confidence,"rationale":confidence_text},"counterfactuals":counter,"market_explanations":market_explanations,"network_calls":0,"telegram_calls":0})
    public_fp=fingerprint({"version":"goalvision-public-latvian-reasoning-v1","html":public})
    status="REASONING_BLOCKED" if blockers else "REASONING_CREATED";material={"observation_id":observation_id,"analysis_id":analysis_id,"model_input_id":model_input.model_input_id,"model_input_fingerprint":model_input.model_input_fingerprint,"model_artifact_id":artifact.artifact_id,"model_artifact_fingerprint":artifact.artifact_fingerprint,"calibration_artifact_id":calibration_artifact_id,"calibration_fingerprint":calibration_fingerprint,"selected_market":selected_market,"status":status,"catalog":CATALOG_FINGERPRINT,"policy":policy.policy_fingerprint,"public":public_fp,"operator":fingerprint(operator),"supporting":[x.evidence_fingerprint for x in supporting],"opposing":[x.evidence_fingerprint for x in opposing],"markets":[x.market_fingerprint for x in market_explanations],"trace":trace,"created_at":created_at_utc}
    reasoning_fp=fingerprint(material);reasoning_id="prediction-reasoning-"+reasoning_fp
    return ReasoningRecord(reasoning_id,observation_id,analysis_id,model_input.model_input_id,model_input.model_input_fingerprint,artifact.artifact_id,artifact.artifact_fingerprint,calibration_artifact_id,calibration_fingerprint,selected_market,status,CATALOG_VERSION,CATALOG_FINGERPRINT,policy.version,policy.policy_fingerprint,public,public_fp,operator,supporting,opposing,tuple(risks),tuple(disclosures),calibration_text,shift_text,confidence,confidence_text,tuple(market_explanations),counter,attributions,groups,"CONTRIBUTIONS_COMPUTED",stability,trace,reasoning_fp,created_at_utc)
