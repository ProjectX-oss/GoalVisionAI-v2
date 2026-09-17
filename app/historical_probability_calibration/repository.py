"""Atomic append-only SQLite historical calibration repository."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from app.database import Database, MigrationManager
from app.historical_dataset_split import Partition
from app.prediction_inference import PredictionTarget, RawProbability, RawProbabilitySet

from .exceptions import CalibrationConflictError, CalibrationPersistenceError
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    CalibrationArtifactSet, CalibrationMetric, NormalizedCalibrationCommand,
    PreparedCalibrationRun, ReliabilityBin, TargetCalibrationArtifact,
    ValidationPrediction,
)
from .policy import CalibrationMethod, TargetMethodOverride


class SQLiteHistoricalProbabilityCalibrationRepository:
    def __init__(self, database: Database, *, migrate: bool = True):
        self._connection = database.connection
        if migrate: MigrationManager(self._connection).migrate()

    def append_calibration_run(self, run: PreparedCalibrationRun):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT request_fingerprint FROM historical_probability_calibration_runs WHERE calibration_request_id=?",
                (run.command.calibration_request_id,),
            ).fetchone()
            if existing:
                if existing[0] != run.request_fingerprint:
                    raise CalibrationConflictError("Calibration request ID has different immutable content.")
                self._connection.commit(); return
            self._insert_run(run); self._insert_set(run); self._insert_targets(run)
            self._insert_predictions(run); self._insert_metrics(run); self._insert_bins(run)
            self._connection.commit()
        except CalibrationConflictError:
            _rollback(self._connection); raise
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise CalibrationPersistenceError(f"Historical calibration transaction failed: {exc}") from exc

    def find_by_calibration_run_fingerprint(self, fingerprint):
        row = self._connection.execute("SELECT calibration_run_id FROM historical_probability_calibration_runs WHERE calibration_run_fingerprint=?", (fingerprint,)).fetchone()
        return self.load_calibration_run(row[0]) if row else None

    def find_by_request_id(self, request_id):
        row = self._connection.execute("SELECT calibration_run_id FROM historical_probability_calibration_runs WHERE calibration_request_id=?", (request_id,)).fetchone()
        return self.load_calibration_run(row[0]) if row else None

    def load_calibration_run(self, calibration_run_id):
        row = self._connection.execute("SELECT * FROM historical_probability_calibration_runs WHERE calibration_run_id=?", (calibration_run_id,)).fetchone()
        if row is None: return None
        snapshot = json.loads(row["deterministic_run_snapshot"])
        command = _command(snapshot["command"])
        set_row = self._connection.execute("SELECT artifact_set_id FROM historical_probability_calibration_artifact_sets WHERE calibration_run_id=?", (calibration_run_id,)).fetchone()
        return PreparedCalibrationRun(
            calibration_run_id=calibration_run_id, command=command,
            request_fingerprint=row["request_fingerprint"], calibration_run_fingerprint=row["calibration_run_fingerprint"],
            artifact_set=self.load_calibration_artifact_set(set_row[0]),
            predictions=self.list_validation_predictions(calibration_run_id),
            metrics=self.list_calibration_metrics(calibration_run_id),
            reliability_bins=self.list_reliability_bins(calibration_run_id),
            aggregate_raw_metrics=tuple((name, Decimal(value)) for name, value in snapshot["aggregate_raw_metrics"]),
            aggregate_calibrated_metrics=tuple((name, Decimal(value)) for name, value in snapshot["aggregate_calibrated_metrics"]),
            monotonicity_summary=tuple((name, int(value) if name.endswith("count") else Decimal(value)) for name, value in snapshot["monotonicity_summary"]),
            reconciliation_summary=tuple((name, int(value) if name.endswith("count") else Decimal(value)) for name, value in snapshot["reconciliation_summary"]),
            deterministic_run_snapshot=row["deterministic_run_snapshot"],
        )

    def load_calibration_artifact_set(self, artifact_set_id):
        row = self._connection.execute("SELECT * FROM historical_probability_calibration_artifact_sets WHERE artifact_set_id=?", (artifact_set_id,)).fetchone()
        if row is None: return None
        run_row = self._connection.execute("SELECT * FROM historical_probability_calibration_runs WHERE calibration_run_id=?", (row["calibration_run_id"],)).fetchone()
        command = _command(json.loads(run_row["deterministic_run_snapshot"])["command"])
        compatibility = json.loads(row["compatibility_snapshot"])
        return CalibrationArtifactSet(
            artifact_set_id=artifact_set_id, artifact_set_fingerprint=row["artifact_set_fingerprint"],
            calibration_run_id=row["calibration_run_id"], request_fingerprint=run_row["request_fingerprint"],
            command=command, target_artifacts=self.list_target_calibration_artifacts(artifact_set_id),
            reconciliation_fingerprint=compatibility["reconciliation_fingerprint"],
            monotonicity_fingerprint=compatibility["monotonicity_fingerprint"],
            compatibility_snapshot=row["compatibility_snapshot"], provenance_snapshot=row["provenance_snapshot"],
        )

    def load_target_calibration_artifact(self, artifact_set_id, target_identity):
        row = self._connection.execute("SELECT * FROM historical_probability_calibration_targets WHERE artifact_set_id=? AND target_identity=?", (artifact_set_id, target_identity)).fetchone()
        return _target(row) if row else None

    def list_target_calibration_artifacts(self, artifact_set_id):
        rows = self._connection.execute("SELECT * FROM historical_probability_calibration_targets WHERE artifact_set_id=? ORDER BY target_order", (artifact_set_id,)).fetchall()
        return tuple(_target(row) for row in rows)

    def list_validation_predictions(self, calibration_run_id):
        run = self._connection.execute("SELECT * FROM historical_probability_calibration_runs WHERE calibration_run_id=?", (calibration_run_id,)).fetchone()
        if run is None: return ()
        rows = self._connection.execute("SELECT * FROM historical_probability_calibration_predictions WHERE calibration_run_id=? ORDER BY deterministic_order", (calibration_run_id,)).fetchall()
        return tuple(_prediction(row, run) for row in rows)

    def list_calibration_metrics(self, calibration_run_id):
        rows = self._connection.execute("SELECT * FROM historical_probability_calibration_metrics WHERE calibration_run_id=? ORDER BY deterministic_order", (calibration_run_id,)).fetchall()
        return tuple(CalibrationMetric(
            target_identity=row["target_identity"], metric_phase=row["metric_phase"], metric_name=row["metric_name"],
            metric_value=Decimal(row["metric_value"]) if row["metric_value"] is not None else None,
            metric_snapshot=row["metric_snapshot"], deterministic_order=row["deterministic_order"],
        ) for row in rows)

    def list_reliability_bins(self, calibration_run_id, target_identity=None):
        query = "SELECT * FROM historical_probability_calibration_reliability_bins WHERE calibration_run_id=?"
        params = [calibration_run_id]
        if target_identity is not None: query += " AND target_identity=?"; params.append(target_identity)
        query += " ORDER BY target_identity,metric_phase,bin_index"
        rows = self._connection.execute(query, tuple(params)).fetchall()
        return tuple(ReliabilityBin(
            target_identity=row["target_identity"], metric_phase=row["metric_phase"], bin_index=row["bin_index"],
            lower_bound=Decimal(row["lower_bound"]), upper_bound=Decimal(row["upper_bound"]), sample_count=row["sample_count"],
            mean_predicted_probability=Decimal(row["mean_predicted_probability"]) if row["mean_predicted_probability"] is not None else None,
            observed_frequency=Decimal(row["observed_frequency"]) if row["observed_frequency"] is not None else None,
            absolute_gap=Decimal(row["absolute_gap"]) if row["absolute_gap"] is not None else None,
            bin_fingerprint=row["bin_fingerprint"],
        ) for row in rows)

    def list_calibration_runs_for_artifact(self, artifact_id):
        rows = self._connection.execute("SELECT calibration_run_id FROM historical_probability_calibration_runs WHERE source_artifact_id=? ORDER BY calibration_timestamp,calibration_run_id", (artifact_id,)).fetchall()
        return tuple(self.load_calibration_run(row[0]) for row in rows)

    def stream_calibrated_predictions(self, calibration_run_id):
        run = self._connection.execute(
            "SELECT * FROM historical_probability_calibration_runs WHERE calibration_run_id=?",
            (calibration_run_id,),
        ).fetchone()
        if run is None:
            return
        cursor = self._connection.execute("SELECT * FROM historical_probability_calibration_predictions WHERE calibration_run_id=? ORDER BY deterministic_order", (calibration_run_id,))
        while True:
            rows = cursor.fetchmany(100)
            if not rows: return
            for row in rows:
                yield _prediction(row, run)

    def _insert_run(self, run):
        c = run.command
        self._connection.execute("""INSERT INTO historical_probability_calibration_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            run.calibration_run_id, c.calibration_request_id, run.request_fingerprint, run.calibration_run_fingerprint,
            c.source_training_run_id, c.source_training_run_fingerprint, c.source_model_artifact_id, c.source_model_artifact_fingerprint,
            c.source_split_id, c.source_split_fingerprint, c.fold_id, c.fold_fingerprint, len(run.predictions), 7, 4,
            canonical_json((c.calibration_policy_version, c.runtime_compatibility_version)), "CALIBRATION_FITTED",
            canonical_json(("CALIBRATION_ARTIFACT_SET_PERSISTED",)), canonical_json(run.aggregate_raw_metrics),
            canonical_json(run.aggregate_calibrated_metrics), canonical_json(run.monotonicity_summary),
            canonical_json(run.reconciliation_summary), run.deterministic_run_snapshot, c.calibration_timestamp, c.calibration_timestamp,
        ))

    def _insert_set(self, run):
        a, c = run.artifact_set, run.command
        compatibility = json.loads(a.compatibility_snapshot)
        compatibility["reconciliation_fingerprint"] = a.reconciliation_fingerprint
        compatibility["monotonicity_fingerprint"] = a.monotonicity_fingerprint
        self._connection.execute("""INSERT INTO historical_probability_calibration_artifact_sets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            a.artifact_set_id, run.calibration_run_id, a.artifact_set_fingerprint, c.artifact_format_version,
            c.runtime_compatibility_version, c.target_schema_version,
            canonical_json(tuple(item.value for item in __import__("app.prediction_inference", fromlist=["OFFICIAL_TARGET_ORDER"]).OFFICIAL_TARGET_ORDER)),
            canonical_json({"version": c.clamp_policy_version}), canonical_json({"version": c.monotonicity_policy_version, "fingerprint": a.monotonicity_fingerprint}),
            canonical_json({"version": c.reconciliation_policy_version, "fingerprint": a.reconciliation_fingerprint}),
            canonical_json(compatibility), a.provenance_snapshot, c.calibration_timestamp,
        ))

    def _insert_targets(self, run):
        for item in run.artifact_set.target_artifacts:
            identity = sha256_fingerprint((run.artifact_set.artifact_set_id, item.target_identity))
            self._connection.execute("INSERT INTO historical_probability_calibration_targets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                f"historical-calibration-target-{identity}", run.artifact_set.artifact_set_id, item.target_identity,
                item.target_order, item.method.value, item.target_artifact_fingerprint, item.fitted_parameters_snapshot,
                canonical_json(item.class_order), item.support_snapshot, item.convergence_snapshot,
                item.derivation_snapshot, run.command.calibration_timestamp,
            ))

    def _insert_predictions(self, run):
        for item in run.predictions:
            identity = sha256_fingerprint((run.calibration_run_id, item.training_example_id))
            self._connection.execute("INSERT INTO historical_probability_calibration_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                f"historical-calibration-prediction-{identity}", run.calibration_run_id, item.training_example_id,
                item.example_fingerprint, item.raw_prediction_fingerprint, _probability_snapshot(item.raw_probabilities),
                _probability_snapshot(item.calibrated_probabilities), item.monotonicity_adjustment_snapshot,
                item.reconciliation_snapshot, item.deterministic_order, run.command.calibration_timestamp,
            ))

    def _insert_metrics(self, run):
        for item in run.metrics:
            identity = sha256_fingerprint((run.calibration_run_id, item.deterministic_order))
            self._connection.execute("INSERT INTO historical_probability_calibration_metrics VALUES (?,?,?,?,?,?,?,?,?)", (
                f"historical-calibration-metric-{identity}", run.calibration_run_id, item.target_identity,
                item.metric_phase, item.metric_name, str(item.metric_value) if item.metric_value is not None else None,
                item.metric_snapshot, item.deterministic_order, run.command.calibration_timestamp,
            ))

    def _insert_bins(self, run):
        for item in run.reliability_bins:
            identity = sha256_fingerprint((run.calibration_run_id, item.target_identity, item.metric_phase, item.bin_index))
            self._connection.execute("INSERT INTO historical_probability_calibration_reliability_bins VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                f"historical-calibration-bin-{identity}", run.calibration_run_id, item.target_identity,
                item.metric_phase, item.bin_index, str(item.lower_bound), str(item.upper_bound), item.sample_count,
                str(item.mean_predicted_probability) if item.mean_predicted_probability is not None else None,
                str(item.observed_frequency) if item.observed_frequency is not None else None,
                str(item.absolute_gap) if item.absolute_gap is not None else None,
                item.bin_fingerprint, run.command.calibration_timestamp,
            ))


def _command(value):
    return NormalizedCalibrationCommand(
        **{key: item for key, item in value.items() if key not in {"calibration_partition", "match_result_method", "totals_method", "btts_method", "target_method_overrides"}},
        calibration_partition=Partition(value["calibration_partition"]),
        match_result_method=CalibrationMethod(value["match_result_method"]), totals_method=CalibrationMethod(value["totals_method"]),
        btts_method=CalibrationMethod(value["btts_method"]),
        target_method_overrides=tuple(TargetMethodOverride(item["target_identity"], CalibrationMethod(item["method"])) for item in value["target_method_overrides"]),
    )


def _target(row):
    return TargetCalibrationArtifact(
        target_identity=row["target_identity"], target_order=row["target_order"], method=CalibrationMethod(row["calibration_method"]),
        target_artifact_fingerprint=row["target_artifact_fingerprint"], fitted_parameters_snapshot=row["fitted_parameters_snapshot"],
        class_order=tuple(json.loads(row["class_order_snapshot"])), support_snapshot=row["support_snapshot"],
        convergence_snapshot=row["convergence_snapshot"], derivation_snapshot=row["derivation_snapshot"],
    )


def _probability_snapshot(value):
    return canonical_json(tuple((item.target.value, item.probability) for item in value.ordered_probabilities))


def _probabilities(snapshot):
    return RawProbabilitySet(tuple(RawProbability(PredictionTarget(target), Decimal(value)) for target, value in json.loads(snapshot)))


def _prediction(row, run):
    return ValidationPrediction(
        training_example_id=row["training_example_id"], example_fingerprint=row["example_fingerprint"],
        artifact_id=run["source_artifact_id"], artifact_fingerprint=run["source_artifact_fingerprint"],
        training_run_id=run["source_training_run_id"], split_id=run["source_split_id"], fold_id=run["fold_id"],
        partition=Partition.VALIDATION, raw_probabilities=_probabilities(row["raw_probabilities_snapshot"]),
        calibrated_probabilities=_probabilities(row["calibrated_probabilities_snapshot"]),
        raw_prediction_fingerprint=row["raw_prediction_fingerprint"],
        monotonicity_adjustment_snapshot=row["monotonicity_adjustment_snapshot"],
        reconciliation_snapshot=row["reconciliation_snapshot"], deterministic_order=row["deterministic_order"],
    )


def _rollback(connection):
    if connection.in_transaction: connection.rollback()
