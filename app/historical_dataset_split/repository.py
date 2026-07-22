"""Atomic append-only SQLite persistence and bounded split reads."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from typing import Iterator

from app.database import Database, MigrationManager
from app.historical_training_dataset import HistoricalTrainingExample, SQLiteHistoricalTrainingDatasetRepository

from .exceptions import DatasetSplitConflictError, DatasetSplitPersistenceError
from .fingerprint import canonical_json
from .models import (
    DatasetSplitFold, GapConfiguration, MinimumPartitionSizes, NormalizedDatasetSplitCommand,
    Partition, PartitionAssignment, PreparedDatasetSplit, SplitStrategy,
)


class SQLiteHistoricalDatasetSplitRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self._database = database
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()
        self._training = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)

    def append_dataset_split(self, split: PreparedDatasetSplit) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT request_fingerprint FROM historical_dataset_splits WHERE split_request_id=?",
                (split.command.split_request_id,),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != split.request_fingerprint:
                    raise DatasetSplitConflictError("Split request ID already has different content.")
                self._connection.commit()
                return
            self._insert_split(split)
            for fold in split.folds:
                self._insert_fold(fold, split.command.split_timestamp)
                for assignment in fold.assignments:
                    self._insert_assignment(assignment, split.command.split_timestamp)
            self._connection.commit()
        except DatasetSplitConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise DatasetSplitPersistenceError("Historical dataset split transaction failed.") from exc

    def find_by_split_fingerprint(self, fingerprint: str) -> PreparedDatasetSplit | None:
        row = self._connection.execute(
            "SELECT split_id FROM historical_dataset_splits WHERE split_fingerprint=?", (fingerprint,),
        ).fetchone()
        return self.load_dataset_split(row[0]) if row is not None else None

    def find_by_request_id(self, request_id: str) -> PreparedDatasetSplit | None:
        row = self._connection.execute(
            "SELECT split_id FROM historical_dataset_splits WHERE split_request_id=?", (request_id,),
        ).fetchone()
        return self.load_dataset_split(row[0]) if row is not None else None

    def load_dataset_split(self, split_id: str) -> PreparedDatasetSplit | None:
        row = self._connection.execute(
            "SELECT * FROM historical_dataset_splits WHERE split_id=?", (split_id,),
        ).fetchone()
        if row is None:
            return None
        snapshot = json.loads(row["deterministic_split_snapshot"])
        command = _command(snapshot["command"])
        folds = self._list_folds(split_id)
        return PreparedDatasetSplit(
            split_id=split_id, command=command, request_fingerprint=row["request_fingerprint"],
            split_fingerprint=row["split_fingerprint"], folds=folds,
            aggregate_counts=tuple((name, int(value)) for name, value in json.loads(row["aggregate_counts"])),
            deterministic_split_snapshot=row["deterministic_split_snapshot"],
        )

    def load_split_with_folds(self, split_id: str) -> PreparedDatasetSplit | None:
        return self.load_dataset_split(split_id)

    def load_fold(self, fold_id: str) -> DatasetSplitFold | None:
        row = self._connection.execute(
            "SELECT * FROM historical_dataset_split_folds WHERE fold_id=?", (fold_id,),
        ).fetchone()
        return self._fold(row) if row is not None else None

    def load_assignment(self, assignment_id: str) -> PartitionAssignment | None:
        row = self._connection.execute(
            "SELECT * FROM historical_dataset_split_assignments WHERE assignment_id=?",
            (assignment_id,),
        ).fetchone()
        return _assignment(row) if row is not None else None

    def list_assignments_for_fold(self, fold_id: str) -> tuple[PartitionAssignment, ...]:
        rows = self._connection.execute(
            """SELECT * FROM historical_dataset_split_assignments
               WHERE fold_id=? ORDER BY assignment_order""",
            (fold_id,),
        ).fetchall()
        return tuple(_assignment(row) for row in rows)

    def list_assignments_by_partition(self, fold_id: str, partition: Partition) -> tuple[PartitionAssignment, ...]:
        rows = self._connection.execute(
            """SELECT * FROM historical_dataset_split_assignments
               WHERE fold_id=? AND partition=? ORDER BY assignment_order""",
            (fold_id, partition.value),
        ).fetchall()
        return tuple(_assignment(row) for row in rows)

    def list_splits_for_dataset(self, dataset_build_id: str) -> tuple[PreparedDatasetSplit, ...]:
        rows = self._connection.execute(
            """SELECT split_id FROM historical_dataset_splits
               WHERE source_dataset_build_id=? ORDER BY split_timestamp,split_id""",
            (dataset_build_id,),
        ).fetchall()
        return tuple(self.load_dataset_split(row[0]) for row in rows)

    def count_partition_labels(self, fold_id: str, partition: Partition) -> tuple[tuple[str, int], ...]:
        rows = self._connection.execute(
            """
            SELECT e.labels_snapshot FROM historical_dataset_split_assignments a
            JOIN historical_training_examples e ON e.training_example_id=a.training_example_id
            WHERE a.fold_id=? AND a.partition=? ORDER BY a.assignment_order
            """,
            (fold_id, partition.value),
        )
        counts: dict[str, int] = {}
        for row in rows:
            for name, value in json.loads(row[0]):
                counts[name] = counts.get(name, 0) + int(value)
        return tuple(sorted(counts.items()))

    def stream_partition_examples(self, fold_id: str, partition: Partition) -> Iterator[HistoricalTrainingExample]:
        cursor = self._connection.execute(
            """SELECT training_example_id FROM historical_dataset_split_assignments
               WHERE fold_id=? AND partition=? ORDER BY assignment_order""",
            (fold_id, partition.value),
        )
        while True:
            rows = cursor.fetchmany(100)
            if not rows:
                return
            for row in rows:
                example = self._training.load_training_example(row[0])
                if example is not None:
                    yield example

    def list_excluded_assignments(self, fold_id: str) -> tuple[PartitionAssignment, ...]:
        rows = self._connection.execute(
            """SELECT * FROM historical_dataset_split_assignments
               WHERE fold_id=? AND partition LIKE 'EXCLUDED_%' ORDER BY assignment_order""",
            (fold_id,),
        ).fetchall()
        return tuple(_assignment(row) for row in rows)

    def _list_folds(self, split_id: str) -> tuple[DatasetSplitFold, ...]:
        rows = self._connection.execute(
            "SELECT * FROM historical_dataset_split_folds WHERE split_id=? ORDER BY fold_index",
            (split_id,),
        ).fetchall()
        return tuple(self._fold(row) for row in rows)

    def _fold(self, row: sqlite3.Row) -> DatasetSplitFold:
        return DatasetSplitFold(
            fold_id=row["fold_id"], split_id=row["split_id"], fold_index=row["fold_index"],
            fold_fingerprint=row["fold_fingerprint"],
            train_boundary=tuple(tuple(item) for item in json.loads(row["train_boundary_snapshot"])),
            validation_boundary=tuple(tuple(item) for item in json.loads(row["validation_boundary_snapshot"])),
            test_boundary=tuple(tuple(item) for item in json.loads(row["test_boundary_snapshot"])),
            assignments=self.list_assignments_for_fold(row["fold_id"]),
            achieved_counts=tuple((name, int(value)) for name, value in json.loads(row["achieved_counts"])),
            achieved_ratios=tuple((name, Decimal(value)) for name, value in json.loads(row["achieved_ratios"])),
            earliest_latest_kickoffs=tuple(tuple(item) for item in json.loads(row["earliest_latest_kickoffs_snapshot"])),
        )

    def _insert_split(self, split: PreparedDatasetSplit) -> None:
        command = split.command
        filters = canonical_json({
            "competitions": command.competition_filters, "seasons": command.season_filters,
            "kickoff_lower_bound": command.kickoff_lower_bound, "kickoff_upper_bound": command.kickoff_upper_bound,
        })
        boundary_ratio = canonical_json({
            "explicit_boundaries": command.explicit_boundaries,
            "ratios": command.ratios, "expanding_window": command.expanding_window,
            "equal_kickoff_policy": command.equal_kickoff_policy,
        })
        self._connection.execute(
            """
            INSERT INTO historical_dataset_splits (
                split_id,split_request_id,request_fingerprint,split_fingerprint,split_name,
                source_dataset_build_id,source_dataset_fingerprint,split_strategy,
                split_policy_version,feature_schema_version,label_schema_version,
                filter_snapshot,boundary_ratio_snapshot,gap_snapshot,minimum_size_snapshot,
                fold_count,aggregate_counts,deterministic_split_snapshot,split_timestamp,created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                split.split_id, command.split_request_id, split.request_fingerprint, split.split_fingerprint,
                command.split_name, command.source_dataset_build_id, command.source_dataset_fingerprint,
                command.strategy.value, command.split_policy_version, command.feature_schema_version,
                command.label_schema_version, filters, boundary_ratio, canonical_json(command.gaps),
                canonical_json(command.minimum_partition_sizes), len(split.folds),
                canonical_json(split.aggregate_counts), split.deterministic_split_snapshot,
                command.split_timestamp, command.split_timestamp,
            ),
        )

    def _insert_fold(self, fold: DatasetSplitFold, created: str) -> None:
        self._connection.execute(
            """
            INSERT INTO historical_dataset_split_folds (
                fold_id,split_id,fold_index,fold_fingerprint,train_boundary_snapshot,
                validation_boundary_snapshot,test_boundary_snapshot,achieved_counts,
                achieved_ratios,earliest_latest_kickoffs_snapshot,created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                fold.fold_id, fold.split_id, fold.fold_index, fold.fold_fingerprint,
                canonical_json(fold.train_boundary), canonical_json(fold.validation_boundary),
                canonical_json(fold.test_boundary), canonical_json(fold.achieved_counts),
                canonical_json(fold.achieved_ratios), canonical_json(fold.earliest_latest_kickoffs), created,
            ),
        )

    def _insert_assignment(self, item: PartitionAssignment, created: str) -> None:
        self._connection.execute(
            """
            INSERT INTO historical_dataset_split_assignments (
                assignment_id,split_id,fold_id,training_example_id,historical_match_id,
                kickoff_timestamp,competition,season,partition,assignment_order,
                example_fingerprint,assignment_fingerprint,exclusion_reason,created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                item.assignment_id, item.split_id, item.fold_id, item.training_example_id,
                item.historical_match_id, item.kickoff_utc, item.competition, item.season,
                item.partition.value, item.assignment_order, item.example_fingerprint,
                item.assignment_fingerprint, item.exclusion_reason, created,
            ),
        )


