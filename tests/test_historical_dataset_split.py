import sqlite3
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.historical_data_import import HISTORICAL_DATASET_SCHEMA, HistoricalDataset, HistoricalMatchInput, build_historical_match_importer
from app.historical_training_dataset import (
    DatasetBuildCommand, DatasetBuildStatus, SQLiteHistoricalTrainingDatasetRepository,
    build_historical_training_dataset_service,
)
from app.historical_dataset_split import (
    DatasetSplitCommand, DatasetSplitStatus, ExpandingWindow, ExplicitTimeBoundaries,
    GapConfiguration, MinimumPartitionSizes, Partition, RatioByChronology,
    SQLiteHistoricalDatasetSplitRepository, SplitStrategy,
    build_historical_dataset_split_service, inspect_partition_assignment,
    inspect_split_fold, summarize_dataset_split, summarize_partition_labels,
    verify_equal_kickoff_grouping, verify_partition_chronology,
    verify_partition_exclusivity, verify_source_dataset_linkage, verify_split_fingerprints,
)
from app.historical_dataset_split.validation import normalize_split_command, validate_source_dataset
from app.historical_dataset_split.policy import DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY


UTC = timezone.utc
BASE = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
SPLIT_AT = datetime(2026, 7, 22, 21, 0, tzinfo=UTC)


def match(day: int, game: int, home: str, away: str) -> HistoricalMatchInput:
    home_score = (day + game) % 4
    away_score = (day * 2 + game) % 3
    return HistoricalMatchInput(
        source_match_id=f"match-{day}-{game}", competition="Example League",
        season="2024/25", round=f"Round {day + 1}", kickoff_utc=BASE + timedelta(days=day),
        home_team=home, away_team=away, full_time_home_score=home_score,
        full_time_away_score=away_score,
        full_time_result="H" if home_score > away_score else "D" if home_score == away_score else "A",
        venue=f"{home} Ground",
    )


def history() -> tuple[HistoricalMatchInput, ...]:
    games = []
    for day in range(10):
        if day % 2 == 0:
            pairs = (("Alpha", "Charlie"), ("Bravo", "Delta"))
        else:
            pairs = (("Charlie", "Alpha"), ("Delta", "Bravo"))
        games.extend(match(day, index, home, away) for index, (home, away) in enumerate(pairs))
    return tuple(games)


def build_source(database: Database):
    imported = build_historical_match_importer(database).import_dataset(
        HistoricalDataset(
            schema_version=HISTORICAL_DATASET_SCHEMA, provider="Split Test Provider",
            dataset_id="split-history", dataset_version="v1", matches=history(),
        ),
        import_timestamp="2026-07-22T19:00:00Z",
    )
    training = build_historical_training_dataset_service(database, migrate=False)
    outcome = training.build(DatasetBuildCommand(
        request_id="training-for-split", dataset_name="Training source",
        source_import_ids=(imported.import_id,), competition_filters=("Example League",),
        season_filters=("2024/25",), kickoff_lower_bound=BASE + timedelta(days=3),
        kickoff_upper_bound=BASE + timedelta(days=10), build_timestamp="2026-07-22T20:00:00Z",
    ))
    assert outcome.status is DatasetBuildStatus.DATASET_BUILT
    return outcome


def explicit_command(source, *, request_id="split-request-1", gaps=GapConfiguration(1, 1), minimums=MinimumPartitionSizes()):
    return DatasetSplitCommand(
        split_request_id=request_id, split_name="Explicit chronological split",
        source_dataset_build_id=source.dataset_build_id,
        source_dataset_fingerprint=source.dataset_fingerprint,
        explicit_boundaries=ExplicitTimeBoundaries(
            train_end_exclusive=BASE + timedelta(days=5),
            validation_start_inclusive=BASE + timedelta(days=6),
            validation_end_exclusive=BASE + timedelta(days=8),
            test_start_inclusive=BASE + timedelta(days=9),
            test_end_exclusive=None,
        ),
        gaps=gaps, minimum_partition_sizes=minimums, split_timestamp=SPLIT_AT,
    )


class ExplicitSplitTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.source = build_source(self.database)
        self.service = build_historical_dataset_split_service(self.database, migrate=False)
        self.repository = SQLiteHistoricalDatasetSplitRepository(self.database, migrate=False)

    def tearDown(self):
        self.database.close()

    def test_explicit_split_preserves_chronology_groups_gaps_and_open_test(self):
        outcome = self.service.create(explicit_command(self.source))
        self.assertEqual(outcome.status, DatasetSplitStatus.SPLIT_CREATED)
        self.assertEqual((outcome.train_count, outcome.validation_count, outcome.test_count), (4, 4, 2))
        self.assertEqual(outcome.excluded_gap_count, 4)
        fold = self.repository.load_dataset_split(outcome.split_id).folds[0]
        by_partition = {part: self.repository.list_assignments_by_partition(fold.fold_id, part) for part in Partition}
        self.assertLess(max(item.kickoff_utc for item in by_partition[Partition.TRAIN]), min(item.kickoff_utc for item in by_partition[Partition.VALIDATION]))
        self.assertLess(max(item.kickoff_utc for item in by_partition[Partition.VALIDATION]), min(item.kickoff_utc for item in by_partition[Partition.TEST]))
        self.assertEqual({item.kickoff_utc for item in by_partition[Partition.EXCLUDED_GAP]}, {
            "2025-01-06T12:00:00Z", "2025-01-09T12:00:00Z",
        })
        self.assertEqual(verify_equal_kickoff_grouping(self.repository, outcome.split_id), ())

    def test_empty_gap_adjacent_boundaries_and_same_day_order_are_valid(self):
        command = replace(
            explicit_command(self.source, request_id="no-gap"),
            gaps=GapConfiguration(),
            explicit_boundaries=ExplicitTimeBoundaries(
                BASE + timedelta(days=5), BASE + timedelta(days=5),
                BASE + timedelta(days=7), BASE + timedelta(days=7), None,
            ),
        )
        outcome = self.service.create(command)
        self.assertEqual(outcome.status, DatasetSplitStatus.SPLIT_CREATED)
        self.assertEqual(outcome.excluded_gap_count, 0)
        fold = self.repository.load_dataset_split(outcome.split_id).folds[0]
        kickoffs = tuple(item.kickoff_utc for item in fold.assignments)
        self.assertEqual(kickoffs, tuple(sorted(kickoffs)))

    def test_overlapping_unordered_boundaries_and_gap_mismatch_are_rejected_without_writes(self):
        cases = (
            replace(explicit_command(self.source), explicit_boundaries=ExplicitTimeBoundaries(
                BASE + timedelta(days=7), BASE + timedelta(days=6), BASE + timedelta(days=8), BASE + timedelta(days=9), None,
            )),
            replace(explicit_command(self.source), gaps=GapConfiguration()),
        )
        for item in cases:
            with self.subTest(item=item):
                self.assertEqual(self.service.create(item).status, DatasetSplitStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_dataset_splits").fetchone()[0], 0)

    def test_minimum_partition_sizes_are_enforced(self):
        outcome = self.service.create(explicit_command(
            self.source, request_id="too-large", minimums=MinimumPartitionSizes(train=5, validation=1, test=1),
        ))
        self.assertEqual(outcome.status, DatasetSplitStatus.REJECTED_PARTITION_SIZE)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_dataset_splits").fetchone()[0], 0)

    def test_filters_persist_excluded_filter_assignments(self):
        outcome = self.service.create(replace(
            explicit_command(self.source, request_id="filtered"),
            season_filters=("other-season",), minimum_partition_sizes=MinimumPartitionSizes(0, 0, 0),
        ))
        self.assertEqual(outcome.status, DatasetSplitStatus.NO_ELIGIBLE_EXAMPLES)
        self.assertEqual(outcome.fold_count, 1)
        self.assertEqual(outcome.excluded_filter_count, 14)
        fold = self.repository.load_dataset_split(outcome.split_id).folds[0]
        self.assertTrue(all(item.partition is Partition.EXCLUDED_FILTER for item in fold.assignments))


class RatioAndExpandingSplitTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.source = build_source(self.database)
        self.service = build_historical_dataset_split_service(self.database, migrate=False)
        self.repository = SQLiteHistoricalDatasetSplitRepository(self.database, migrate=False)

    def tearDown(self):
        self.database.close()

    def ratio_command(self, request_id="ratio", ratios=RatioByChronology("0.5", "0.25", "0.25"), gaps=GapConfiguration()):
        return DatasetSplitCommand(
            split_request_id=request_id, split_name="Ratio split",
            source_dataset_build_id=self.source.dataset_build_id,
            source_dataset_fingerprint=self.source.dataset_fingerprint,
            strategy=SplitStrategy.RATIO_BY_CHRONOLOGY_V1, ratios=ratios, gaps=gaps,
            split_timestamp=SPLIT_AT,
        )

    def test_ratio_split_is_deterministic_grouped_unshuffled_and_reports_ratios(self):
        first = self.service.create(self.ratio_command())
        self.assertEqual(first.status, DatasetSplitStatus.SPLIT_CREATED)
        self.assertEqual(first.train_count + first.validation_count + first.test_count, 14)
        self.assertEqual(sum(value for _, value in first.actual_achieved_ratios), Decimal("1.000000"))
        fold = self.repository.load_dataset_split(first.split_id).folds[0]
        self.assertEqual(tuple(item.assignment_order for item in fold.assignments), tuple(range(14)))
        self.assertEqual(verify_equal_kickoff_grouping(self.repository, first.split_id), ())
        replay = self.service.create(self.ratio_command())
        self.assertEqual(replay.status, DatasetSplitStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(first.split_fingerprint, replay.split_fingerprint)

    def test_ratio_validation_and_small_group_handling(self):
        invalid = self.service.create(self.ratio_command("bad-ratio", RatioByChronology("0.5", "0.3", "0.3")))
        self.assertEqual(invalid.status, DatasetSplitStatus.REJECTED_INVALID_REQUEST)
        small = self.service.create(replace(
            self.ratio_command("small"), kickoff_lower_bound=BASE + timedelta(days=8),
            minimum_partition_sizes=MinimumPartitionSizes(0, 0, 0),
        ))
        self.assertEqual(small.status, DatasetSplitStatus.REJECTED_PARTITION_SIZE)

    def test_ratio_gap_is_auditable_and_preserves_chronology(self):
        outcome = self.service.create(self.ratio_command("ratio-gap", gaps=GapConfiguration(1, 1)))
        self.assertEqual(outcome.status, DatasetSplitStatus.SPLIT_CREATED)
        self.assertGreater(outcome.excluded_gap_count, 0)
        self.assertEqual(verify_partition_chronology(self.repository, outcome.split_id), ())

    def test_expanding_window_is_deterministic_bounded_and_train_expands(self):
        command = DatasetSplitCommand(
            split_request_id="expanding", split_name="Expanding split",
            source_dataset_build_id=self.source.dataset_build_id,
            source_dataset_fingerprint=self.source.dataset_fingerprint,
            strategy=SplitStrategy.EXPANDING_WINDOW_V1,
            expanding_window=ExpandingWindow(BASE + timedelta(days=5), 2, 1, 1, 2),
            maximum_folds=2, split_timestamp=SPLIT_AT,
        )
        outcome = self.service.create(command)
        self.assertEqual((outcome.status, outcome.fold_count), (DatasetSplitStatus.SPLIT_CREATED, 2))
        split = self.repository.load_dataset_split(outcome.split_id)
        counts = [dict(fold.achieved_counts) for fold in split.folds]
        self.assertLess(counts[0]["TRAIN"], counts[1]["TRAIN"])
        self.assertTrue(all(not verify_partition_chronology(self.repository, outcome.split_id) for _ in (0,)))
        self.assertNotEqual(split.folds[0].fold_fingerprint, split.folds[1].fold_fingerprint)
        for fold in split.folds:
            self.assertEqual(len({item.training_example_id for item in fold.assignments}), len(fold.assignments))

    def test_expanding_gaps_are_preserved(self):
        outcome = self.service.create(DatasetSplitCommand(
            split_request_id="expanding-gap", split_name="Expanding gaps",
            source_dataset_build_id=self.source.dataset_build_id,
            source_dataset_fingerprint=self.source.dataset_fingerprint,
            strategy=SplitStrategy.EXPANDING_WINDOW_V1,
            expanding_window=ExpandingWindow(BASE + timedelta(days=4), 1, 1, 2, 2),
            gaps=GapConfiguration(1, 1), split_timestamp=SPLIT_AT,
        ))
        self.assertEqual(outcome.status, DatasetSplitStatus.SPLIT_CREATED)
        self.assertGreater(outcome.excluded_gap_count, 0)


class SourceVerificationAndPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.source = build_source(self.database)
        self.service = build_historical_dataset_split_service(self.database, migrate=False)
        self.repository = SQLiteHistoricalDatasetSplitRepository(self.database, migrate=False)

    def tearDown(self):
        self.database.close()

    def test_source_identity_fingerprint_and_schema_mismatches_reject_without_writes(self):
        cases = (
            replace(explicit_command(self.source), source_dataset_build_id="historical-training-dataset-" + "a" * 64),
            replace(explicit_command(self.source), source_dataset_fingerprint="b" * 64),
            replace(explicit_command(self.source), feature_schema_version="wrong-schema"),
            replace(explicit_command(self.source), label_schema_version="wrong-labels"),
        )
        for item in cases:
            with self.subTest(item=item):
                self.assertEqual(self.service.create(item).status, DatasetSplitStatus.REJECTED_SOURCE_DATASET)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_dataset_splits").fetchone()[0], 0)

    def test_duplicate_id_fingerprint_missing_and_non_utc_examples_fail_validation(self):
        training = SQLiteHistoricalTrainingDatasetRepository(self.database, migrate=False)
        build = training.load_dataset_build(self.source.dataset_build_id)
        example = training.list_examples_for_dataset(build.dataset_build_id)[0]
        normalized = normalize_split_command(explicit_command(self.source), DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY)
        cases = (
            (example, example),
            (example, replace(example, training_example_id="different")),
            (replace(example, kickoff_utc=""),),
            (replace(example, kickoff_utc="2025-01-01T12:00:00+01:00"),),
            (replace(example, dataset_build_id="wrong"),),
        )
        for examples in cases:
            with self.subTest(examples=examples), self.assertRaises(Exception):
                validate_source_dataset(build, examples, normalized)

    def test_corrupted_labels_fingerprints_and_leakage_fail_before_split(self):
        examples = SQLiteHistoricalTrainingDatasetRepository(self.database, migrate=False).list_examples_for_dataset(self.source.dataset_build_id)
        target = examples[-1]
        self.database.connection.execute("DROP TRIGGER historical_training_examples_no_update")
        self.database.connection.execute(
            "UPDATE historical_training_examples SET labels_snapshot='[[\"HOME_WIN\",1]]' WHERE training_example_id=?",
            (target.training_example_id,),
        )
        self.database.connection.commit()
        outcome = self.service.create(explicit_command(self.source, request_id="corrupt-label"))
        self.assertEqual(outcome.status, DatasetSplitStatus.REJECTED_SOURCE_DATASET)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_dataset_splits").fetchone()[0], 0)

    def test_failed_source_leakage_verification_creates_no_split(self):
        training = SQLiteHistoricalTrainingDatasetRepository(self.database, migrate=False)
        target = training.list_examples_for_dataset(self.source.dataset_build_id)[-1]
        self.database.connection.execute("DROP TRIGGER historical_training_example_sources_no_update")
        self.database.connection.execute(
            "UPDATE historical_training_example_sources SET source_kickoff=? WHERE training_example_id=? AND deterministic_order_index=0",
            (target.kickoff_utc, target.training_example_id),
        )
        self.database.connection.commit()
        outcome = self.service.create(explicit_command(self.source, request_id="source-leakage"))
        self.assertEqual(outcome.status, DatasetSplitStatus.REJECTED_SOURCE_DATASET)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_dataset_splits").fetchone()[0], 0)

    def test_idempotency_request_conflict_and_multiple_plans(self):
        first = self.service.create(explicit_command(self.source))
        before = self.database.connection.total_changes
        replay = self.service.create(explicit_command(self.source))
        self.assertEqual(replay.status, DatasetSplitStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(before, self.database.connection.total_changes)
        conflict = self.service.create(replace(explicit_command(self.source), split_name="Changed"))
        self.assertEqual(conflict.status, DatasetSplitStatus.CONFLICT)
        second = self.service.create(replace(explicit_command(self.source, request_id="plan-2"), split_name="Second"))
        self.assertEqual(second.status, DatasetSplitStatus.SPLIT_CREATED)
        self.assertEqual(len(self.repository.list_splits_for_dataset(self.source.dataset_build_id)), 2)

    def test_atomic_rollback_on_fold_and_assignment_failure(self):
        for table, request_id in (("historical_dataset_split_folds", "fold-failure"), ("historical_dataset_split_assignments", "assignment-failure")):
            trigger = f"force_{table}_failure"
            self.database.connection.execute(f"CREATE TRIGGER {trigger} BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'forced'); END")
            self.database.connection.commit()
            outcome = self.service.create(explicit_command(self.source, request_id=request_id))
            self.assertEqual(outcome.status, DatasetSplitStatus.PERSISTENCE_FAILURE)
            self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_dataset_splits").fetchone()[0], 0)
            self.database.connection.execute(f"DROP TRIGGER {trigger}")
            self.database.connection.commit()

    def test_append_only_foreign_keys_uniqueness_and_serialization(self):
        outcome = self.service.create(explicit_command(self.source))
        split = self.repository.load_dataset_split(outcome.split_id)
        fold = split.folds[0]
        assignment = fold.assignments[0]
        for table, key, identity in (
            ("historical_dataset_splits", "split_id", split.split_id),
            ("historical_dataset_split_folds", "fold_id", fold.fold_id),
            ("historical_dataset_split_assignments", "assignment_id", assignment.assignment_id),
        ):
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(f"UPDATE {table} SET {key}={key} WHERE {key}=?", (identity,))
            self.database.connection.rollback()
        snapshot = self.database.connection.execute("SELECT deterministic_split_snapshot FROM historical_dataset_splits").fetchone()[0]
        self.assertNotIn(": ", snapshot)


class InspectionMigrationStartupTests(unittest.TestCase):
    def test_inspection_labels_streaming_integrity_and_read_only_behavior(self):
        database = Database(":memory:")
        source = build_source(database)
        service = build_historical_dataset_split_service(database, migrate=False)
        repository = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
        outcome = service.create(explicit_command(source))
        split = repository.load_dataset_split(outcome.split_id)
        fold = split.folds[0]
        before = database.connection.total_changes
        self.assertEqual(summarize_dataset_split(repository, split.split_id).fold_count, 1)
        self.assertEqual(inspect_split_fold(repository, fold.fold_id), fold)
        self.assertEqual(inspect_partition_assignment(repository, fold.assignments[0].assignment_id), fold.assignments[0])
        self.assertEqual(verify_partition_exclusivity(repository, split.split_id), ())
        self.assertEqual(verify_partition_chronology(repository, split.split_id), ())
        self.assertEqual(verify_equal_kickoff_grouping(repository, split.split_id), ())
        self.assertEqual(verify_split_fingerprints(repository, split.split_id), ())
        training = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
        self.assertEqual(verify_source_dataset_linkage(repository, training, split.split_id), ())
        distributions = summarize_partition_labels(repository, fold.fold_id)
        self.assertTrue(all(len(labels) == 11 for _, labels in distributions))
        streamed = tuple(repository.stream_partition_examples(fold.fold_id, Partition.TRAIN))
        self.assertEqual(len(streamed), outcome.train_count)
        self.assertEqual(database.connection.total_changes, before)
        database.close()

    def test_independent_chronology_and_fingerprint_verifiers_detect_corruption(self):
        database = Database(":memory:")
        source = build_source(database)
        service = build_historical_dataset_split_service(database, migrate=False)
        repository = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
        outcome = service.create(explicit_command(source))
        fold = repository.load_dataset_split(outcome.split_id).folds[0]
        validation = repository.list_assignments_by_partition(fold.fold_id, Partition.VALIDATION)[0]
        train_kickoff = repository.list_assignments_by_partition(fold.fold_id, Partition.TRAIN)[0].kickoff_utc
        database.connection.execute("DROP TRIGGER historical_dataset_split_assignments_no_update")
        database.connection.execute(
            "UPDATE historical_dataset_split_assignments SET kickoff_timestamp=? WHERE assignment_id=?",
            (train_kickoff, validation.assignment_id),
        )
        database.connection.commit()
        self.assertTrue(verify_partition_chronology(repository, outcome.split_id))
        self.assertTrue(verify_split_fingerprints(repository, outcome.split_id))
        database.close()

    def test_fresh_v25_and_v24_upgrade_preserve_existing_data(self):
        fresh = Database(":memory:")
        MigrationManager(fresh.connection).migrate()
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 41)
        objects = {(row[0], row[1]) for row in fresh.connection.execute("SELECT name,type FROM sqlite_master")}
        for table in ("historical_dataset_splits", "historical_dataset_split_folds", "historical_dataset_split_assignments"):
            self.assertIn((table, "table"), objects)
            self.assertIn((f"{table}_no_update", "trigger"), objects)
            self.assertIn((f"{table}_no_delete", "trigger"), objects)
        fresh.close()
        upgrade = Database(":memory:")
        upgrade.connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS[:-1]:
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute("INSERT INTO schema_migrations VALUES (?, 'existing')", (migration.version,))
        upgrade.connection.execute("INSERT INTO published_predictions (prediction_id,fixture_id,market,pick,published_at) VALUES ('sentinel',1,'MATCH_WINNER','HOME','2026-01-01T00:00:00Z')")
        upgrade.connection.commit()
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 41)
        self.assertEqual(upgrade.connection.execute("SELECT prediction_id FROM published_predictions").fetchone()[0], "sentinel")
        upgrade.close()

    def test_import_is_inert_and_has_no_external_runtime_dependencies(self):
        before_threads = tuple(thread.name for thread in threading.enumerate())
        before_database = Database.DEFAULT_PATH.exists()
        import app.historical_dataset_split as package
        import app.historical_dataset_split.factory as factory
        self.assertIsNotNone((package, factory))
        self.assertEqual(tuple(thread.name for thread in threading.enumerate()), before_threads)
        self.assertEqual(Database.DEFAULT_PATH.exists(), before_database)
        source = "\n".join(path.read_text(encoding="utf-8") for path in __import__("pathlib").Path("app/historical_dataset_split").glob("*.py")).lower()
        for forbidden in (
            "import requests", "from requests", "import aiohttp", "from aiohttp",
            "apscheduler", "celery", "import telegram", "from telegram", "create_task(",
            "model.fit", "predict(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
