import hashlib
import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from app.database import Database, MigrationManager
from app.match_data_snapshot import canonical_json
from app.prediction_inference import PredictionTarget
from app.probability_calibration import CalibrationMethod

from .exceptions import CalibratedAssemblyConflictError, CalibratedAssemblyPersistenceError
from .models import (
    CalibratedMarketProbabilityAssembly, CalibratedTargetResult,
    CalibratedValidationCheck, CalibratedValidationSummary,
    CalibrationSetDefinition, CalibrationTargetMapping,
)


class SQLiteCalibratedMarketProbabilityRepository:
    """Append-only calibration-set and calibrated-assembly storage."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self.connection = database.connection
        if migrate:
            MigrationManager(self.connection).migrate()

    def append_calibration_set(self, value: CalibrationSetDefinition) -> tuple[CalibrationSetDefinition, bool]:
        try:
            existing = self.find_calibration_set_by_fingerprint(value.calibration_set_fingerprint)
            if existing:
                return existing, True
            with self.connection:
                self.connection.execute(
                    """INSERT INTO probability_calibration_sets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (value.calibration_set_id, value.set_name, value.set_version,
                     value.source_model_artifact_id, canonical_json(value.compatible_source_model_versions),
                     canonical_json(tuple((x.target.value, x.calibration_artifact_id) for x in value.ordered_target_mappings)),
                     value.calibration_set_fingerprint, value.policy_version, int(value.active),
                     value.effective_timestamp.isoformat(), value.created_timestamp.isoformat()),
                )
            return value, False
        except sqlite3.IntegrityError as exc:
            existing = self.find_calibration_set_by_fingerprint(value.calibration_set_fingerprint)
            if existing:
                return existing, True
            raise CalibratedAssemblyConflictError("Calibration set conflicts with immutable history.") from exc
        except sqlite3.DatabaseError as exc:
            raise CalibratedAssemblyPersistenceError("Calibration set append failed.") from exc

    def find_calibration_set_by_id(self, calibration_set_id: str) -> CalibrationSetDefinition | None:
        return self._set_one("calibration_set_id = ?", (calibration_set_id,))

    def find_calibration_set_by_fingerprint(self, fingerprint: str) -> CalibrationSetDefinition | None:
        return self._set_one("calibration_set_fingerprint = ?", (fingerprint,))

    def find_active_compatible_set(self, model_artifact_id: str, model_version: str) -> CalibrationSetDefinition | None:
        values = self.list_calibration_sets_for_model(model_artifact_id)
        compatible = tuple(x for x in values if x.active and model_version in x.compatible_source_model_versions)
        if len(compatible) > 1:
            raise CalibratedAssemblyConflictError("Multiple active compatible calibration sets exist.")
        return compatible[0] if compatible else None

    def list_calibration_sets_for_model(self, model_artifact_id: str) -> tuple[CalibrationSetDefinition, ...]:
        try:
            rows = self.connection.execute(
                "SELECT * FROM probability_calibration_sets WHERE source_model_artifact_id=? ORDER BY effective_timestamp, calibration_set_id",
                (model_artifact_id,),
            ).fetchall()
            return tuple(_set_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise CalibratedAssemblyPersistenceError("Calibration set lookup failed.") from exc

    def append_calibrated_assembly(self, value: CalibratedMarketProbabilityAssembly) -> tuple[CalibratedMarketProbabilityAssembly, bool]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self._assembly_by_fingerprint(value.calibrated_assembly_fingerprint)
            if existing:
                self.connection.commit()
                return existing, True
            self.connection.execute(
                """INSERT INTO calibrated_market_probability_assemblies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (value.calibrated_assembly_id, value.inference_id, value.model_input_id,
                 value.match_id, value.source_snapshot_id, value.source_feature_set_id,
                 value.source_model_artifact_id, value.source_model_name, value.source_model_version,
                 value.raw_inference_fingerprint, value.calibration_set_id,
                 value.calibration_set_fingerprint, value.assembly_policy_version,
                 value.calibrated_assembly_fingerprint, _validation_json(value.validation_summary),
                 value.calibration_effective_timestamp.isoformat(), value.created_timestamp.isoformat()),
            )
            for index, item in enumerate(value.ordered_target_results):
                target_id = "calibrated-target-" + hashlib.sha256((value.calibrated_assembly_id + "|" + item.target.value).encode()).hexdigest()
                self.connection.execute(
                    """INSERT INTO calibrated_market_probability_targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (target_id, value.calibrated_assembly_id, index, item.target.value,
                     _decimal(item.raw_probability), _decimal(item.calibrated_probability),
                     item.calibration_artifact_id, item.calibration_method.value,
                     item.calibration_model_version, item.calibration_policy_version,
                     item.calibration_report_fingerprint, item.quality_metadata_reference,
                     None if item.clamping_indicator is None else int(item.clamping_indicator),
                     canonical_json(item.diagnostics), item.target_result_fingerprint,
                     value.created_timestamp.isoformat()),
                )
            self.connection.commit()
            return value, False
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            existing = self._assembly_by_fingerprint(value.calibrated_assembly_fingerprint)
            if existing:
                return existing, True
            raise CalibratedAssemblyConflictError("Calibrated assembly conflicts with immutable history.") from exc
        except sqlite3.DatabaseError as exc:
            self.connection.rollback()
            raise CalibratedAssemblyPersistenceError("Calibrated assembly append failed.") from exc

    def find_by_assembly_fingerprint(self, fingerprint: str) -> CalibratedMarketProbabilityAssembly | None:
        try:
            return self._assembly_by_fingerprint(fingerprint)
        except sqlite3.DatabaseError as exc:
            raise CalibratedAssemblyPersistenceError("Assembly fingerprint lookup failed.") from exc

    def load_assembly_by_id(self, assembly_id: str) -> CalibratedMarketProbabilityAssembly | None:
        return self._assembly_one("calibrated_assembly_id = ?", (assembly_id,))

    def find_for_inference_and_calibration_set(self, inference_id: str, calibration_set_fingerprint: str) -> CalibratedMarketProbabilityAssembly | None:
        return self._assembly_one("inference_id = ? AND calibration_set_fingerprint = ?", (inference_id, calibration_set_fingerprint), descending=True)

    def find_latest_for_match_and_model(self, match_id: str, model_artifact_id: str) -> CalibratedMarketProbabilityAssembly | None:
        return self._assembly_one("match_id = ? AND source_model_artifact_id = ?", (match_id, model_artifact_id), descending=True)

    def list_assemblies_for_inference(self, inference_id: str) -> tuple[CalibratedMarketProbabilityAssembly, ...]:
        try:
            rows = self.connection.execute(
                "SELECT * FROM calibrated_market_probability_assemblies WHERE inference_id=? ORDER BY calibration_effective_timestamp, calibrated_assembly_id", (inference_id,)
            ).fetchall()
            return tuple(self._aggregate(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise CalibratedAssemblyPersistenceError("Assembly history lookup failed.") from exc

    def _set_one(self, where: str, params: tuple) -> CalibrationSetDefinition | None:
        try:
            row = self.connection.execute(f"SELECT * FROM probability_calibration_sets WHERE {where}", params).fetchone()
            return _set_from_row(row) if row else None
        except sqlite3.DatabaseError as exc:
            raise CalibratedAssemblyPersistenceError("Calibration set lookup failed.") from exc

    def _assembly_by_fingerprint(self, value: str) -> CalibratedMarketProbabilityAssembly | None:
        return self._assembly_one("calibrated_assembly_fingerprint = ?", (value,))

    def _assembly_one(self, where: str, params: tuple, descending: bool = False) -> CalibratedMarketProbabilityAssembly | None:
        try:
            order = " ORDER BY calibration_effective_timestamp DESC, calibrated_assembly_id DESC" if descending else ""
            row = self.connection.execute(f"SELECT * FROM calibrated_market_probability_assemblies WHERE {where}{order} LIMIT 1", params).fetchone()
            return self._aggregate(row) if row else None
        except sqlite3.DatabaseError as exc:
            raise CalibratedAssemblyPersistenceError("Calibrated assembly lookup failed.") from exc

    def _aggregate(self, row: sqlite3.Row) -> CalibratedMarketProbabilityAssembly:
        target_rows = self.connection.execute(
            "SELECT * FROM calibrated_market_probability_targets WHERE calibrated_assembly_id=? ORDER BY target_order", (row["calibrated_assembly_id"],)
        ).fetchall()
        targets = tuple(_target_from_row(item) for item in target_rows)
        raw = json.loads(row["validation_snapshot"])
        summary = CalibratedValidationSummary(raw["policy_version"], raw["target_count"], tuple(
            CalibratedValidationCheck(x["code"], bool(x["passed"]), Decimal(x["observed_value"]), Decimal(x["tolerance"])) for x in raw["ordered_checks"]
        ))
        return CalibratedMarketProbabilityAssembly(
            row["calibrated_assembly_id"], row["inference_id"], row["model_input_id"], row["match_id"],
            row["snapshot_id"], row["feature_set_id"], row["source_model_artifact_id"],
            row["source_model_name"], row["source_model_version"], row["raw_inference_fingerprint"],
            row["calibration_set_id"], row["calibration_set_fingerprint"], row["assembly_policy_version"],
            datetime.fromisoformat(row["calibration_effective_timestamp"]), datetime.fromisoformat(row["created_timestamp"]),
            targets, summary, row["calibrated_assembly_fingerprint"],
        )


def _set_from_row(row: sqlite3.Row) -> CalibrationSetDefinition:
    mappings = tuple(CalibrationTargetMapping(PredictionTarget(x[0]), x[1]) for x in json.loads(row["target_mapping_snapshot"]))
    return CalibrationSetDefinition(
        row["calibration_set_id"], row["set_name"], row["set_version"], row["source_model_artifact_id"],
        tuple(json.loads(row["source_model_versions"])), mappings, row["policy_version"], bool(row["active"]),
        datetime.fromisoformat(row["created_timestamp"]), datetime.fromisoformat(row["effective_timestamp"]),
        row["calibration_set_fingerprint"],
    )


def _target_from_row(row: sqlite3.Row) -> CalibratedTargetResult:
    clamp = row["clamping_indicator"]
    return CalibratedTargetResult(
        PredictionTarget(row["target"]), Decimal(row["raw_probability"]), Decimal(row["calibrated_probability"]),
        row["calibration_artifact_id"], CalibrationMethod(row["calibration_method"]), row["calibration_model_version"],
        row["calibration_policy_version"], row["calibration_report_fingerprint"], row["quality_metadata_reference"],
        None if clamp is None else bool(clamp), tuple(json.loads(row["diagnostics_snapshot"])), row["target_result_fingerprint"],
    )


def _validation_json(value: CalibratedValidationSummary) -> str:
    return canonical_json({"policy_version": value.policy_version, "target_count": value.target_count,
        "ordered_checks": tuple({"code": x.code, "passed": x.passed, "observed_value": _decimal(x.observed_value), "tolerance": _decimal(x.tolerance)} for x in value.ordered_checks)})


def _decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")
