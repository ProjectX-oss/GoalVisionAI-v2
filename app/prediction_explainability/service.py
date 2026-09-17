"""Explicit service boundary; creation never performs network or Telegram work."""

import json
from dataclasses import replace

from app.database import Database
from app.historical_model_training import SQLiteHistoricalModelTrainingRepository
from app.model_input_builder.repository import SQLiteModelInputRepository

from .audit import audit_reasoning
from .engine import compute_class_attributions, explain_prediction
from .repository import SQLiteReasoningRepository


class PredictionExplainabilityService:
    def __init__(self,database:Database)->None:self.database=database;self.repository=SQLiteReasoningRepository(database)

    def create(self,*,artifact,model_input,checked_at_utc:str,**context):
        record=explain_prediction(artifact=artifact,model_input=model_input,**context);stored,replayed=self.repository.append(record);audit=audit_reasoning(stored,checked_at_utc=checked_at_utc);stored_audit,audit_replayed=self.repository.append_audit(audit);return {"record":stored,"audit":stored_audit,"replayed":replayed,"audit_replayed":audit_replayed,"provider_calls":0,"telegram_calls":0,"official_mutations":0}

    def create_for_analysis(self,analysis_id:str,*,created_at_utc:str,observation_id:str|None=None):
        row=self.database.connection.execute("SELECT result_snapshot,selected_market FROM real_match_lab_analyses WHERE analysis_id=?",(analysis_id,)).fetchone()
        if row is None:raise ValueError("Analysis not found.")
        result=json.loads(row[0]);evidence=result.get("evidence") or {};artifact=SQLiteHistoricalModelTrainingRepository(self.database,migrate=False).load_model_artifact(evidence.get("model_artifact_id"))
        model_input=SQLiteModelInputRepository(self.database,migrate=False).find_by_fingerprint(evidence.get("model_input_fingerprint",""))
        if artifact is None or model_input is None:raise ValueError("Persisted model artifact or input is unavailable.")
        quality=evidence.get("calibration_quality_report") or {};shift=quality.get("distribution_shift") or {}
        return self.create(artifact=artifact,model_input=model_input,analysis_id=analysis_id,observation_id=observation_id,selected_market=row[1] or evidence.get("mathematically_top_ranked_market"),market_evaluations=evidence.get("evaluations") or (),created_at_utc=created_at_utc,checked_at_utc=created_at_utc,calibration_artifact_id=evidence.get("calibration_set_id","UNKNOWN"),calibration_fingerprint=evidence.get("calibration_fingerprint","UNKNOWN"),calibration_quality_status=quality.get("lab_outcome","CALIBRATION_QUALITY_NOT_EVALUATED"),distribution_shift_status=shift.get("status","DISTRIBUTION_SHIFT_NOT_EVALUATED"),lineup_status=evidence.get("lineup_status","UNKNOWN"))

    def reproduce(self,reasoning_id:str,*,artifact,model_input,**context):
        existing=self.repository.load(reasoning_id)
        if existing is None:raise ValueError("Reasoning not found.")
        rebuilt=explain_prediction(artifact=artifact,model_input=model_input,**context)
        return {"status":"REASONING_REPRODUCED" if rebuilt.reasoning_fingerprint==existing.reasoning_fingerprint else "REASONING_REPRODUCTION_CONFLICT","reasoning_id":reasoning_id,"expected_fingerprint":existing.reasoning_fingerprint,"actual_fingerprint":rebuilt.reasoning_fingerprint,"matches":rebuilt.reasoning_fingerprint==existing.reasoning_fingerprint}

    def verify_stored_reproduction(self, reasoning_id: str) -> dict:
        """Recompute persisted class attribution from its immutable artifact/input."""
        existing = self.repository.load(reasoning_id)
        if existing is None: raise ValueError("Reasoning not found.")
        artifact = SQLiteHistoricalModelTrainingRepository(self.database,migrate=False).load_model_artifact(existing.model_artifact_id)
        model_input = SQLiteModelInputRepository(self.database,migrate=False).find_by_fingerprint(existing.model_input_fingerprint)
        if artifact is None or model_input is None:
            return {"status":"REASONING_REPRODUCTION_EVIDENCE_UNAVAILABLE","reasoning_id":reasoning_id,"matches":False,"artifact_available":artifact is not None,"model_input_available":model_input is not None}
        rebuilt = compute_class_attributions(artifact,model_input,source_timestamp_utc=model_input.created_timestamp.isoformat())
        expected = tuple(item.attribution_fingerprint for item in existing.class_attributions)
        actual = tuple(item.attribution_fingerprint for item in rebuilt)
        matches = expected == actual and all(item.score_reproduced and item.probability_reproduced for item in rebuilt)
        return {"status":"REASONING_REPRODUCED" if matches else "REASONING_REPRODUCTION_CONFLICT","reasoning_id":reasoning_id,"matches":matches,"class_count":len(rebuilt),"expected_attribution_fingerprints":expected,"actual_attribution_fingerprints":actual,"network_calls":0,"telegram_calls":0}
