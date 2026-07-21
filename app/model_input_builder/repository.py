import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from app.database import Database, MigrationManager
from app.feature_store import FeatureValueType
from app.match_data_snapshot import canonical_json

from .exceptions import ModelInputConflictError, ModelInputPersistenceError
from .models import (
    ModelInputFeatureMetadata,
    ModelInputVector,
    PersistedSourceFeatureIdentity,
)


class SQLiteModelInputRepository:
    """Append-only model input vectors and read-only feature provenance."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def load_source_feature_identity(
        self,
        feature_set_id: str,
    ) -> PersistedSourceFeatureIdentity | None:
        try:
            row = self._connection.execute(
                """
                SELECT feature_set_id, snapshot_id, match_id,
                       schema_name, schema_version,
                       model_compatibility_version,
                       source_snapshot_fingerprint, feature_fingerprint,
                       created_timestamp
                FROM match_feature_sets WHERE feature_set_id = ?
                """,
                (feature_set_id,),
            ).fetchone()
            if row is None:
                return None
            return PersistedSourceFeatureIdentity(
                feature_set_id=row["feature_set_id"],
                snapshot_id=row["snapshot_id"],
                match_id=row["match_id"],
                feature_schema_name=row["schema_name"],
                feature_schema_version=row["schema_version"],
                compatibility_version=row["model_compatibility_version"],
                source_snapshot_fingerprint=row["source_snapshot_fingerprint"],
                feature_fingerprint=row["feature_fingerprint"],
                created_timestamp=datetime.fromisoformat(row["created_timestamp"]),
            )
        except sqlite3.DatabaseError as exc:
            raise ModelInputPersistenceError(
                "Source feature identity lookup failed."
            ) from exc

    def append_model_input(
        self,
        vector: ModelInputVector,
    ) -> tuple[ModelInputVector, bool]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._by_fingerprint(vector.model_input_fingerprint)
            if existing is not None:
                self._connection.commit()
                return existing, True
            same_slot = self._for_feature_set(
                vector.feature_set_id,
                vector.schema_name,
                vector.schema_version,
                vector.compatibility_version,
            )
            if same_slot is not None:
                raise ModelInputConflictError(
                    "Feature set and model schema already have different immutable content."
                )
            self._connection.execute(
                """
                INSERT INTO model_input_vectors (
                    model_input_id, feature_set_id, snapshot_id, match_id,
                    schema_name, schema_version, compatibility_version,
                    feature_fingerprint, source_snapshot_fingerprint,
                    source_feature_fingerprint, model_input_fingerprint,
                    ordered_feature_names, ordered_feature_values,
                    missingness_mask, missing_feature_names, feature_metadata,
                    completeness_score, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vector.model_input_id,
                    vector.feature_set_id,
                    vector.snapshot_id,
                    vector.match_id,
                    vector.schema_name,
                    vector.schema_version,
                    vector.compatibility_version,
                    vector.feature_fingerprint,
                    vector.source_snapshot_fingerprint,
                    vector.source_feature_fingerprint,
                    vector.model_input_fingerprint,
                    canonical_json(vector.ordered_feature_names),
                    canonical_json(vector.ordered_feature_values),
                    canonical_json(vector.missingness_mask),
                    canonical_json(vector.missing_feature_names),
                    canonical_json(vector.feature_metadata),
                    _decimal(vector.completeness_score),
                    vector.created_timestamp.isoformat(),
                ),
            )
            self._connection.commit()
            return vector, False
        except ModelInputConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.IntegrityError as exc:
            _rollback(self._connection)
            existing = self._by_fingerprint(vector.model_input_fingerprint)
            if existing is not None:
                return existing, True
            raise ModelInputConflictError(
                "Concurrent model-input append conflicted."
            ) from exc
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise ModelInputPersistenceError("Model-input append failed.") from exc

    def find_by_fingerprint(self, fingerprint: str) -> ModelInputVector | None:
        try:
            return self._by_fingerprint(fingerprint)
        except sqlite3.DatabaseError as exc:
            raise ModelInputPersistenceError(
                "Model-input fingerprint lookup failed."
            ) from exc

    def find_for_feature_set(
        self,
        feature_set_id: str,
        schema_name: str,
        schema_version: str,
        compatibility_version: str,
    ) -> ModelInputVector | None:
        try:
            return self._for_feature_set(
                feature_set_id,
                schema_name,
                schema_version,
                compatibility_version,
            )
        except sqlite3.DatabaseError as exc:
            raise ModelInputPersistenceError(
                "Feature-set model-input lookup failed."
            ) from exc

    def list_for_feature_set(
        self,
        feature_set_id: str,
    ) -> tuple[ModelInputVector, ...]:
        try:
            rows = self._connection.execute(
                """
                SELECT * FROM model_input_vectors WHERE feature_set_id = ?
                ORDER BY schema_name, schema_version, compatibility_version
                """,
                (feature_set_id,),
            ).fetchall()
            return tuple(_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise ModelInputPersistenceError(
                "Model-input history lookup failed."
            ) from exc

    def _by_fingerprint(self, fingerprint: str) -> ModelInputVector | None:
        row = self._connection.execute(
            "SELECT * FROM model_input_vectors WHERE model_input_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def _for_feature_set(
        self,
        feature_set_id: str,
        schema_name: str,
        schema_version: str,
        compatibility_version: str,
    ) -> ModelInputVector | None:
        row = self._connection.execute(
            """
            SELECT * FROM model_input_vectors
            WHERE feature_set_id = ? AND schema_name = ? AND schema_version = ?
              AND compatibility_version = ?
            """,
            (
                feature_set_id,
                schema_name,
                schema_version,
                compatibility_version,
            ),
        ).fetchone()
        return _from_row(row) if row is not None else None


def _from_row(row: sqlite3.Row) -> ModelInputVector:
    raw_metadata = json.loads(row["feature_metadata"])
    metadata = tuple(
        ModelInputFeatureMetadata(
            index=item["index"],
            name=item["name"],
            value_type=FeatureValueType(item["value_type"]),
            description=item["description"],
            required_baseline=bool(item["required_baseline"]),
            source_feature_schema=item["source_feature_schema"],
        )
        for item in raw_metadata
    )
    raw_values = json.loads(row["ordered_feature_values"])
    values = tuple(
        _restore_value(value, item.value_type)
        for value, item in zip(raw_values, metadata, strict=True)
    )
    return ModelInputVector(
        model_input_id=row["model_input_id"],
        feature_set_id=row["feature_set_id"],
        snapshot_id=row["snapshot_id"],
        match_id=row["match_id"],
        schema_name=row["schema_name"],
        schema_version=row["schema_version"],
        compatibility_version=row["compatibility_version"],
        ordered_feature_names=tuple(json.loads(row["ordered_feature_names"])),
        ordered_feature_values=values,
        missingness_mask=tuple(json.loads(row["missingness_mask"])),
        missing_feature_names=tuple(json.loads(row["missing_feature_names"])),
        completeness_score=Decimal(row["completeness_score"]),
        feature_metadata=metadata,
        feature_fingerprint=row["feature_fingerprint"],
        source_snapshot_fingerprint=row["source_snapshot_fingerprint"],
        source_feature_fingerprint=row["source_feature_fingerprint"],
        model_input_fingerprint=row["model_input_fingerprint"],
        created_timestamp=datetime.fromisoformat(row["created_timestamp"]),
    )


def _restore_value(
    value: object,
    value_type: FeatureValueType,
) -> Decimal | int | bool | None:
    if value is None:
        return None
    if value_type is FeatureValueType.DECIMAL:
        return Decimal(str(value))
    if value_type is FeatureValueType.INTEGER:
        return int(value)
    return bool(value)


def _decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.DatabaseError:
        pass
