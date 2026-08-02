"""Immutable explainability contracts."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FeatureContribution:
    estimator_identity: str; class_identity: str; feature_name: str; transformed_feature_name: str
    raw_value: str | None; standardized_value: Decimal; coefficient: Decimal; signed_contribution: Decimal
    missing: bool; source_timestamp_utc: str | None; contribution_fingerprint: str


@dataclass(frozen=True, slots=True)
class ClassAttribution:
    estimator_identity: str; class_identity: str; intercept: Decimal; score: Decimal; probability: Decimal
    contributions: tuple[FeatureContribution, ...]; score_reproduced: bool; probability_reproduced: bool; attribution_fingerprint: str


@dataclass(frozen=True, slots=True)
class GroupContribution:
    group_id: str; display_name_lv: str; signed_contribution: Decimal; absolute_contribution: Decimal
    rank: int; direction: str; supporting_feature_count: int; missing_feature_count: int
    public_eligible: bool; member_feature_names: tuple[str, ...]; group_fingerprint: str


@dataclass(frozen=True, slots=True)
class EvidenceFactor:
    factor_type: str; group_id: str; display_name_lv: str; signed_contribution: Decimal
    member_feature_names: tuple[str, ...]; public_text_lv: str; evidence_fingerprint: str


@dataclass(frozen=True, slots=True)
class MarketExplanation:
    market: str; attribution_mode: str; target_identity: str; raw_probability: Decimal
    calibrated_probability: Decimal; bookmaker_odds: Decimal | None; implied_probability: Decimal | None
    fair_odds: Decimal | None; expected_value: Decimal | None; mathematical_rank: int | None
    actionable: bool; primary_rejection_code: str | None; secondary_rejection_codes: tuple[str, ...]
    calibration_quality_status: str; distribution_shift_status: str
    concise_explanation_lv: str; operator_explanation: str; market_fingerprint: str


@dataclass(frozen=True, slots=True)
class ReasoningRecord:
    reasoning_id: str; observation_id: str | None; analysis_id: str; model_input_id: str
    model_input_fingerprint: str; model_artifact_id: str; model_artifact_fingerprint: str
    calibration_artifact_id: str; calibration_fingerprint: str; selected_market: str
    reasoning_status: str; feature_catalog_version: str; feature_catalog_fingerprint: str
    reasoning_policy_version: str; reasoning_policy_fingerprint: str
    public_reasoning_html: str; public_reasoning_fingerprint: str; operator_reasoning_json: str
    supporting_factors: tuple[EvidenceFactor, ...]; opposing_factors: tuple[EvidenceFactor, ...]
    risk_factors: tuple[str, ...]; missing_data_disclosures: tuple[str, ...]
    calibration_explanation: str; shift_explanation: str; confidence: str; confidence_explanation: str
    market_explanations: tuple[MarketExplanation, ...]; counterfactuals: tuple[tuple[str,str], ...]
    class_attributions: tuple[ClassAttribution, ...]; selected_group_contributions: tuple[GroupContribution, ...]
    contribution_reproduction_status: str; explanation_stability_status: str
    trace_fingerprint: str; reasoning_fingerprint: str; created_at_utc: str


@dataclass(frozen=True, slots=True)
class ReasoningAudit:
    audit_id: str; reasoning_id: str; status: str; findings: tuple[tuple[str,str,str], ...]
    checked_at_utc: str; audit_fingerprint: str
