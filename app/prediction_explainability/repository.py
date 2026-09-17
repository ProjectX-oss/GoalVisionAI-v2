"""Atomic append-only persistence and exact replay for reasoning evidence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from decimal import Decimal

from app.database import Database, MigrationManager
from app.real_match_lab_analysis.fingerprint import canonical_json

from .models import ClassAttribution, EvidenceFactor, FeatureContribution, GroupContribution, MarketExplanation, ReasoningAudit, ReasoningRecord


class ReasoningConflictError(RuntimeError):pass


class SQLiteReasoningRepository:
    def __init__(self,database:Database,*,migrate:bool=True)->None:
        self.connection=database.connection
        if migrate:MigrationManager(self.connection).migrate()

    @classmethod
    def from_connection(cls, connection):
        """Adapt an existing migrated SQLite connection without side effects."""
        repository=cls.__new__(cls);repository.connection=connection;return repository

    def append(self,record:ReasoningRecord)->tuple[ReasoningRecord,bool]:
        existing=self.connection.execute("SELECT reasoning_fingerprint,reasoning_json FROM prediction_reasoning_records WHERE analysis_id=? AND selected_market=?",(record.analysis_id,record.selected_market)).fetchone()
        if existing:
            if existing[0]!=record.reasoning_fingerprint:raise ReasoningConflictError("PREDICTION_REASONING_REPLAY_CONFLICT")
            return _record(json.loads(existing[1])),True
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute("INSERT INTO prediction_reasoning_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(record.reasoning_id,record.observation_id,record.analysis_id,record.model_input_id,record.model_input_fingerprint,record.model_artifact_id,record.model_artifact_fingerprint,record.calibration_artifact_id,record.calibration_fingerprint,record.selected_market,record.reasoning_status,record.feature_catalog_fingerprint,record.reasoning_policy_fingerprint,record.public_reasoning_fingerprint,record.reasoning_fingerprint,canonical_json(record),record.created_at_utc))
            sequence=0
            for attribution in record.class_attributions:
                for item in attribution.contributions:
                    self.connection.execute("INSERT INTO prediction_reasoning_feature_contributions VALUES (?,?,?,?,?,?,?,?,?)",(f"{record.reasoning_id}-feature-{sequence}",record.reasoning_id,sequence,item.estimator_identity,item.class_identity,item.feature_name,item.signed_contribution.__str__(),item.contribution_fingerprint,canonical_json(item)));sequence+=1
            for item in record.selected_group_contributions:self.connection.execute("INSERT INTO prediction_reasoning_group_contributions VALUES (?,?,?,?,?,?,?)",(f"{record.reasoning_id}-group-{item.rank}",record.reasoning_id,item.rank,item.group_id,str(item.signed_contribution),item.group_fingerprint,canonical_json(item)))
            for order,item in enumerate(record.supporting_factors+record.opposing_factors):self.connection.execute("INSERT INTO prediction_reasoning_factors VALUES (?,?,?,?,?,?,?)",(f"{record.reasoning_id}-factor-{order}",record.reasoning_id,order,item.factor_type,item.group_id,item.evidence_fingerprint,canonical_json(item)))
            for order,item in enumerate(record.market_explanations):self.connection.execute("INSERT INTO prediction_reasoning_market_explanations VALUES (?,?,?,?,?,?,?)",(f"{record.reasoning_id}-market-{order}",record.reasoning_id,order,item.market,item.primary_rejection_code,item.market_fingerprint,canonical_json(item)))
            self.connection.commit();return record,False
        except Exception:
            self.connection.rollback();raise

    def append_audit(self,audit:ReasoningAudit)->tuple[ReasoningAudit,bool]:
        existing=self.connection.execute("SELECT audit_fingerprint,audit_json FROM prediction_reasoning_audits WHERE reasoning_id=?",(audit.reasoning_id,)).fetchone()
        if existing:
            if existing[0]!=audit.audit_fingerprint:raise ReasoningConflictError("PREDICTION_REASONING_AUDIT_REPLAY_CONFLICT")
            return _audit(json.loads(existing[1])),True
        with self.connection:
            self.connection.execute("INSERT INTO prediction_reasoning_audits VALUES (?,?,?,?,?,?)",(audit.audit_id,audit.reasoning_id,audit.status,audit.checked_at_utc,audit.audit_fingerprint,canonical_json(audit)))
            for order,(code,severity,detail) in enumerate(audit.findings):self.connection.execute("INSERT INTO prediction_reasoning_audit_findings VALUES (?,?,?,?,?,?,?)",(f"{audit.audit_id}-{order}",audit.audit_id,order,code,severity,detail,canonical_json({"code":code,"severity":severity,"detail":detail})))
        return audit,False

    def load(self,reasoning_id:str)->ReasoningRecord|None:
        row=self.connection.execute("SELECT reasoning_json FROM prediction_reasoning_records WHERE reasoning_id=?",(reasoning_id,)).fetchone();return _record(json.loads(row[0])) if row else None
    def for_analysis(self,analysis_id:str)->ReasoningRecord|None:
        row=self.connection.execute("SELECT reasoning_json FROM prediction_reasoning_records WHERE analysis_id=? ORDER BY created_at_utc DESC LIMIT 1",(analysis_id,)).fetchone();return _record(json.loads(row[0])) if row else None
    def for_observation(self,observation_id:str)->ReasoningRecord|None:
        row=self.connection.execute("SELECT reasoning_json FROM prediction_reasoning_records WHERE observation_id=? ORDER BY created_at_utc DESC LIMIT 1",(observation_id,)).fetchone();return _record(json.loads(row[0])) if row else None
    def list(self,limit:int=100)->tuple[ReasoningRecord,...]:
        return tuple(_record(json.loads(row[0])) for row in self.connection.execute("SELECT reasoning_json FROM prediction_reasoning_records ORDER BY created_at_utc DESC,reasoning_id LIMIT ?",(limit,)))
    def audit_for(self,reasoning_id:str)->ReasoningAudit|None:
        row=self.connection.execute("SELECT audit_json FROM prediction_reasoning_audits WHERE reasoning_id=?",(reasoning_id,)).fetchone();return _audit(json.loads(row[0])) if row else None


def _feature(value):return FeatureContribution(value["estimator_identity"],value["class_identity"],value["feature_name"],value["transformed_feature_name"],value["raw_value"],Decimal(value["standardized_value"]),Decimal(value["coefficient"]),Decimal(value["signed_contribution"]),bool(value["missing"]),value["source_timestamp_utc"],value["contribution_fingerprint"])
def _class(value):return ClassAttribution(value["estimator_identity"],value["class_identity"],Decimal(value["intercept"]),Decimal(value["score"]),Decimal(value["probability"]),tuple(_feature(x) for x in value["contributions"]),bool(value["score_reproduced"]),bool(value["probability_reproduced"]),value["attribution_fingerprint"])
def _group(value):return GroupContribution(value["group_id"],value["display_name_lv"],Decimal(value["signed_contribution"]),Decimal(value["absolute_contribution"]),int(value["rank"]),value["direction"],int(value["supporting_feature_count"]),int(value["missing_feature_count"]),bool(value["public_eligible"]),tuple(value["member_feature_names"]),value["group_fingerprint"])
def _factor(value):return EvidenceFactor(value["factor_type"],value["group_id"],value["display_name_lv"],Decimal(value["signed_contribution"]),tuple(value["member_feature_names"]),value["public_text_lv"],value["evidence_fingerprint"])
def _market(value):return MarketExplanation(value["market"],value["attribution_mode"],value["target_identity"],Decimal(value["raw_probability"]),Decimal(value["calibrated_probability"]),Decimal(value["bookmaker_odds"]) if value["bookmaker_odds"] is not None else None,Decimal(value["implied_probability"]) if value["implied_probability"] is not None else None,Decimal(value["fair_odds"]) if value["fair_odds"] is not None else None,Decimal(value["expected_value"]) if value["expected_value"] is not None else None,value["mathematical_rank"],bool(value["actionable"]),value["primary_rejection_code"],tuple(value["secondary_rejection_codes"]),value["calibration_quality_status"],value["distribution_shift_status"],value["concise_explanation_lv"],value["operator_explanation"],value["market_fingerprint"])
def _record(v):return ReasoningRecord(v["reasoning_id"],v["observation_id"],v["analysis_id"],v["model_input_id"],v["model_input_fingerprint"],v["model_artifact_id"],v["model_artifact_fingerprint"],v["calibration_artifact_id"],v["calibration_fingerprint"],v["selected_market"],v["reasoning_status"],v["feature_catalog_version"],v["feature_catalog_fingerprint"],v["reasoning_policy_version"],v["reasoning_policy_fingerprint"],v["public_reasoning_html"],v["public_reasoning_fingerprint"],v["operator_reasoning_json"],tuple(_factor(x) for x in v["supporting_factors"]),tuple(_factor(x) for x in v["opposing_factors"]),tuple(v["risk_factors"]),tuple(v["missing_data_disclosures"]),v["calibration_explanation"],v["shift_explanation"],v["confidence"],v["confidence_explanation"],tuple(_market(x) for x in v["market_explanations"]),tuple(tuple(x) for x in v["counterfactuals"]),tuple(_class(x) for x in v["class_attributions"]),tuple(_group(x) for x in v["selected_group_contributions"]),v["contribution_reproduction_status"],v["explanation_stability_status"],v["trace_fingerprint"],v["reasoning_fingerprint"],v["created_at_utc"])
def _audit(v):return ReasoningAudit(v["audit_id"],v["reasoning_id"],v["status"],tuple(tuple(x) for x in v["findings"]),v["checked_at_utc"],v["audit_fingerprint"])
