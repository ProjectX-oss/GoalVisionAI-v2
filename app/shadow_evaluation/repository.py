"""Atomic append-only SQLite persistence for shadow evidence."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from app.database import Database, MigrationManager
from app.prediction_inference import PredictionTarget, RawProbability, RawProbabilitySet

from .exceptions import ShadowConflictError, ShadowPersistenceError
from .fingerprint import canonical_json
from .models import (
    DisagreementSeverity, DisagreementType, ModelRole, PreMatchOutcome,
    SettlementOutcome, ShadowAggregateSnapshot, ShadowComparison,
    ShadowEvaluationCommand, ShadowExecution, ShadowExclusion, ShadowInference,
    ShadowMarketAssessment, ShadowMetric, ShadowModelInputSnapshot,
    ShadowOddsSnapshot, ShadowOddsSnapshotSet, ShadowSelection, ShadowSettlement,
)


class SQLiteShadowEvaluationRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_shadow_evaluation(self, execution: ShadowExecution) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT request_fingerprint FROM shadow_evaluation_executions WHERE shadow_request_id=?",
                (execution.command.shadow_request_id,),
            ).fetchone()
            if row:
                if row[0] != execution.request_fingerprint:
                    raise ShadowConflictError("Shadow request ID has different immutable content.")
                self._connection.commit()
                return
            c = execution.command
            self._connection.execute(
                """INSERT INTO shadow_evaluation_executions
                (shadow_execution_id,shadow_request_id,request_fingerprint,execution_fingerprint,status,
                 comparison_run_id,challenger_candidate_id,champion_model_artifact_id,
                 challenger_model_artifact_id,match_id,competition,kickoff_utc,evaluation_timestamp_utc,
                 command_snapshot,deterministic_snapshot)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (execution.shadow_execution_id, c.shadow_request_id, execution.request_fingerprint,
                 execution.execution_fingerprint, "PRE_MATCH_EVALUATED", c.comparison_run_id,
                 c.challenger_candidate_id, c.champion_model_artifact_id,
                 c.challenger_model_artifact_id, c.match_id, c.competition, _text(c.kickoff_utc),
                 _text(c.evaluation_timestamp_utc), canonical_json(c), execution.deterministic_snapshot),
            )
            self._connection.execute(
                "INSERT INTO shadow_evaluation_input_snapshots VALUES (?,?,?,?,?,?,?)",
                (f"shadow-input-{execution.shadow_execution_id}", execution.input_snapshot.input_snapshot_fingerprint, execution.shadow_execution_id,
                 execution.input_snapshot.model_input_vector_id,
                 execution.input_snapshot.model_input_fingerprint,
                 execution.odds_snapshot_set.odds_snapshot_set_fingerprint,
                 canonical_json({"input": execution.input_snapshot, "odds": execution.odds_snapshot_set})),
            )
            for item in execution.inferences:
                self._connection.execute(
                    "INSERT INTO shadow_evaluation_inferences VALUES (?,?,?,?,?,?,?,?,?)",
                    (item.inference_id, execution.shadow_execution_id, item.model_role.value,
                     item.model_artifact_id, item.calibration_artifact_set_id,
                     item.raw_inference_fingerprint, item.calibrated_inference_fingerprint,
                     item.preprocessing_fingerprint, canonical_json(item)),
                )
            for item in execution.market_assessments:
                self._connection.execute(
                    "INSERT INTO shadow_evaluation_market_assessments VALUES (?,?,?,?,?,?,?,?,?)",
                    (item.assessment_id, execution.shadow_execution_id, item.model_role.value,
                     item.market_identity, item.odds_snapshot_id, int(item.eligible),
                     item.deterministic_rank, item.assessment_fingerprint, canonical_json(item)),
                )
            for item in execution.selections:
                self._connection.execute(
                    "INSERT INTO shadow_evaluation_selections VALUES (?,?,?,?,?,?,?)",
                    (item.selection_id, execution.shadow_execution_id, item.model_role.value,
                     item.market_identity, item.outcome.value, item.selection_fingerprint,
                     canonical_json(item)),
                )
            item = execution.comparison
            self._connection.execute(
                "INSERT INTO shadow_evaluation_comparisons VALUES (?,?,?,?,?,?)",
                (item.comparison_id, execution.shadow_execution_id, item.disagreement_type.value,
                 item.severity.value, item.comparison_fingerprint, canonical_json(item)),
            )
            self._insert_metrics(execution.shadow_execution_id, execution.metrics)
            self._insert_aggregates(execution.shadow_execution_id, execution.aggregate_snapshots)
            for item in execution.exclusions:
                self._connection.execute(
                    "INSERT INTO shadow_evaluation_exclusions VALUES (?,?,?,?,?,?)",
                    (item.exclusion_id, execution.shadow_execution_id, item.stage, item.reason,
                     item.deterministic_order, item.detail_snapshot),
                )
            self._connection.commit()
        except ShadowConflictError:
            self._rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise ShadowPersistenceError(f"Shadow evaluation transaction failed: {exc}") from exc

    def append_shadow_settlement(self, settlement, metrics=(), aggregate_snapshots=()) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT settlement_fingerprint FROM shadow_evaluation_settlements WHERE settlement_request_id=?",
                (settlement.settlement_request_id,),
            ).fetchone()
            prior = self._connection.execute(
                "SELECT settlement_fingerprint FROM shadow_evaluation_settlements WHERE shadow_execution_id=?",
                (settlement.shadow_execution_id,),
            ).fetchone()
            if existing or prior:
                fingerprint = (existing or prior)[0]
                if fingerprint != settlement.settlement_fingerprint:
                    raise ShadowConflictError("Shadow settlement conflicts with immutable prior evidence.")
                self._connection.commit()
                return
            self._connection.execute(
                "INSERT INTO shadow_evaluation_settlements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (settlement.settlement_id, settlement.settlement_request_id,
                 settlement.shadow_execution_id, settlement.champion_outcome.value,
                 settlement.challenger_outcome.value, str(settlement.champion_profit_per_unit),
                 str(settlement.challenger_profit_per_unit), settlement.final_home_score,
                 settlement.final_away_score, settlement.source_fingerprint,
                 settlement.settlement_timestamp_utc, settlement.settlement_fingerprint,
                 canonical_json(settlement)),
            )
            self._insert_metrics(settlement.shadow_execution_id, metrics)
            self._insert_aggregates(settlement.shadow_execution_id, aggregate_snapshots)
            self._connection.commit()
        except ShadowConflictError:
            self._rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise ShadowPersistenceError(f"Shadow settlement transaction failed: {exc}") from exc

    def find_by_shadow_execution_fingerprint(self, fingerprint):
        row = self._connection.execute(
            "SELECT shadow_execution_id FROM shadow_evaluation_executions WHERE execution_fingerprint=?", (fingerprint,),
        ).fetchone()
        return self.load_shadow_execution(row[0]) if row else None

    def find_by_request_id(self, request_id):
        row = self._connection.execute(
            "SELECT shadow_execution_id FROM shadow_evaluation_executions WHERE shadow_request_id=?", (request_id,),
        ).fetchone()
        return self.load_shadow_execution(row[0]) if row else None

    def load_shadow_execution(self, execution_id):
        row = self._connection.execute(
            "SELECT * FROM shadow_evaluation_executions WHERE shadow_execution_id=?", (execution_id,),
        ).fetchone()
        if row is None:
            return None
        command = _command(json.loads(row["command_snapshot"]))
        source = json.loads(self._connection.execute(
            "SELECT snapshot FROM shadow_evaluation_input_snapshots WHERE shadow_execution_id=?", (execution_id,),
        ).fetchone()[0])
        input_snapshot = _input(source["input"])
        odds_set = _odds_set(source["odds"])
        comparison = self.list_comparisons(execution_id)[0]
        return ShadowExecution(
            shadow_execution_id=execution_id, command=command,
            request_fingerprint=row["request_fingerprint"], input_snapshot=input_snapshot,
            odds_snapshot_set=odds_set, inferences=self.list_inferences(execution_id),
            market_assessments=self.list_market_assessments(execution_id),
            selections=self.list_selections(execution_id), comparison=comparison,
            metrics=self.list_metrics(execution_id),
            aggregate_snapshots=self.list_aggregate_snapshots(execution_id),
            exclusions=self.list_exclusions(execution_id),
            execution_fingerprint=row["execution_fingerprint"],
            deterministic_snapshot=row["deterministic_snapshot"],
        )

    def list_input_snapshots(self, execution_id):
        execution = self.load_shadow_execution(execution_id)
        return (execution.input_snapshot,) if execution else ()

    def list_inferences(self, execution_id):
        rows = self._snapshots("shadow_evaluation_inferences", execution_id, "CASE model_role WHEN 'CHAMPION' THEN 0 ELSE 1 END,inference_id")
        return tuple(_inference(item) for item in rows)

    def list_market_assessments(self, execution_id):
        rows = self._snapshots("shadow_evaluation_market_assessments", execution_id, "CASE model_role WHEN 'CHAMPION' THEN 0 ELSE 1 END,deterministic_rank")
        return tuple(_assessment(item) for item in rows)

    def list_selections(self, execution_id):
        rows = self._snapshots("shadow_evaluation_selections", execution_id, "CASE model_role WHEN 'CHAMPION' THEN 0 ELSE 1 END")
        return tuple(_selection(item) for item in rows)

    def list_comparisons(self, execution_id):
        rows = self._snapshots("shadow_evaluation_comparisons", execution_id, "comparison_id")
        return tuple(_comparison(item) for item in rows)

    def find_settlement_for_execution(self, execution_id):
        row = self._connection.execute(
            "SELECT snapshot FROM shadow_evaluation_settlements WHERE shadow_execution_id=?", (execution_id,),
        ).fetchone()
        return _settlement(json.loads(row[0])) if row else None

    def list_settlements(self, execution_id=None):
        query = "SELECT snapshot FROM shadow_evaluation_settlements"
        params = ()
        if execution_id is not None:
            query += " WHERE shadow_execution_id=?"; params = (execution_id,)
        query += " ORDER BY settlement_timestamp_utc,settlement_id"
        return tuple(_settlement(json.loads(row[0])) for row in self._connection.execute(query, params))

    def list_metrics(self, execution_id):
        rows = self._snapshots("shadow_evaluation_metrics", execution_id, "phase,category,grouping_identity,metric_name,metric_id")
        return tuple(_metric(item) for item in rows)

    def list_aggregate_snapshots(self, execution_id=None):
        query = "SELECT snapshot FROM shadow_evaluation_aggregate_snapshots"
        params = ()
        if execution_id is not None:
            query += " WHERE shadow_execution_id=?"; params = (execution_id,)
        query += " ORDER BY grouping_category,grouping_identity,aggregate_snapshot_id"
        return tuple(_aggregate(json.loads(row[0])) for row in self._connection.execute(query, params))

    def list_exclusions(self, execution_id):
        rows = self._connection.execute(
            "SELECT * FROM shadow_evaluation_exclusions WHERE shadow_execution_id=? ORDER BY deterministic_order", (execution_id,),
        )
        return tuple(ShadowExclusion(row["exclusion_id"], row["stage"], row["reason"], row["detail_snapshot"], row["deterministic_order"]) for row in rows)

    def list_executions_for_champion(self, artifact_id):
        return self._executions("champion_model_artifact_id", artifact_id)

    def list_executions_for_challenger(self, artifact_id):
        return self._executions("challenger_model_artifact_id", artifact_id)

    def list_executions_for_model_pair(self, champion_id, challenger_id):
        rows = self._connection.execute(
            "SELECT shadow_execution_id FROM shadow_evaluation_executions WHERE champion_model_artifact_id=? AND challenger_model_artifact_id=? ORDER BY evaluation_timestamp_utc,shadow_execution_id",
            (champion_id, challenger_id),
        )
        return tuple(self.load_shadow_execution(row[0]) for row in rows)

    def list_unsettled(self):
        rows = self._connection.execute(
            """SELECT e.shadow_execution_id FROM shadow_evaluation_executions e
               LEFT JOIN shadow_evaluation_settlements s ON s.shadow_execution_id=e.shadow_execution_id
               WHERE s.shadow_execution_id IS NULL ORDER BY e.kickoff_utc,e.shadow_execution_id"""
        )
        return tuple(self.load_shadow_execution(row[0]) for row in rows)

    def stream_shadow_events(self, execution_id):
        for event_type, table, identity, ordering in (
            ("INFERENCE", "shadow_evaluation_inferences", "inference_id", "model_role"),
            ("ASSESSMENT", "shadow_evaluation_market_assessments", "assessment_id", "model_role,deterministic_rank"),
            ("SELECTION", "shadow_evaluation_selections", "selection_id", "model_role"),
            ("COMPARISON", "shadow_evaluation_comparisons", "comparison_id", "comparison_id"),
            ("METRIC", "shadow_evaluation_metrics", "metric_id", "phase,metric_id"),
            ("EXCLUSION", "shadow_evaluation_exclusions", "exclusion_id", "deterministic_order"),
        ):
            for row in self._connection.execute(
                f"SELECT {identity} FROM {table} WHERE shadow_execution_id=? ORDER BY {ordering}", (execution_id,),
            ):
                yield event_type, row[0]

    def _insert_metrics(self, execution_id, metrics):
        for item in metrics:
            self._connection.execute(
                "INSERT INTO shadow_evaluation_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (item.metric_id, execution_id, item.phase,
                 item.model_role.value if item.model_role else None, item.category,
                 item.grouping_identity, item.metric_name,
                 str(item.metric_value) if item.metric_value is not None else None,
                 item.metric_fingerprint, item.metric_snapshot, canonical_json(item)),
            )

    def _insert_aggregates(self, execution_id, aggregates):
        for item in aggregates:
            self._connection.execute(
                "INSERT INTO shadow_evaluation_aggregate_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                (item.aggregate_snapshot_id, execution_id, item.grouping_category,
                 item.grouping_identity, item.sample_count, item.settled_count,
                 item.aggregate_fingerprint, item.metric_snapshot, canonical_json(item)),
            )

    def _snapshots(self, table, execution_id, ordering):
        return tuple(json.loads(row[0]) for row in self._connection.execute(
            f"SELECT snapshot FROM {table} WHERE shadow_execution_id=? ORDER BY {ordering}", (execution_id,),
        ))

    def _executions(self, column, value):
        rows = self._connection.execute(
            f"SELECT shadow_execution_id FROM shadow_evaluation_executions WHERE {column}=? ORDER BY evaluation_timestamp_utc,shadow_execution_id", (value,),
        )
        return tuple(self.load_shadow_execution(row[0]) for row in rows)

    def _rollback(self):
        if self._connection.in_transaction:
            self._connection.rollback()


