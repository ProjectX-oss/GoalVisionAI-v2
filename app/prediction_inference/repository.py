import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Callable, TypeVar

from app.database import Database, MigrationManager
from app.match_data_snapshot import canonical_json

from .exceptions import InferenceConflictError, InferencePersistenceError
from .models import (
    InferenceValidationSummary,
    PersistedModelInputIdentity,
    PredictionInferenceResult,
    PredictionTarget,
    ProbabilityValidationCheck,
    RawProbability,
    RawProbabilitySet,
)


_T = TypeVar("_T")


class SQLitePredictionInferenceRepository:
    """Append-only raw inference storage and read-only model-input provenance."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def load_model_input_identity(self, model_input_id: str) -> PersistedModelInputIdentity | None:
        try:
            row = self._connection.execute(
                """
                SELECT model_input_id, feature_set_id, snapshot_id, match_id,
                       schema_name, schema_version, compatibility_version,
                       feature_fingerprint, source_snapshot_fingerprint,
                       source_feature_fingerprint,
                       model_input_fingerprint, created_timestamp
                FROM model_input_vectors WHERE model_input_id = ?
                """,
                (model_input_id,),
            ).fetchone()
            if row is None:
                return None
            return PersistedModelInputIdentity(
                model_input_id=row["model_input_id"],
                feature_set_id=row["feature_set_id"],
                snapshot_id=row["snapshot_id"],
                match_id=row["match_id"],
                schema_name=row["schema_name"],
                schema_version=row["schema_version"],
                compatibility_version=row["compatibility_version"],
                feature_fingerprint=row["feature_fingerprint"],
                source_snapshot_fingerprint=row["source_snapshot_fingerprint"],
                source_feature_fingerprint=row["source_feature_fingerprint"],
                model_input_fingerprint=row["model_input_fingerprint"],
                effective_timestamp=datetime.fromisoformat(row["created_timestamp"]),
            )
        except sqlite3.DatabaseError as exc:
            raise InferencePersistenceError("Model-input identity lookup failed.") from exc

    def append_inference_result(self, result: PredictionInferenceResult) -> tuple[PredictionInferenceResult, bool]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._by_fingerprint(result.inference_fingerprint)
            if existing is not None:
                self._connection.commit()
                return existing, True
            by_id = self._by_id(result.inference_id)
            if by_id is not None:
                raise InferenceConflictError("Inference ID already identifies different immutable content.")
            self._connection.execute(
                """
                INSERT INTO prediction_inference_results (
                    inference_id, model_input_id, match_id, snapshot_id,
                    feature_set_id, model_artifact_id, model_name,
                    model_version, model_family, input_schema_name,
                    input_schema_version, compatibility_version,
                    policy_version, model_input_fingerprint,
                    inference_fingerprint, ordered_raw_probability_snapshot,
                    validation_snapshot, inference_timestamp, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.inference_id,
                    result.model_input_id,
                    result.match_id,
                    result.source_snapshot_id,
                    result.source_feature_set_id,
                    result.model_artifact_id,
                    result.model_name,
                    result.model_version,
                    result.model_family,
                    result.input_schema_name,
                    result.input_schema_version,
                    result.compatibility_version,
                    result.policy_version,
                    result.model_input_fingerprint,
                    result.inference_fingerprint,
                    _probabilities_json(result.raw_probabilities),
                    _validation_json(result.validation_summary),
                    result.inference_timestamp.isoformat(),
                    result.created_timestamp.isoformat(),
                ),
            )
            self._connection.commit()
            return result, False
        except InferenceConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.IntegrityError as exc:
            _rollback(self._connection)
            try:
                existing = self._by_fingerprint(result.inference_fingerprint)
            except sqlite3.DatabaseError:
                existing = None
            if existing is not None:
                return existing, True
            raise InferenceConflictError("Concurrent inference append conflicted.") from exc
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise InferencePersistenceError("Inference append failed.") from exc

    def find_by_inference_fingerprint(self, fingerprint: str) -> PredictionInferenceResult | None:
        return self._read(lambda: self._by_fingerprint(fingerprint), "Inference fingerprint lookup failed.")

    def find_for_model_input_and_artifact(self, model_input_id: str, model_artifact_id: str) -> PredictionInferenceResult | None:
        def query() -> PredictionInferenceResult | None:
            row = self._connection.execute(
                """
                SELECT * FROM prediction_inference_results
                WHERE model_input_id = ? AND model_artifact_id = ?
                ORDER BY inference_timestamp DESC, inference_id DESC LIMIT 1
                """,
                (model_input_id, model_artifact_id),
            ).fetchone()
            return _from_row(row) if row is not None else None
        return self._read(query, "Model-input inference lookup failed.")

    def find_latest_for_match_and_model(self, match_id: str, model_artifact_id: str) -> PredictionInferenceResult | None:
        def query() -> PredictionInferenceResult | None:
            row = self._connection.execute(
                """
                SELECT * FROM prediction_inference_results
                WHERE match_id = ? AND model_artifact_id = ?
                ORDER BY inference_timestamp DESC, inference_id DESC LIMIT 1
                """,
                (match_id, model_artifact_id),
            ).fetchone()
            return _from_row(row) if row is not None else None
        return self._read(query, "Latest match inference lookup failed.")

    def list_inferences_for_model_input(self, model_input_id: str) -> tuple[PredictionInferenceResult, ...]:
        def query() -> tuple[PredictionInferenceResult, ...]:
            rows = self._connection.execute(
                """
                SELECT * FROM prediction_inference_results WHERE model_input_id = ?
                ORDER BY inference_timestamp, inference_id
                """,
                (model_input_id,),
            ).fetchall()
            return tuple(_from_row(row) for row in rows)
        return self._read(query, "Model-input inference history lookup failed.")

    def load_inference_by_id(self, inference_id: str) -> PredictionInferenceResult | None:
        return self._read(lambda: self._by_id(inference_id), "Inference ID lookup failed.")

    def _by_fingerprint(self, fingerprint: str) -> PredictionInferenceResult | None:
        row = self._connection.execute(
            "SELECT * FROM prediction_inference_results WHERE inference_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def _by_id(self, inference_id: str) -> PredictionInferenceResult | None:
        row = self._connection.execute(
            "SELECT * FROM prediction_inference_results WHERE inference_id = ?",
            (inference_id,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def _read(self, operation: Callable[[], _T], message: str) -> _T:
        try:
            return operation()
        except sqlite3.DatabaseError as exc:
            raise InferencePersistenceError(message) from exc


def _probabilities_json(values: RawProbabilitySet) -> str:
    return canonical_json(tuple((item.target.value, _decimal(item.probability)) for item in values.ordered_probabilities))


def _validation_json(value: InferenceValidationSummary) -> str:
    return canonical_json({
        "policy_version": value.policy_version,
        "target_count": value.target_count,
        "ordered_checks": tuple({
            "code": item.code,
            "passed": item.passed,
            "observed_value": _decimal(item.observed_value) if item.observed_value is not None else None,
            "tolerance": _decimal(item.tolerance) if item.tolerance is not None else None,
        } for item in value.ordered_checks),
    })


def _from_row(row: sqlite3.Row) -> PredictionInferenceResult:
    probabilities = RawProbabilitySet(tuple(
        RawProbability(PredictionTarget(item[0]), Decimal(item[1]))
        for item in json.loads(row["ordered_raw_probability_snapshot"])
    ))
    raw_validation = json.loads(row["validation_snapshot"])
    validation = InferenceValidationSummary(
        policy_version=raw_validation["policy_version"],
        target_count=raw_validation["target_count"],
        ordered_checks=tuple(ProbabilityValidationCheck(
            code=item["code"],
            passed=bool(item["passed"]),
            observed_value=Decimal(item["observed_value"]) if item["observed_value"] is not None else None,
            tolerance=Decimal(item["tolerance"]) if item["tolerance"] is not None else None,
        ) for item in raw_validation["ordered_checks"]),
    )
    return PredictionInferenceResult(
        inference_id=row["inference_id"],
        model_input_id=row["model_input_id"],
        match_id=row["match_id"],
        source_snapshot_id=row["snapshot_id"],
        source_feature_set_id=row["feature_set_id"],
        model_artifact_id=row["model_artifact_id"],
        model_name=row["model_name"],
        model_version=row["model_version"],
        model_family=row["model_family"],
        input_schema_name=row["input_schema_name"],
        input_schema_version=row["input_schema_version"],
        compatibility_version=row["compatibility_version"],
        policy_version=row["policy_version"],
        inference_timestamp=datetime.fromisoformat(row["inference_timestamp"]),
        created_timestamp=datetime.fromisoformat(row["created_timestamp"]),
        raw_probabilities=probabilities,
        validation_summary=validation,
        model_input_fingerprint=row["model_input_fingerprint"],
        inference_fingerprint=row["inference_fingerprint"],
    )


def _decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.DatabaseError:
        pass
