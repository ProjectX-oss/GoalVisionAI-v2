import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from app.database import Database, MigrationManager

from .definitions import FEATURE_DEFINITION_BY_NAME
from .exceptions import FeatureStoreConflictError, FeatureStorePersistenceError
from .fingerprint import FeatureSetFingerprint
from .models import DataQualitySummary, FeatureValue, FeatureValueType, MatchFeatureSet


class SQLiteFeatureStoreRepository:
    """Append-only feature-set persistence."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_feature_set(self, feature_set: MatchFeatureSet) -> tuple[MatchFeatureSet, bool]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._by_fingerprint(feature_set.feature_fingerprint)
            if existing is not None:
                self._connection.commit()
                return existing, True
            same_slot = self._for_snapshot_schema(
                feature_set.snapshot_id,
                feature_set.feature_schema_name,
                feature_set.feature_schema_version,
                feature_set.model_compatibility_version,
            )
            if same_slot is not None:
                raise FeatureStoreConflictError(
                    "Snapshot/schema identity already has different immutable feature content."
                )
            serializer = FeatureSetFingerprint()
            self._connection.execute(
                """
                INSERT INTO match_feature_sets (
                    feature_set_id, snapshot_id, match_id, schema_name,
                    schema_version, model_compatibility_version,
                    source_snapshot_fingerprint, feature_fingerprint,
                    deterministic_feature_snapshot, missingness_snapshot,
                    data_quality_snapshot, feature_timestamp, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feature_set.feature_set_id, feature_set.snapshot_id,
                    feature_set.match_id, feature_set.feature_schema_name,
                    feature_set.feature_schema_version,
                    feature_set.model_compatibility_version,
                    feature_set.source_snapshot_fingerprint,
                    feature_set.feature_fingerprint,
                    serializer.serialize_values(feature_set.ordered_feature_values),
                    serializer.serialize_missingness(feature_set.missingness_indicators),
                    serializer.serialize_quality(feature_set.data_quality_summary),
                    feature_set.feature_timestamp.isoformat(),
                    feature_set.created_timestamp.isoformat(),
                ),
            )
            self._connection.commit()
            return feature_set, False
        except FeatureStoreConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.IntegrityError as exc:
            _rollback(self._connection)
            existing = self._by_fingerprint(feature_set.feature_fingerprint)
            if existing is not None:
                return existing, True
            raise FeatureStoreConflictError("Concurrent feature append conflicted.") from exc
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise FeatureStorePersistenceError("Feature append failed.") from exc

    def find_by_feature_fingerprint(self, fingerprint: str) -> MatchFeatureSet | None:
        try:
            return self._by_fingerprint(fingerprint)
        except sqlite3.DatabaseError as exc:
            raise FeatureStorePersistenceError("Feature fingerprint lookup failed.") from exc

    def find_for_snapshot_and_schema(
        self,
        snapshot_id: str,
        schema_name: str,
        schema_version: str,
        model_compatibility_version: str = "official_prediction_model_input_v1",
    ) -> MatchFeatureSet | None:
        try:
            return self._for_snapshot_schema(
                snapshot_id, schema_name, schema_version, model_compatibility_version
            )
        except sqlite3.DatabaseError as exc:
            raise FeatureStorePersistenceError("Snapshot feature lookup failed.") from exc

    def find_latest_for_match(
        self,
        match_id: str,
        schema_name: str | None = None,
    ) -> MatchFeatureSet | None:
        try:
            clause = " AND schema_name = ?" if schema_name is not None else ""
            params = (match_id, schema_name) if schema_name is not None else (match_id,)
            row = self._connection.execute(
                f"""
                SELECT * FROM match_feature_sets WHERE match_id = ?{clause}
                ORDER BY feature_timestamp DESC, feature_set_id DESC LIMIT 1
                """,
                params,
            ).fetchone()
            return _from_row(row) if row is not None else None
        except sqlite3.DatabaseError as exc:
            raise FeatureStorePersistenceError("Latest match feature lookup failed.") from exc

    def list_feature_sets_for_snapshot(self, snapshot_id: str) -> tuple[MatchFeatureSet, ...]:
        try:
            rows = self._connection.execute(
                """
                SELECT * FROM match_feature_sets WHERE snapshot_id = ?
                ORDER BY schema_name, schema_version, model_compatibility_version
                """,
                (snapshot_id,),
            ).fetchall()
            return tuple(_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise FeatureStorePersistenceError("Snapshot feature history lookup failed.") from exc

    def _by_fingerprint(self, fingerprint: str) -> MatchFeatureSet | None:
        row = self._connection.execute(
            "SELECT * FROM match_feature_sets WHERE feature_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def _for_snapshot_schema(
        self,
        snapshot_id: str,
        schema_name: str,
        schema_version: str,
        model_compatibility_version: str,
    ) -> MatchFeatureSet | None:
        row = self._connection.execute(
            """
            SELECT * FROM match_feature_sets
            WHERE snapshot_id = ? AND schema_name = ? AND schema_version = ?
              AND model_compatibility_version = ?
            """,
            (snapshot_id, schema_name, schema_version, model_compatibility_version),
        ).fetchone()
        return _from_row(row) if row is not None else None


def _from_row(row: sqlite3.Row) -> MatchFeatureSet:
    raw_values = json.loads(row["deterministic_feature_snapshot"])
    values = []
    for raw in raw_values:
        name, value = raw["name"], raw["value"]
        definition = FEATURE_DEFINITION_BY_NAME[name]
        if value is not None:
            if definition.value_type is FeatureValueType.DECIMAL:
                value = Decimal(value)
            elif definition.value_type is FeatureValueType.INTEGER:
                value = int(value)
            else:
                value = bool(value)
        values.append(FeatureValue(name, value))
    missingness = tuple((name, bool(missing)) for name, missing in json.loads(row["missingness_snapshot"]))
    raw_quality = json.loads(row["data_quality_snapshot"])
    quality = DataQualitySummary(
        Decimal(raw_quality["completeness_score"]),
        raw_quality["available_feature_count"], raw_quality["missing_feature_count"],
        raw_quality["total_feature_count"],
        tuple((name, bool(value)) for name, value in raw_quality["source_group_availability"]),
    )
    return MatchFeatureSet(
        row["feature_set_id"], row["snapshot_id"], row["match_id"],
        row["schema_name"], row["schema_version"],
        row["model_compatibility_version"], datetime.fromisoformat(row["feature_timestamp"]),
        tuple(values), missingness, quality, row["source_snapshot_fingerprint"],
        row["feature_fingerprint"], datetime.fromisoformat(row["created_timestamp"]),
    )


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.DatabaseError:
        pass