def _command(value: dict) -> NormalizedDatasetSplitCommand:
    return NormalizedDatasetSplitCommand(
        split_request_id=value["split_request_id"], split_name=value["split_name"],
        source_dataset_build_id=value["source_dataset_build_id"],
        source_dataset_fingerprint=value["source_dataset_fingerprint"],
        strategy=SplitStrategy(value["strategy"]),
        explicit_boundaries=tuple((name, item) for name, item in value["explicit_boundaries"]),
        ratios=tuple((name, Decimal(item)) for name, item in value["ratios"]),
        expanding_window=tuple((name, item) for name, item in value["expanding_window"]),
        gaps=GapConfiguration(**value["gaps"]),
        minimum_partition_sizes=MinimumPartitionSizes(**value["minimum_partition_sizes"]),
        equal_kickoff_policy=value["equal_kickoff_policy"], maximum_folds=value["maximum_folds"],
        split_timestamp=value["split_timestamp"], feature_schema_version=value["feature_schema_version"],
        label_schema_version=value["label_schema_version"], split_policy_version=value["split_policy_version"],
        metadata_version=value["metadata_version"], competition_filters=tuple(value["competition_filters"]),
        season_filters=tuple(value["season_filters"]), kickoff_lower_bound=value["kickoff_lower_bound"],
        kickoff_upper_bound=value["kickoff_upper_bound"],
    )


def _assignment(row: sqlite3.Row) -> PartitionAssignment:
    return PartitionAssignment(
        assignment_id=row["assignment_id"], split_id=row["split_id"], fold_id=row["fold_id"],
        training_example_id=row["training_example_id"], historical_match_id=row["historical_match_id"],
        kickoff_utc=row["kickoff_timestamp"], competition=row["competition"], season=row["season"],
        partition=Partition(row["partition"]), assignment_order=row["assignment_order"],
        example_fingerprint=row["example_fingerprint"], assignment_fingerprint=row["assignment_fingerprint"],
        exclusion_reason=row["exclusion_reason"],
    )


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()
