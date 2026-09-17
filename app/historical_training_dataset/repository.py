"""SQLite source adapter and append-only training dataset repository."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT
from typing import Iterator

from app.database import Database, MigrationManager
from app.historical_data_import import NormalizedHistoricalStatistics

from .exceptions import DatasetBuildConflictError, DatasetPersistenceError, SourceProvenanceError
from .feature_projection import HISTORICAL_TRAINING_FEATURES_V1
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    ExclusionReason,
    HistoricalSourceMatch,
    HistoricalTrainingExample,
    HistoricalTrainingExclusion,
    NormalizedDatasetBuildCommand,
    PreparedDatasetBuild,
    TrainingExampleSource,
)


class SQLiteHistoricalTrainingSourceRepository:
    """Read explicitly selected immutable imports without provider access."""

    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def load_matches_for_imports(self, import_ids: tuple[str, ...]) -> tuple[HistoricalSourceMatch, ...]:
        fingerprint_imports: dict[str, set[str]] = {}
        for import_id in import_ids:
            row = self._connection.execute(
                "SELECT match_fingerprint_snapshot FROM historical_match_imports WHERE import_id=?",
                (import_id,),
            ).fetchone()
            if row is None:
                raise SourceProvenanceError(f"Selected historical import does not exist: {import_id}.")
            try:
                fingerprints = json.loads(row["match_fingerprint_snapshot"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise SourceProvenanceError("Historical import match provenance is malformed.") from exc
            if not isinstance(fingerprints, list) or not fingerprints:
                raise SourceProvenanceError("Historical import has no match provenance.")
            for fingerprint in fingerprints:
                if not isinstance(fingerprint, str):
                    raise SourceProvenanceError("Historical import match fingerprint is malformed.")
                fingerprint_imports.setdefault(fingerprint, set()).add(import_id)
        placeholders = ",".join("?" for _ in fingerprint_imports)
        rows = self._connection.execute(
            f"""
            SELECT * FROM historical_matches
            WHERE match_fingerprint IN ({placeholders})
            ORDER BY kickoff_utc,competition_identity,historical_match_id
            """,
            tuple(sorted(fingerprint_imports)),
        ).fetchall()
        if len(rows) != len(fingerprint_imports):
            raise SourceProvenanceError("Selected import references missing historical matches.")
        matches = tuple(self._source_match(row, fingerprint_imports[row["match_fingerprint"]]) for row in rows)
        return matches

    def _source_match(self, row: sqlite3.Row, import_ids: set[str]) -> HistoricalSourceMatch:
        statistics_rows = self._connection.execute(
            "SELECT * FROM historical_match_statistics WHERE historical_match_id=? ORDER BY team_side",
            (row["historical_match_id"],),
        ).fetchall()
        statistics = {item["team_side"]: _statistics(item) for item in statistics_rows}
        return HistoricalSourceMatch(
            historical_match_id=row["historical_match_id"],
            import_ids=tuple(sorted(import_ids)),
            match_fingerprint=row["match_fingerprint"],
            competition=row["competition"],
            competition_identity=row["competition_identity"],
            season=row["season"],
            kickoff_utc=row["kickoff_utc"],
            home_team_identity=row["home_team_identity"],
            away_team_identity=row["away_team_identity"],
            full_time_home_score=row["full_time_home_score"],
            full_time_away_score=row["full_time_away_score"],
            home_statistics=statistics.get("HOME"),
            away_statistics=statistics.get("AWAY"),
        )


class SQLiteHistoricalTrainingDatasetRepository:
    """Persist a complete build, examples, sources, and exclusions atomically."""

    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_dataset_build(self, build: PreparedDatasetBuild) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT request_fingerprint FROM historical_training_dataset_builds WHERE request_id=?",
                (build.command.request_id,),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != build.request_fingerprint:
                    raise DatasetBuildConflictError("Request ID already has different immutable content.")
                self._connection.commit()
                return
            self._insert_build(build)
            for example in build.examples:
                self._insert_example(example, build.command.build_timestamp)
                for source in example.sources:
                    self._insert_source(example, source, build.command.build_timestamp)
            for exclusion in build.exclusions:
                self._insert_exclusion(build, exclusion)
            self._connection.commit()
        except DatasetBuildConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise DatasetPersistenceError("Historical training dataset transaction failed.") from exc

    def find_by_dataset_fingerprint(self, fingerprint: str) -> PreparedDatasetBuild | None:
        row = self._connection.execute(
            "SELECT dataset_build_id FROM historical_training_dataset_builds WHERE dataset_fingerprint=?",
            (fingerprint,),
        ).fetchone()
        return self.load_dataset_build(row[0]) if row is not None else None

    def find_by_request_id(self, request_id: str) -> PreparedDatasetBuild | None:
        row = self._connection.execute(
            "SELECT dataset_build_id FROM historical_training_dataset_builds WHERE request_id=?",
            (request_id,),
        ).fetchone()
        return self.load_dataset_build(row[0]) if row is not None else None

    def load_dataset_identity(self, dataset_build_id: str) -> tuple[str, str, str, str] | None:
        """Load identity/schema metadata without materializing any example partition."""
        row = self._connection.execute(
            """SELECT request_fingerprint,dataset_fingerprint,feature_schema_version,label_schema_version
               FROM historical_training_dataset_builds WHERE dataset_build_id=?""",
            (dataset_build_id,),
        ).fetchone()
        return tuple(row) if row is not None else None

    def load_dataset_build(self, dataset_build_id: str) -> PreparedDatasetBuild | None:
        row = self._connection.execute(
            "SELECT * FROM historical_training_dataset_builds WHERE dataset_build_id=?",
            (dataset_build_id,),
        ).fetchone()
        if row is None:
            return None
        snapshot = json.loads(row["deterministic_build_snapshot"])
        command = NormalizedDatasetBuildCommand(**snapshot["command"])
        examples = self.list_examples_for_dataset(dataset_build_id)
        exclusions = self.list_exclusions_for_dataset(dataset_build_id)
        return PreparedDatasetBuild(
            dataset_build_id=dataset_build_id,
            command=command,
            request_fingerprint=row["request_fingerprint"],
            dataset_fingerprint=row["dataset_fingerprint"],
            source_match_count=row["source_match_count"],
            examples=examples,
            exclusions=exclusions,
            deterministic_build_snapshot=row["deterministic_build_snapshot"],
        )

    def load_training_example(self, training_example_id: str) -> HistoricalTrainingExample | None:
        row = self._connection.execute(
            "SELECT * FROM historical_training_examples WHERE training_example_id=?",
            (training_example_id,),
        ).fetchone()
        return self._example(row) if row is not None else None

    def list_examples_for_dataset(self, dataset_build_id: str) -> tuple[HistoricalTrainingExample, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM historical_training_examples WHERE dataset_build_id=?
            ORDER BY kickoff_timestamp,competition,historical_match_id
            """,
            (dataset_build_id,),
        ).fetchall()
        return tuple(self._example(row) for row in rows)

    def list_sources_for_example(self, training_example_id: str) -> tuple[TrainingExampleSource, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM historical_training_example_sources WHERE training_example_id=?
            ORDER BY deterministic_order_index
            """,
            (training_example_id,),
        ).fetchall()
        return tuple(TrainingExampleSource(
            source_historical_match_id=row["source_historical_match_id"],
            source_match_fingerprint=row["source_match_fingerprint"],
            source_kickoff=row["source_kickoff"],
            source_role=row["source_role"],
            deterministic_order_index=row["deterministic_order_index"],
            lookback_window_identity=row["lookback_window_identity"],
        ) for row in rows)

    def list_exclusions_for_dataset(self, dataset_build_id: str) -> tuple[HistoricalTrainingExclusion, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM historical_training_exclusions WHERE dataset_build_id=?
            ORDER BY historical_match_id,exclusion_reason
            """,
            (dataset_build_id,),
        ).fetchall()
        result = []
        for row in rows:
            detail = json.loads(row["deterministic_detail_snapshot"])
            result.append(HistoricalTrainingExclusion(
                historical_match_id=row["historical_match_id"],
                reason=ExclusionReason(row["exclusion_reason"]),
                ordered_reason_codes=tuple(detail["ordered_reason_codes"]),
                detail=tuple(tuple(item) for item in detail["detail"]),
            ))
        return tuple(result)

    def list_datasets_for_match(self, historical_match_id: str) -> tuple[PreparedDatasetBuild, ...]:
        rows = self._connection.execute(
            """
            SELECT dataset_build_id FROM historical_training_examples
            WHERE historical_match_id=? ORDER BY dataset_build_id
            """,
            (historical_match_id,),
        ).fetchall()
        return tuple(self.load_dataset_build(row[0]) for row in rows)

    def count_examples_by_label(self, dataset_build_id: str) -> tuple[tuple[str, int], ...]:
        counts: dict[str, int] = {}
        rows = self._connection.execute(
            "SELECT labels_snapshot FROM historical_training_examples WHERE dataset_build_id=?",
            (dataset_build_id,),
        )
        for row in rows:
            for name, value in json.loads(row[0]):
                counts[name] = counts.get(name, 0) + int(value)
        return tuple(sorted(counts.items()))

    def stream_examples_in_deterministic_order(self, dataset_build_id: str) -> Iterator[HistoricalTrainingExample]:
        cursor = self._connection.execute(
            """
            SELECT * FROM historical_training_examples WHERE dataset_build_id=?
            ORDER BY kickoff_timestamp,competition,historical_match_id
            """,
            (dataset_build_id,),
        )
        while True:
            rows = cursor.fetchmany(100)
            if not rows:
                return
            for row in rows:
                yield self._example(row)

    def _insert_build(self, build: PreparedDatasetBuild) -> None:
        command = build.command
        insufficient = sum(item.reason is ExclusionReason.INSUFFICIENT_HISTORY for item in build.exclusions)
        invalid = sum(item.reason is ExclusionReason.INVALID_PROVENANCE for item in build.exclusions)
        filters = canonical_json({
            "competitions": command.competition_filters,
            "seasons": command.season_filters,
            "kickoff_lower_bound": command.kickoff_lower_bound,
            "kickoff_upper_bound": command.kickoff_upper_bound,
            "metadata_version": command.metadata_version,
        })
        self._connection.execute(
            """
            INSERT INTO historical_training_dataset_builds (
                dataset_build_id,request_id,request_fingerprint,dataset_fingerprint,
                dataset_name,source_import_ids_snapshot,filters_snapshot,cutoff_policy,
                feature_schema_version,label_schema_version,dataset_policy_version,
                source_match_count,included_count,excluded_insufficient_history_count,
                excluded_invalid_provenance_count,deterministic_build_snapshot,
                build_timestamp,created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                build.dataset_build_id, command.request_id, build.request_fingerprint,
                build.dataset_fingerprint, command.dataset_name, canonical_json(command.source_import_ids),
                filters, command.cutoff_policy, command.feature_schema_version,
                command.label_schema_version, command.dataset_policy_version,
                build.source_match_count, len(build.examples), insufficient, invalid,
                build.deterministic_build_snapshot, command.build_timestamp, command.build_timestamp,
            ),
        )

    def _insert_example(self, item: HistoricalTrainingExample, created: str) -> None:
        self._connection.execute(
            """
            INSERT INTO historical_training_examples (
                training_example_id,dataset_build_id,historical_match_id,
                historical_match_fingerprint,kickoff_timestamp,competition,season,
                home_team_id,away_team_id,ordered_feature_vector,missingness_mask,
                completeness_score,feature_provenance_snapshot,lookback_window_identity,
                cutoff_timestamp,historical_source_fingerprints_snapshot,labels_snapshot,
                feature_schema_version,label_schema_version,dataset_policy_version,
                example_fingerprint,created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                item.training_example_id, item.dataset_build_id, item.historical_match_id,
                item.historical_match_fingerprint, item.kickoff_utc, item.competition, item.season,
                item.home_team_identity, item.away_team_identity,
                canonical_json(item.ordered_feature_vector), canonical_json(item.missingness_mask),
                str(item.completeness_score), canonical_json(item.feature_provenance),
                item.lookback_window_identity, item.cutoff_timestamp,
                canonical_json(item.historical_source_fingerprints), canonical_json(item.labels),
                item.feature_schema_version, item.label_schema_version, item.policy_version,
                item.example_fingerprint, created,
            ),
        )

    def _insert_source(self, example: HistoricalTrainingExample, source: TrainingExampleSource, created: str) -> None:
        identity = sha256_fingerprint({
            "training_example_id": example.training_example_id,
            "source_historical_match_id": source.source_historical_match_id,
            "order": source.deterministic_order_index,
        })
        self._connection.execute(
            """
            INSERT INTO historical_training_example_sources (
                source_row_id,training_example_id,source_historical_match_id,
                source_match_fingerprint,source_kickoff,source_role,
                deterministic_order_index,lookback_window_identity,created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                f"historical-training-source-{identity}", example.training_example_id,
                source.source_historical_match_id, source.source_match_fingerprint,
                source.source_kickoff, source.source_role, source.deterministic_order_index,
                source.lookback_window_identity, created,
            ),
        )

    def _insert_exclusion(self, build: PreparedDatasetBuild, item: HistoricalTrainingExclusion) -> None:
        detail = canonical_json({"ordered_reason_codes": item.ordered_reason_codes, "detail": item.detail})
        identity = sha256_fingerprint({
            "dataset_build_id": build.dataset_build_id,
            "historical_match_id": item.historical_match_id,
            "reason": item.reason,
        })
        self._connection.execute(
            """
            INSERT INTO historical_training_exclusions (
                exclusion_id,dataset_build_id,historical_match_id,exclusion_reason,
                deterministic_detail_snapshot,created_timestamp
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                f"historical-training-exclusion-{identity}", build.dataset_build_id,
                item.historical_match_id, item.reason.value, detail, build.command.build_timestamp,
            ),
        )

    def _example(self, row: sqlite3.Row) -> HistoricalTrainingExample:
        raw_values = json.loads(row["ordered_feature_vector"])
        if row["feature_schema_version"] == LIVE_MODEL_INPUT_CONTRACT.schema_version:
            converters = {
                "DECIMAL": Decimal,
                "INTEGER": int,
                "BOOLEAN": lambda value: bool(value),
            }
            values = tuple(
                None if value is None else converters[kind](value)
                for kind, value in zip(
                    LIVE_MODEL_INPUT_CONTRACT.ordered_feature_types, raw_values,
                    strict=True,
                )
            )
        else:
            values = tuple(
                None if value is None else int(value) if definition.data_type.value == "INTEGER" else Decimal(value)
                for definition, value in zip(HISTORICAL_TRAINING_FEATURES_V1, raw_values)
            )
        sources = self.list_sources_for_example(row["training_example_id"])
        return HistoricalTrainingExample(
            training_example_id=row["training_example_id"], dataset_build_id=row["dataset_build_id"],
            historical_match_id=row["historical_match_id"], historical_match_fingerprint=row["historical_match_fingerprint"],
            competition=row["competition"], season=row["season"], kickoff_utc=row["kickoff_timestamp"],
            home_team_identity=row["home_team_id"], away_team_identity=row["away_team_id"],
            ordered_feature_vector=values, missingness_mask=tuple(json.loads(row["missingness_mask"])),
            completeness_score=Decimal(row["completeness_score"]),
            feature_provenance=tuple(tuple(item) for item in json.loads(row["feature_provenance_snapshot"])),
            lookback_window_identity=row["lookback_window_identity"], cutoff_timestamp=row["cutoff_timestamp"],
            historical_source_fingerprints=tuple(json.loads(row["historical_source_fingerprints_snapshot"])),
            labels=tuple((name, int(value)) for name, value in json.loads(row["labels_snapshot"])),
            feature_schema_version=row["feature_schema_version"], label_schema_version=row["label_schema_version"],
            policy_version=row["dataset_policy_version"], example_fingerprint=row["example_fingerprint"],
            sources=sources,
        )


def _statistics(row: sqlite3.Row) -> NormalizedHistoricalStatistics:
    decimal = lambda value: Decimal(value) if value is not None else None
    return NormalizedHistoricalStatistics(
        possession=decimal(row["possession"]), shots=row["shots"], shots_on_target=row["shots_on_target"],
        expected_goals=decimal(row["expected_goals"]), corners=row["corners"],
        yellow_cards=row["yellow_cards"], red_cards=row["red_cards"], fouls=row["fouls"], offsides=row["offsides"],
    )


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()
