"""SQLite append-only persistence for pipeline executions and stage events."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime

from app.database import Database, MigrationManager

from .exceptions import PipelineConflictError, PipelinePersistenceError
from .models import (
    OfficialPredictionPipelineOutcome,
    PipelineExecutionWithStages,
    PipelineStage,
    PipelineStageEvent,
    PipelineStatus,
)


class SQLiteOfficialPredictionPipelineRepository:
    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_pipeline_execution(self, execution, stage_events=()):
        if execution.pipeline_execution_id is None or execution.pipeline_fingerprint is None:
            raise PipelinePersistenceError("A terminal identified execution is required.")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self.find_by_request_identity(execution.pipeline_request_identity)
            if existing is not None:
                if existing == execution:
                    self._connection.commit()
                    return existing
                raise PipelineConflictError("Pipeline request identity conflicts.")
            self._insert_execution(execution)
            for event in stage_events:
                self._insert_stage(event)
            self._connection.commit()
        except PipelineConflictError:
            self._connection.rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._connection.rollback()
            raise PipelinePersistenceError("Pipeline execution transaction failed.") from exc
        stored = self.load_pipeline_execution(execution.pipeline_execution_id)
        if stored != execution:
            raise PipelinePersistenceError("Stored pipeline execution conflicts with input.")
        return stored

    def append_stage_events(self, events):
        if not events:
            return ()
        try:
            with self._connection:
                for event in events:
                    self._insert_stage(event)
        except sqlite3.DatabaseError as exc:
            raise PipelinePersistenceError("Pipeline stage events could not be stored.") from exc
        return events

    def find_by_pipeline_fingerprint(self, fingerprint):
        return self._one("pipeline_fingerprint = ?", (fingerprint,))

    def find_by_request_identity(self, identity):
        return self._one("pipeline_request_identity = ?", (identity,))

    def load_pipeline_execution(self, execution_id):
        return self._one("pipeline_execution_id = ?", (execution_id,))

    def load_execution_with_stages(self, execution_id):
        execution = self.load_pipeline_execution(execution_id)
        if execution is None:
            return None
        rows = self._connection.execute(
            "SELECT * FROM official_prediction_pipeline_stage_events WHERE pipeline_execution_id = ? ORDER BY stage_order, stage_event_id",
            (execution_id,),
        ).fetchall()
        return PipelineExecutionWithStages(execution, tuple(_stage(row) for row in rows))

    def list_executions_for_candidate(self, candidate_id):
        return self._many("candidate_id = ?", (candidate_id,))

    def list_executions_for_match(self, match_id):
        return self._many("match_id = ?", (match_id,))

    def list_published_executions(self):
        return self._many("final_pipeline_status = 'PUBLISHED'", ())

    def list_gate_rejected_executions(self):
        return self._many("final_pipeline_status IN ('NO_PUBLICATION_QUALITY_GATE_REJECTED','NO_PUBLICATION_REVIEW_REQUIRED')", ())

    def list_retry_required_executions(self):
        return self._many("final_pipeline_status = 'RETRY_REQUIRED'", ())

    def find_latest_for_candidate(self, candidate_id):
        values = self._many("candidate_id = ?", (candidate_id,), descending=True)
        return values[0] if values else None

    def _one(self, where, params):
        row = self._connection.execute(f"SELECT * FROM official_prediction_pipeline_executions WHERE {where} LIMIT 1", params).fetchone()
        return _execution(row) if row is not None else None

    def _many(self, where, params, descending=False):
        direction = "DESC" if descending else "ASC"
        rows = self._connection.execute(f"SELECT * FROM official_prediction_pipeline_executions WHERE {where} ORDER BY pipeline_execution_timestamp {direction}, pipeline_execution_id {direction}", params).fetchall()
        return tuple(_execution(row) for row in rows)

    def _insert_execution(self, value):
        self._connection.execute(
            """INSERT INTO official_prediction_pipeline_executions (
            pipeline_execution_id,pipeline_request_identity,request_fingerprint,pipeline_fingerprint,manual_run_identity,
            candidate_id,candidate_version,candidate_fingerprint,match_id,kickoff_timestamp,quality_gate_evaluation_timestamp,
            pipeline_execution_timestamp,publication_effective_timestamp,dry_run,retry,candidate_state_result,publication_state_result,
            quality_gate_evaluation_id,quality_gate_status,quality_gate_fingerprint,orchestration_id,orchestration_status,
            orchestration_fingerprint,publication_event_id,publication_status,publication_fingerprint,publication_claim_identity,
            message_fingerprint,telegram_message_reference,final_pipeline_status,pipeline_policy_version,ordered_reason_code_snapshot,
            explanation_snapshot,deterministic_execution_snapshot,created_timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value.pipeline_execution_id,value.pipeline_request_identity,value.request_fingerprint,value.pipeline_fingerprint,value.manual_run_identity,
             value.candidate_id,value.candidate_version,value.candidate_fingerprint,value.match_id,value.kickoff_timestamp.isoformat(),value.quality_gate_evaluation_timestamp.isoformat(),
             value.pipeline_execution_timestamp.isoformat(),_time(value.publication_effective_timestamp),int(value.dry_run),int(value.retry),value.candidate_state_result,value.publication_state_result,
             value.quality_gate_evaluation_id,value.quality_gate_status,value.quality_gate_fingerprint,value.orchestration_id,value.orchestration_status,value.orchestration_fingerprint,
             value.publication_event_id,value.publication_status,value.publication_fingerprint,value.publication_claim_identity,value.message_fingerprint,value.telegram_message_reference,
             value.final_status.value,value.pipeline_policy_version,_json(value.ordered_reason_codes),_json(value.explanations),_json(value.deterministic_execution_snapshot),value.pipeline_execution_timestamp.isoformat())
        )

    def _insert_stage(self, value):
        self._connection.execute("""INSERT INTO official_prediction_pipeline_stage_events (
            stage_event_id,pipeline_execution_id,stage_order,stage_name,stage_status,referenced_domain_record_id,
            referenced_fingerprint,ordered_reason_codes,deterministic_stage_snapshot,created_timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (value.stage_event_id,value.pipeline_execution_id,value.stage_order,value.stage_name.value,value.stage_status,value.referenced_domain_record_id,
             value.referenced_fingerprint,_json(value.ordered_reason_codes),_json(value.deterministic_stage_snapshot),value.created_timestamp.isoformat()))


def _execution(row):
    return OfficialPredictionPipelineOutcome(
        pipeline_execution_id=row["pipeline_execution_id"], pipeline_request_identity=row["pipeline_request_identity"], manual_run_identity=row["manual_run_identity"],
        candidate_id=row["candidate_id"], candidate_version=row["candidate_version"], candidate_fingerprint=row["candidate_fingerprint"], match_id=row["match_id"],
        kickoff_timestamp=datetime.fromisoformat(row["kickoff_timestamp"]), quality_gate_evaluation_id=row["quality_gate_evaluation_id"], quality_gate_status=row["quality_gate_status"],
        quality_gate_fingerprint=row["quality_gate_fingerprint"], orchestration_id=row["orchestration_id"], orchestration_status=row["orchestration_status"], orchestration_fingerprint=row["orchestration_fingerprint"],
        publication_event_id=row["publication_event_id"], publication_status=row["publication_status"], publication_fingerprint=row["publication_fingerprint"], publication_claim_identity=row["publication_claim_identity"],
        message_fingerprint=row["message_fingerprint"], telegram_message_reference=row["telegram_message_reference"], final_status=PipelineStatus(row["final_pipeline_status"]), dry_run=bool(row["dry_run"]), retry=bool(row["retry"]),
        ordered_reason_codes=tuple(json.loads(row["ordered_reason_code_snapshot"])), explanations=tuple(json.loads(row["explanation_snapshot"])), request_fingerprint=row["request_fingerprint"], pipeline_fingerprint=row["pipeline_fingerprint"],
        quality_gate_evaluation_timestamp=datetime.fromisoformat(row["quality_gate_evaluation_timestamp"]), pipeline_execution_timestamp=datetime.fromisoformat(row["pipeline_execution_timestamp"]),
        publication_effective_timestamp=_datetime(row["publication_effective_timestamp"]), pipeline_policy_version=row["pipeline_policy_version"], candidate_state_result=row["candidate_state_result"],
        publication_state_result=row["publication_state_result"], deterministic_execution_snapshot=tuple(tuple(item) for item in json.loads(row["deterministic_execution_snapshot"])),
    )


def _stage(row):
    return PipelineStageEvent(row["stage_event_id"],row["pipeline_execution_id"],row["stage_order"],PipelineStage(row["stage_name"]),row["stage_status"],row["referenced_domain_record_id"],row["referenced_fingerprint"],tuple(json.loads(row["ordered_reason_codes"])),tuple(tuple(item) for item in json.loads(row["deterministic_stage_snapshot"])),datetime.fromisoformat(row["created_timestamp"]))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _time(value):
    return value.isoformat() if value is not None else None


def _datetime(value):
    return datetime.fromisoformat(value) if value is not None else None