def _text(value):
    return value if isinstance(value, str) else value.isoformat().replace("+00:00", "Z")


def _command(d): return ShadowEvaluationCommand(**d)
def _input(d):
    return ShadowModelInputSnapshot(
        **{**d, "ordered_feature_values": tuple(Decimal(x) if x is not None else None for x in d["ordered_feature_values"]),
           "ordered_feature_names": tuple(d["ordered_feature_names"]), "missingness_mask": tuple(d["missingness_mask"]),
           "ordered_missing_features": tuple(d["ordered_missing_features"]), "completeness_score": Decimal(d["completeness_score"]),
           "ordered_source_timestamps": tuple(d["ordered_source_timestamps"])}
    )
def _odds_set(d):
    return ShadowOddsSnapshotSet(d["odds_snapshot_set_id"], d["odds_snapshot_set_fingerprint"], tuple(
        ShadowOddsSnapshot(**{**item, "decimal_odds": Decimal(item["decimal_odds"])}) for item in d["snapshots"]
    ))
def _probs(rows):
    return RawProbabilitySet(tuple(RawProbability(PredictionTarget(item["target"]), Decimal(item["probability"])) for item in rows["ordered_probabilities"]))
def _inference(d):
    return ShadowInference(**{**d, "model_role": ModelRole(d["model_role"]), "raw_probabilities": _probs(d["raw_probabilities"]), "calibrated_probabilities": _probs(d["calibrated_probabilities"])})
