"""Fail-closed integrity audit for persisted deterministic reasoning."""

from __future__ import annotations

from app.real_match_lab_analysis.fingerprint import fingerprint

from .models import ReasoningAudit, ReasoningRecord
from .policy import DEFAULT_REASONING_POLICY, ReasoningPolicy


def audit_reasoning(record: ReasoningRecord, *, checked_at_utc: str, policy: ReasoningPolicy=DEFAULT_REASONING_POLICY) -> ReasoningAudit:
    findings=[]
    def add(code,severity,detail):findings.append((code,severity,detail))
    if record.reasoning_id!="prediction-reasoning-"+record.reasoning_fingerprint:add("REASONING_FINGERPRINT_ID_MISMATCH","CORRUPT","Reasoning ID does not match its canonical fingerprint.")
    if fingerprint({"version":"goalvision-public-latvian-reasoning-v1","html":record.public_reasoning_html})!=record.public_reasoning_fingerprint:add("PUBLIC_REASONING_FINGERPRINT_MISMATCH","CORRUPT","Public reasoning content differs from its fingerprint.")
    if not record.analysis_id or not record.model_input_id or not record.model_artifact_id:add("REASONING_LINKAGE_INCOMPLETE","BLOCKING","Required immutable evidence linkage is absent.")
    if record.contribution_reproduction_status!="CONTRIBUTIONS_COMPUTED" or not all(x.score_reproduced and x.probability_reproduced for x in record.class_attributions):add("CONTRIBUTION_REPRODUCTION_FAILED","CORRUPT","Class scores or probabilities were not reproduced.")
    eligible_features={name for factor in record.supporting_factors+record.opposing_factors for name in factor.member_feature_names}
    contribution_features={item.feature_name for attribution in record.class_attributions for item in attribution.contributions}
    if not eligible_features.issubset(contribution_features):add("UNTRACEABLE_PUBLIC_FACTOR","CORRUPT","A public factor is not traceable to a model contribution.")
    lowered=record.public_reasoning_html.casefold()
    for phrase in policy.prohibited_phrases+policy.certainty_blacklist:
        if phrase.casefold() in lowered:add("PROHIBITED_REASONING_PHRASE","BLOCKING",f"Prohibited phrase detected: {phrase}")
    if "CORRECT_SCORE" in record.operator_reasoning_json or "COMBO" in record.operator_reasoning_json:add("PROHIBITED_MARKET_CLAIM","BLOCKING","Correct-score or combo content is prohibited.")
    if "REASONING_BLOCKED"==record.reasoning_status and not any(term in lowered for term in ("nav publicējama","nav pietiekama","trūkst")):add("HIDDEN_REASONING_BLOCKER","BLOCKING","Blocked reasoning does not disclose a blocker publicly.")
    if record.confidence=="HIGH" and record.reasoning_status!="REASONING_CREATED":add("CONFIDENCE_BLOCKER_CONFLICT","BLOCKING","HIGH confidence cannot coexist with a blocker.")
    if len(record.public_reasoning_html)>policy.public_message_character_limit:add("PUBLIC_REASONING_TOO_LONG","BLOCKING","Public reasoning exceeds the policy limit.")
    if not record.supporting_factors:add("NO_MATERIAL_PUBLIC_SUPPORT","WARNING","No public supporting factor exceeded materiality.")
    if record.explanation_stability_status=="EXPLANATION_FRAGILE":add("FRAGILE_EXPLANATION","WARNING","Top reasoning is sensitive to a small controlled change.")
    severity={item[1] for item in findings};status="REASONING_AUDIT_CORRUPT" if "CORRUPT" in severity else "REASONING_AUDIT_BLOCKED" if "BLOCKING" in severity else "REASONING_AUDIT_WARNING" if "WARNING" in severity else "REASONING_AUDIT_PASSED"
    material={"reasoning_id":record.reasoning_id,"reasoning_fingerprint":record.reasoning_fingerprint,"status":status,"findings":findings,"checked_at_utc":checked_at_utc,"policy_fingerprint":policy.policy_fingerprint};fp=fingerprint(material)
    return ReasoningAudit("prediction-reasoning-audit-"+fp,record.reasoning_id,status,tuple(findings),checked_at_utc,fp)