def _assessment(d):
    for key in ("calibrated_probability", "fair_odds", "decimal_odds", "implied_probability", "edge", "expected_value", "expected_profit_per_unit"):
        d[key] = Decimal(d[key]) if d[key] is not None else None
    return ShadowMarketAssessment(**{**d, "model_role": ModelRole(d["model_role"]), "rejection_reasons": tuple(d["rejection_reasons"])})
def _selection(d):
    for key in ("probability", "decimal_odds", "expected_value"):
        d[key] = Decimal(d[key]) if d[key] is not None else None
    return ShadowSelection(**{**d, "model_role": ModelRole(d["model_role"]), "outcome": PreMatchOutcome(d["outcome"]), "reason_codes": tuple(d["reason_codes"])})
def _comparison(d):
    decimal_keys = ("maximum_probability_delta", "mean_probability_delta", "result_distribution_delta", "totals_delta", "btts_delta", "fair_odds_delta", "expected_value_delta", "confidence_delta")
    for key in decimal_keys:
        d[key] = Decimal(d[key]) if d[key] is not None else None
    return ShadowComparison(**{**d, "disagreement_type": DisagreementType(d["disagreement_type"]), "severity": DisagreementSeverity(d["severity"]), "target_probability_deltas": tuple((x[0], Decimal(x[1])) for x in d["target_probability_deltas"]), "reason_codes": tuple(d["reason_codes"])})
def _metric(d):
    return ShadowMetric(**{**d, "model_role": ModelRole(d["model_role"]) if d["model_role"] else None, "metric_value": Decimal(d["metric_value"]) if d["metric_value"] is not None else None})
def _aggregate(d): return ShadowAggregateSnapshot(**d)
def _settlement(d):
    return ShadowSettlement(**{**d, "champion_outcome": SettlementOutcome(d["champion_outcome"]), "challenger_outcome": SettlementOutcome(d["challenger_outcome"]), "champion_profit_per_unit": Decimal(d["champion_profit_per_unit"]), "challenger_profit_per_unit": Decimal(d["challenger_profit_per_unit"])})
